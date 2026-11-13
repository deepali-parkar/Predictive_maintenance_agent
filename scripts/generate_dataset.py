"""Reproducible synthetic dataset + knowledge-base generator (seed 20261109).
Writes data/synthetic/*.csv, split.json, data/manuals/*.md, data/historical_work_orders/*.json.
The APPLICATION never imports this module: scenario IDs below exist only to seed demo data."""
import argparse, json, _bootstrap  # noqa
from pathlib import Path
import numpy as np, pandas as pd
from src.common.config import get_settings

SEED = 20261109
START = pd.Timestamp("2026-10-10 00:00:00"); HOURS = 720
BASE = {"pump": {"vibration": 2.5, "temperature": 55, "pressure": 6.0, "current": 18},
        "motor": {"vibration": 2.0, "temperature": 65, "pressure": 2.0, "current": 30},
        "compressor": {"vibration": 3.0, "temperature": 80, "pressure": 8.0, "current": 45}}
NOISE = {"vibration": 0.05, "temperature": 0.02, "pressure": 0.02, "current": 0.03}
UNITS = {"vibration": "mm/s", "temperature": "degC", "pressure": "bar", "current": "A"}
COLS = {"vibration": "vibration_mm_s", "temperature": "temperature_c", "pressure": "pressure_bar", "current": "current_a"}
ASSETS = [  # id, name, type, criticality
 ("PMP-101","Feed Water Pump 1","pump","HIGH"),("PMP-102","Feed Water Pump 2","pump","HIGH"),("PMP-103","Cooling Circulation Pump A","pump","MEDIUM"),
 ("PMP-104","Cooling Circulation Pump B","pump","MEDIUM"),("PMP-105","Transfer Pump 1","pump","LOW"),("PMP-106","Boiler Feed Pump","pump","CRITICAL"),
 ("PMP-107","Process Pump 7","pump","MEDIUM"),("PMP-108","Process Pump 8","pump","LOW"),
 ("MTR-201","Main Drive Motor 1","motor","HIGH"),("MTR-202","Main Drive Motor 2","motor","HIGH"),("MTR-203","Conveyor Motor 3","motor","MEDIUM"),
 ("MTR-204","Conveyor Motor 4","motor","LOW"),("MTR-205","Mixer Motor 5","motor","MEDIUM"),("MTR-206","Fan Motor 6","motor","LOW"),("MTR-207","Crusher Motor 7","motor","CRITICAL"),
 ("CMP-301","Air Compressor 1","compressor","HIGH"),("CMP-302","Air Compressor 2","compressor","HIGH"),("CMP-303","Instrument Air Compressor","compressor","MEDIUM"),
 ("CMP-304","Process Gas Compressor 4","compressor","MEDIUM"),("CMP-305","Process Gas Compressor 5","compressor","CRITICAL")]
# id -> (onset_day, {sensor: relative change}, failure_mode, pattern, confirmed, expected_risk, acceptable decisions)
EVENTS = {
 "PMP-102": (16, {"vibration": +0.90}, "BEARING_WEAR", "vibration_rise", False, "MEDIUM", "MONITOR|INSPECT_FIRST"),
 "PMP-104": (14, {"pressure": -0.28}, "PRESSURE_LOSS", "pressure_drift", False, "MEDIUM", "INSPECT_FIRST|CREATE_DRAFT"),
 "PMP-106": (12, {"vibration": +1.70, "temperature": +0.40}, "BEARING_WEAR", "multi_sensor", True, "HIGH", "CREATE_DRAFT"),
 "PMP-107": (15, {"temperature": +0.55}, "OVERHEATING", "overheating", False, "MEDIUM", "INSPECT_FIRST|CREATE_DRAFT"),
 "MTR-202": (15, {"vibration": +1.20}, "MISALIGNMENT_IMBALANCE", "vibration_rise", False, "MEDIUM", "INSPECT_FIRST|CREATE_DRAFT"),
 "MTR-203": (13, {"temperature": +0.35, "current": +0.30}, "WINDING_DEGRADATION", "multi_sensor", False, "HIGH", "CREATE_DRAFT|INSPECT_FIRST"),
 "MTR-205": (20, {"current": +0.28}, "ELECTRICAL_OVERLOAD", "current_abnormal", False, "LOW", "MONITOR|INSPECT_FIRST"),
 "MTR-207": (11, {"vibration": +1.50, "temperature": +0.35, "current": +0.25}, "BEARING_WEAR", "multi_sensor", False, "HIGH", "CREATE_DRAFT"),
 "CMP-302": (14, {"pressure": -0.25}, "PRESSURE_LOSS", "pressure_drift", False, "MEDIUM", "INSPECT_FIRST|CREATE_DRAFT"),
 "CMP-303": (15, {"current": +0.30}, "ELECTRICAL_OVERLOAD", "current_abnormal", False, "MEDIUM", "INSUFFICIENT_EVIDENCE|MONITOR"),
 "CMP-305": (12, {"vibration": +1.40, "temperature": +0.30}, "BEARING_WEAR", "multi_sensor", False, "HIGH", "CREATE_DRAFT"),
}
HELD_OUT = ["PMP-108", "PMP-107", "MTR-207", "CMP-302"]   # 20% of assets (healthy + 3 degradation patterns)
MFR = ["Grundfos-like", "Siemens-like", "Atlas-like", "ABB-like", "Flowserve-like"]
LOC = ["Boiler House", "Utilities Bay", "Process Hall A", "Process Hall B", "Compressor Room"]
PARTS = [("SP-BRG-6309","Deep groove ball bearing 6309","pump;motor",12,4,38.5,"Shaft bearing for pumps and motors"),
 ("SP-BRG-7312","Angular contact bearing 7312","compressor",6,2,92.0,"Compressor bearing set"),
 ("SP-SEAL-MS40","Mechanical seal 40mm","pump",5,2,145.0,"Pump mechanical seal"),
 ("SP-IMP-210","Impeller 210mm","pump",2,1,420.0,"Replacement impeller"),
 ("SP-CPL-ELA","Elastomer coupling insert","pump;motor;compressor",10,3,24.0,"Flexible coupling element"),
 ("SP-FAN-MTR","Motor cooling fan","motor",3,1,55.0,"TEFC motor cooling fan"),
 ("SP-WND-KIT","Winding repair kit","motor",1,1,640.0,"Stator rewind consumables"),
 ("SP-VLV-PLT","Compressor valve plate","compressor",4,2,210.0,"Suction/discharge valve plate"),
 ("SP-FLT-OIL","Oil filter cartridge","compressor;pump",15,5,18.0,"Lube oil filter"),
 ("SP-GRS-EP2","EP2 bearing grease 400g","all",30,10,9.5,"Lithium complex grease"),
 ("SP-TC-K","Type K thermocouple","all",8,3,14.0,"Temperature probe"),
 ("SP-SNS-VIB","Vibration sensor (accelerometer)","all",0,2,185.0,"Out of stock - reorder")]

def make_series(rng, atype, ev, hours):
    t = np.arange(hours); out = {}; labels = {}; mult = rng.normal(1, 0.03)
    for s, b in BASE[atype].items():
        base = b * mult
        v = base * (1 + rng.normal(0, NOISE[s], hours)) * (1 + 0.015 * np.sin(2 * np.pi * t / 24) * (s in ("temperature", "current")))
        lab = np.zeros(hours, int)
        if ev and s in ev[1]:
            onset = ev[0] * 24; frac = np.clip((t - onset) / (hours - onset), 0, 1) ** 1.2
            v = v * (1 + ev[1][s] * frac); lab = (frac >= 0.2).astype(int)
        out[s] = v; labels[s] = lab
    return out, labels

def build_documents(cfg):
    M = [("MAN-PUMP-BRG","Centrifugal Pump Bearing Maintenance Manual","pump","BEARING_WEAR",
      "A progressive rise in overall vibration velocity over days, often with a modest increase in bearing housing temperature. On pumps, vibration above 4.0 mm/s is an alert level and above 6.0 mm/s requires prompt action.",
      "Lubricant degradation or contamination, excessive radial load, shaft misalignment and fatigue spalling of the rolling elements.",
      "Take a vibration spectrum and look for bearing defect frequencies. Check bearing housing temperature, sample the lubricant for particles, and verify shaft alignment.",
      "Schedule bearing replacement and re-lubrication. Verify alignment after reassembly and record a new vibration baseline."),
     ("MAN-PUMP-SEAL","Centrifugal Pump Seal and Hydraulic Performance Manual","pump","PRESSURE_LOSS",
      "Gradual downward drift of discharge pressure, reduced flow and visible leakage at the seal faces.",
      "Mechanical seal face wear, impeller wear-ring erosion, suction-side restriction and internal recirculation.",
      "Inspect the seal for leakage, check suction pressure and strainer condition, and compare differential head with the pump curve.",
      "Replace the mechanical seal or impeller wear rings. Clean the suction strainer and re-test discharge pressure."),
     ("MAN-PUMP-HEAT","Pump Overheating Troubleshooting Guide","pump","OVERHEATING",
      "Casing or bearing temperature rising steadily; above 70 degC is a warning level and above 85 degC is critical for standard pumps.",
      "Running at low flow, loss of cooling or flushing flow, bearing friction and seal rubbing.",
      "Confirm operating point against minimum flow, verify cooling and flush lines, and check bearing lubrication.",
      "Restore minimum flow, repair cooling or flush circuits, and replace damaged seals or bearings."),
     ("MAN-MTR-IMB","Electric Motor Vibration, Imbalance and Misalignment Manual","motor","MISALIGNMENT_IMBALANCE",
      "Vibration rising at 1x and 2x running speed. Motor vibration above 3.5 mm/s is an alert level and above 5.5 mm/s is critical.",
      "Coupling misalignment, rotor imbalance, soft foot and loose mounting bolts.",
      "Perform laser alignment, check foundation bolts and soft foot, and inspect the coupling element.",
      "Realign the drive train, rebalance the rotor if required and replace worn coupling inserts."),
     ("MAN-MTR-WIND","Electric Motor Winding and Thermal Degradation Manual","motor","WINDING_DEGRADATION",
      "Winding or frame temperature rising together with increased phase current.",
      "Insulation breakdown, inter-turn short circuits and blocked ventilation.",
      "Measure insulation resistance, compare phase currents for imbalance, and inspect the cooling fan and air passages.",
      "Clean ventilation, replace the cooling fan where damaged, and arrange rewind or motor replacement if insulation resistance is low."),
     ("MAN-MTR-ELEC","Electric Motor Overload and Supply Quality Manual","motor","ELECTRICAL_OVERLOAD",
      "Current rising above nameplate trend without a matching temperature rise.",
      "Driven-equipment drag, voltage imbalance, and excessive mechanical load.",
      "Check supply voltage balance, driven load condition and coupling freedom of rotation.",
      "Correct the supply issue or reduce load, and re-measure running current."),
     ("MAN-CMP-VALVE","Reciprocating Compressor Valve and Pressure Manual","compressor","PRESSURE_LOSS",
      "Discharge pressure falling below set point with longer loaded cycles.",
      "Valve plate leakage, clogged intake filter and system leaks.",
      "Inspect valve plates and intake filter, and perform a leak survey of the discharge line.",
      "Replace worn valve plates and filter elements and re-test the pressure build-up time."),
     ("MAN-CMP-BRG","Compressor Bearing and Vibration Manual","compressor","BEARING_WEAR",
      "Rising vibration on the crankcase with increasing bearing temperature. Above 5.0 mm/s is an alert level and above 7.5 mm/s is critical.",
      "Oil starvation or degradation, bearing fatigue and loose crosshead components.",
      "Analyse the vibration spectrum, sample the oil and inspect bearing shells at the next opportunity.",
      "Replace bearings and oil filters, renew the oil charge and verify clearances."),
     ("MAN-CMP-HEAT","Compressor Cooling and Overheating Manual","compressor","OVERHEATING",
      "Discharge or cylinder temperature rising; above 95 degC is a warning level and above 110 degC is critical.",
      "Fouled intercooler or aftercooler, insufficient cooling air or water, and valve leakage causing re-compression.",
      "Inspect cooler cleanliness and cooling flow, and check valve condition.",
      "Clean coolers, restore cooling flow and replace leaking valves."),
     ("MAN-GEN-VIB","General Rotating Equipment Vibration Troubleshooting Guide","general","MISALIGNMENT_IMBALANCE",
      "Vibration trending upward on any rotating asset indicates developing mechanical looseness, imbalance, misalignment or bearing damage.",
      "Imbalance and misalignment dominate at 1x and 2x speed; bearing defects appear at non-synchronous frequencies.",
      "Compare current readings with the commissioning baseline, confirm sensor mounting, then perform spectrum analysis.",
      "Treat by correcting the identified fault; avoid replacing parts before the cause is confirmed.")]
    m_dir = Path(cfg.path("manuals")); m_dir.mkdir(parents=True, exist_ok=True)
    for f in m_dir.glob("*.md"): f.unlink()
    for did, title, at, fm, sym, cau, ins, cor in M:
        body = f"---\ndocument_id: {did}\ndocument_type: manual\ndocument_title: {title}\nasset_type: {at}\nfailure_mode: {fm}\nsource_file: {did}.md\n---\n"
        for i, (h, t) in enumerate([("Symptoms and Indicators", sym), ("Probable Causes", cau), ("Inspection Procedure", ins), ("Corrective Action", cor)], 1):
            body += f"\n## {h}\n<!-- page: {i} -->\n{t}\n"
        (m_dir / f"{did}.md").write_text(body, encoding="utf-8")
    h_dir = Path(cfg.path("historical_work_orders")); h_dir.mkdir(parents=True, exist_ok=True)
    for f in h_dir.glob("*.json"): f.unlink()
    H = [("pump","BEARING_WEAR","Replace drive-end bearing on feed pump","Vibration rose from 2.6 to 5.8 mm/s over 12 days with bearing temperature +9 degC.",["Isolate and lock out pump","Replace drive-end bearing","Re-grease and realign"],["SP-BRG-6309"],"Vibration returned to 2.5 mm/s after repair."),
     ("pump","BEARING_WEAR","Bearing replacement after spectrum alarm","Spectrum showed outer-race defect frequency; housing warm to touch.",["Replace both bearings","Check shaft runout"],["SP-BRG-6309","SP-GRS-EP2"],"Normal operation restored."),
     ("pump","PRESSURE_LOSS","Seal replacement for falling discharge pressure","Discharge pressure fell 20% with seal weep observed.",["Replace mechanical seal","Clean suction strainer"],["SP-SEAL-MS40"],"Pressure back to set point."),
     ("pump","OVERHEATING","Cooling flush line blocked on process pump","Casing temperature climbed above 75 degC at normal load.",["Clear flush line","Verify minimum flow"],[],"Temperature normalised at 56 degC."),
     ("motor","MISALIGNMENT_IMBALANCE","Realign motor and replace coupling insert","Vibration at 2x speed; coupling insert cracked.",["Laser align","Replace coupling insert"],["SP-CPL-ELA"],"Vibration dropped by 60%."),
     ("motor","WINDING_DEGRADATION","Motor overheating with rising current","Frame temperature +25% and current +20%; insulation resistance low.",["Megger test","Replace cooling fan","Plan rewind"],["SP-FAN-MTR","SP-WND-KIT"],"Motor rewound; temperature normal."),
     ("motor","ELECTRICAL_OVERLOAD","Motor current high due to dragging conveyor","Current +25% with no temperature rise.",["Free conveyor roller","Check voltage balance"],[],"Current normalised."),
     ("compressor","PRESSURE_LOSS","Valve plate replacement on air compressor","Longer loaded cycles and low discharge pressure.",["Replace valve plates","Replace intake filter"],["SP-VLV-PLT","SP-FLT-OIL"],"Build-up time restored."),
     ("compressor","OVERHEATING","Aftercooler fouling on gas compressor","Discharge temperature +20% over baseline.",["Clean aftercooler","Verify cooling water flow"],[],"Temperature back to normal.")]
    for i, (at, fm, title, prob, acts, parts, outc) in enumerate(H, 1):
        d = {"document_id": f"WO-HIST-{i:03d}", "document_type": "historical_work_order", "document_title": title, "asset_type": at,
             "failure_mode": fm, "problem_description": prob, "actions_taken": acts, "parts_used": parts, "outcome": outc}
        (h_dir / f"WO-HIST-{i:03d}.json").write_text(json.dumps(d, indent=2), encoding="utf-8")

def main():
    cfg = get_settings(); out = cfg.path("synthetic"); out.mkdir(parents=True, exist_ok=True)
    rng = np.random.default_rng(SEED); idx = pd.date_range(START, periods=HOURS, freq="h")
    A, wide, labs, evs, mh = [], [], [], [], []
    for n, (aid, name, atype, crit) in enumerate(ASSETS):
        A.append({"asset_id": aid, "asset_name": name, "asset_type": atype, "manufacturer": MFR[n % 5], "location": LOC[n % 5], "criticality": crit,
                  "installation_date": str((pd.Timestamp("2018-01-01") + pd.Timedelta(days=int(rng.integers(0, 2500)))).date()), "operating_status": "RUNNING"})
        ev = EVENTS.get(aid); series, lab = make_series(rng, atype, ev, HOURS)
        df = pd.DataFrame({"asset_id": aid, "timestamp": idx.strftime("%Y-%m-%d %H:%M:%S")})
        for s in series: df[COLS[s]] = series[s].round(3)
        if not ev:  # sprinkle missing readings in healthy assets (never zero-filled downstream)
            for s in COLS.values(): df.loc[rng.choice(HOURS, 3, replace=False), s] = np.nan
        wide.append(df)
        for s in series:
            labs.append(pd.DataFrame({"asset_id": aid, "timestamp": df["timestamp"], "sensor_name": s, "label": lab[s], "event_id": f"EV-{aid}" if lab[s].any() else ""}))
        if ev:
            onset_t = idx[int(ev[0] * 24 + 0.2 ** (1 / 1.2) * (HOURS - ev[0] * 24))]
            evs.append({"event_id": f"EV-{aid}", "asset_id": aid, "pattern": ev[3], "sensors": ";".join(ev[1]), "failure_mode": ev[2],
                        "ramp_start": str(idx[ev[0] * 24]), "label_onset": str(onset_t), "end_time": str(idx[-1]),
                        "projected_failure_time": str(idx[-1] + pd.Timedelta(hours=int(0.6 * (HOURS - ev[0] * 24)))),
                        "confirmed_fault": ev[4], "expected_risk_level": ev[5], "acceptable_decisions": ev[6], "expected_citation_failure_mode": ev[2]})
        last_pm = pd.Timestamp("2026-10-10") - pd.Timedelta(days=int(rng.integers(40, 320)))
        mh.append({"maintenance_id": f"MH-{aid}-1", "asset_id": aid, "maintenance_date": str(last_pm.date()), "maintenance_type": "PREVENTIVE",
                   "description": "Routine lubrication, alignment and vibration check", "technician": "T. Rao", "parts_used": "SP-GRS-EP2", "outcome": "COMPLETED"})
        mh.append({"maintenance_id": f"MH-{aid}-2", "asset_id": aid, "maintenance_date": str((last_pm - pd.Timedelta(days=180)).date()), "maintenance_type": "INSPECTION",
                   "description": "Quarterly condition inspection", "technician": "S. Patil", "parts_used": "", "outcome": "NO_FINDINGS"})
        if aid == "PMP-106":
            mh.append({"maintenance_id": "MH-PMP-106-3", "asset_id": aid, "maintenance_date": "2026-11-05", "maintenance_type": "INSPECTION",
                       "description": "Bearing housing crack and abnormal noise found during walk-down", "technician": "S. Patil", "parts_used": "", "outcome": "FAULT_CONFIRMED"})
    pd.DataFrame(A).to_csv(out / "assets.csv", index=False)
    pd.concat(wide).to_csv(out / "sensor_readings.csv", index=False)
    pd.concat(labs).to_csv(out / "sensor_labels.csv", index=False)
    pd.DataFrame(evs).to_csv(out / "degradation_events.csv", index=False)
    pd.DataFrame(mh).to_csv(out / "maintenance_history.csv", index=False)
    pd.DataFrame([dict(zip(["part_id","part_name","compatible_asset_types","quantity_available","reorder_level","unit_cost","description"], p)) for p in PARTS]).to_csv(out / "spare_parts.csv", index=False)
    rows = [{"asset_type": at, "sensor": s, **{k: v for k, v in c.items() if k != "unit"}, "unit": c.get("unit", "")} for at, d in cfg.detection["thresholds"].items() for s, c in d.items()]
    pd.DataFrame(rows).to_csv(out / "threshold_config.csv", index=False)
    all_ids = [a[0] for a in ASSETS]
    (out / "split.json").write_text(json.dumps({"seed": SEED, "heldout_assets": HELD_OUT, "dev_assets": [a for a in all_ids if a not in HELD_OUT],
        "note": "Held-out assets must NOT be used to tune detection thresholds; used only for final reporting."}, indent=2))
    build_documents(cfg)
    print(f"Generated {len(ASSETS)} assets, {sum(len(w) for w in wide)} wide rows, {len(evs)} degradation events, 10 manuals, 9 historical work orders -> {out}")

if __name__ == "__main__":
    argparse.ArgumentParser().parse_args(); main()
