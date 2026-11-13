"""Detection metrics. Final reporting uses the HELD-OUT split (default). --split dev is for development only."""
import argparse, json, _bootstrap  # noqa
from pathlib import Path
from src.common.config import get_settings
from src.evaluation.detection_metrics import evaluate
from src.maintenance_app.database import connect, init_db

if __name__ == "__main__":
    ap = argparse.ArgumentParser(); ap.add_argument("--split", default="heldout", choices=["heldout", "dev", "all"]); ap.add_argument("--out", default="reports/detection_eval_%s.json"); a = ap.parse_args()
    s = get_settings(); d = s.path("synthetic"); sp = json.loads((d / "split.json").read_text()); c = connect(); init_db(c)
    ids = sp["heldout_assets"] if a.split == "heldout" else sp["dev_assets"] if a.split == "dev" else sp["heldout_assets"] + sp["dev_assets"]
    res = evaluate(c, d, s.detection, ids); out = Path(a.out % a.split if "%s" in a.out else a.out); out.parent.mkdir(exist_ok=True); out.write_text(json.dumps(res, indent=2))
    print(f"[{a.split}] assets={ids}"); print("point-level:", json.dumps(res["point_level"])); print("event-level:", json.dumps(res["event_level"]))
    print("by sensor:", {k: (v["precision"], v["recall"]) for k, v in res["by_sensor"].items()}); print(f"-> {out}")
