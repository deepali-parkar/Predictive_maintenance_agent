import pandas as pd
from tests.helpers import make_env
from src.ingestion.dataset_adapter import ingest_dataframe
from src.maintenance_app.database import connect
from src.maintenance_app.services import get_services

def _df(n=100, **cols):
    return pd.DataFrame({"Equipment": "NEW-1", "Date Time": pd.date_range("2026-12-01", periods=n, freq="30min").strftime("%d/%m/%Y %H:%M"), **cols})

def test_different_names_units_and_extra_sensor():
    s, db = make_env(); c = connect(db)
    df = _df(Vib=[0.1] * 100, **{"Temp (°F)": [140.0] * 100, "Press_psi": [87.0] * 100, "Amps": [20.0] * 100, "RPM": [1480.0] * 100})
    rep = ingest_dataframe(c, df, dayfirst=True); assert rep.ok, rep.errors
    svc = get_services(c); sens = svc.sensors.sensors("NEW-1"); assert {"vibration", "temperature", "pressure", "current", "rpm"} <= set(sens)
    t = svc.sensors.history("NEW-1", "temperature")["value"].iloc[0]; assert abs(t - 60.0) < 0.01      # 140F -> 60C
    p = svc.sensors.history("NEW-1", "pressure")["value"].iloc[0]; assert abs(p - 6.0) < 0.01          # 87 psi -> ~6 bar
    assert "NEW-1" in rep.new_assets_registered and rep.sampling_interval_minutes["NEW-1"] == 30.0

def test_missing_dupes_invalid_timestamps_reported_not_zero_filled():
    s, db = make_env(); c = connect(db); df = _df(60, vibration_mm_s=[1.0] * 60)
    df.loc[3, "vibration_mm_s"] = None; df.loc[5, "Date Time"] = "garbage"; df = pd.concat([df, df.iloc[[10]]])
    rep = ingest_dataframe(c, df, dayfirst=True); svc = get_services(c)
    assert rep.missing_values == 1 and rep.invalid_timestamps == 1 and rep.duplicates_removed == 1
    assert (svc.sensors.history("NEW-1")["value"] > 0).all() and len(svc.sensors.history("NEW-1")) == 58

def test_unknown_assets_reject_policy_and_long_format():
    s, db = make_env(); c = connect(db)
    long = pd.DataFrame({"machine_id": ["PMP-101", "ZZZ-9"], "timestamp": ["2027-01-01 00:00:00"] * 2, "sensor": ["vib", "vib"], "value": [2.5, 9.0], "unit": ["mm/s"] * 2})
    rep = ingest_dataframe(c, long, unknown_assets="reject"); assert rep.rejected_assets == ["ZZZ-9"] and rep.rows_inserted == 1
    assert get_services(c).assets.get("ZZZ-9") is None

def test_unrecognised_columns_error_not_crash():
    s, db = make_env(); c = connect(db); rep = ingest_dataframe(c, pd.DataFrame({"foo": [1], "bar": [2]})); assert not rep.ok and rep.errors

def test_new_asset_with_metadata_dynamic_registration_and_detection():
    from src.detection.detection_service import run_detection
    import numpy as np
    s, db = make_env(); c = connect(db); n = 400; r = np.random.default_rng(3)
    v = 3.0 * (1 + r.normal(0, .04, n)); v[300:] *= 2.2
    df = pd.DataFrame({"equipment_id": "UNSEEN-7", "datetime": pd.date_range("2027-02-01", periods=n, freq="h").astype(str), "vib": v})
    meta = pd.DataFrame({"id": ["UNSEEN-7"], "name": ["Mystery Pump"], "type": ["pump"], "criticality": ["high"]})
    assert ingest_dataframe(c, df, meta).ok
    res = run_detection(c, ["UNSEEN-7"], settings=s)[0]; assert res["affected_sensors"] == ["vibration"] and res["risk_level"] in ("MEDIUM", "HIGH")

def test_short_upload_is_not_assessed_instead_of_fake_low():
    from src.dashboard.data import build_overview_df
    from src.detection.detection_service import run_detection
    s, db = make_env(); c = connect(db)
    df = pd.DataFrame({"equipment_id": "SHORT-1", "datetime": pd.date_range("2027-03-01", periods=20, freq="h").astype(str), "vib": [2.0] * 20})
    meta = pd.DataFrame({"id": ["SHORT-1"], "name": ["Tiny"], "type": ["pump"], "criticality": ["HIGH"]})
    ingest_dataframe(c, df, meta); run_detection(c, ["SHORT-1"], settings=s)
    row = build_overview_df(c).set_index("asset_id").loc["SHORT-1"]; assert row.risk_level == "UNASSESSED" and row.criticality == "HIGH"
    ingest_dataframe(c, pd.DataFrame({"equipment_id": "BARE-1", "datetime": ["2027-03-01 00:00:00"], "vib": [1.0]}))      # never assessed at all
    assert build_overview_df(c).set_index("asset_id").loc["BARE-1"].risk_level == "UNASSESSED"

def test_delete_asset_removes_dependents_and_is_audited():
    s, db = make_env(); c = connect(db); svc = get_services(c); n = svc.assets.counts("PMP-101")
    assert n["readings"] > 0 and svc.asset_admin.delete_asset("PMP-101", "planner.x")["readings"] == n["readings"]
    assert svc.assets.get("PMP-101") is None and c.execute("SELECT COUNT(*) FROM sensor_readings WHERE asset_id='PMP-101'").fetchone()[0] == 0
    assert svc.audit.trail("PMP-101")[0]["action"] == "DELETE_ASSET"
