"""One-shot setup: generate data -> validate -> init DB -> ingest -> detect -> (optionally) index documents in ChromaDB."""
import argparse, subprocess, sys, _bootstrap  # noqa
from pathlib import Path
ROOT = Path(__file__).resolve().parent

def run(script, *args):
    print(f"\n=== {script} {' '.join(args)}"); r = subprocess.run([sys.executable, str(ROOT / script), *args])
    if r.returncode: raise SystemExit(f"{script} failed")

if __name__ == "__main__":
    ap = argparse.ArgumentParser(); ap.add_argument("--skip-docs", action="store_true", help="skip ChromaDB indexing (needs Azure embedding deployment)"); a = ap.parse_args()
    run("generate_dataset.py"); run("validate_dataset.py"); run("initialize_database.py"); run("ingest_dataset.py"); run("run_detection.py")
    if not a.skip_docs: run("ingest_documents.py", "--reset")
    run("evaluate_detection.py", "--split", "heldout"); print("\nSetup complete. Start the UI with:  streamlit run app.py")
