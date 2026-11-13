"""Combine reports/*.json into reports/evaluation_report.md."""
import json, _bootstrap  # noqa
from pathlib import Path

def sec(title, p, keys=None):
    f = Path("reports") / p
    if not f.exists(): return f"## {title}\n_not run yet (`{p}` missing)_\n"
    d = json.loads(f.read_text()); d = {k: d[k] for k in keys} if keys else d
    return f"## {title}\n```json\n{json.dumps(d, indent=2, default=str)}\n```\n"

if __name__ == "__main__":
    parts = [sec("Detection - held-out (final)", "detection_eval_heldout.json", ["assets", "point_level", "by_sensor", "event_level"]), sec("Detection - dev (development only)", "detection_eval_dev.json", ["point_level", "event_level"]),
             sec("RAG retrieval", "rag_eval.json", ["hit_rate", "mean_precision", "mrr", "insufficient_evidence_handling"]), sec("Agent / citations / governance / routing cost", "agent_eval.json", ["agent", "citations", "governance", "routing"])]
    Path("reports/evaluation_report.md").write_text("# SENTINEL Evaluation Report\n\n" + "\n".join(parts)); print("reports/evaluation_report.md written")
