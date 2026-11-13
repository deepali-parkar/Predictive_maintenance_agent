"""End-to-end agent evaluation (REQUIRES live Azure AI Foundry deployments + indexed ChromaDB). Works on a scratch copy of the DB."""
import argparse, json, shutil, _bootstrap  # noqa
from pathlib import Path
import pandas as pd
from src.agent import build_agent
from src.common.config import get_settings
from src.evaluation.agent_metrics import agent_eval, governance_eval
from src.evaluation.cost_metrics import routing_report
from src.evaluation.rag_metrics import citation_metrics
from src.maintenance_app.database import connect
from src.maintenance_app.services import get_services

if __name__ == "__main__":
    ap = argparse.ArgumentParser(); ap.add_argument("--split", default="heldout", choices=["heldout", "dev", "all"]); a = ap.parse_args(); s = get_settings()
    sp = json.loads((s.path("synthetic") / "split.json").read_text()); ids = {"heldout": sp["heldout_assets"], "dev": sp["dev_assets"], "all": sp["heldout_assets"] + sp["dev_assets"]}[a.split]
    scratch = Path("reports/eval_scratch.db"); scratch.parent.mkdir(exist_ok=True); shutil.copy(s.db_path, scratch); s.db_path = scratch
    agent = build_agent(s); results = [agent.run(i, user_question="") for i in ids]
    ev = pd.read_csv(s.path("synthetic") / "degradation_events.csv"); c = connect(scratch)
    out = {"agent": agent_eval(results, ev), "citations": citation_metrics(results), "governance": governance_eval(c), "routing": routing_report(get_services(c).model_logs.all(), s.routing["pricing_usd_per_1m_tokens"])}
    Path("reports/agent_eval.json").write_text(json.dumps({**out, "results": results}, indent=2, default=str))
    print(json.dumps({k: {kk: vv for kk, vv in v.items() if kk != "per_asset"} for k, v in out.items()}, indent=2, default=str))
