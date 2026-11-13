"""Sanity-check the generated synthetic dataset."""
import argparse, json, _bootstrap  # noqa
import pandas as pd
from src.common.config import get_settings

def main():
    d = get_settings().path("synthetic"); errs = []
    a = pd.read_csv(d / "assets.csv"); r = pd.read_csv(d / "sensor_readings.csv"); l = pd.read_csv(d / "sensor_labels.csv")
    e = pd.read_csv(d / "degradation_events.csv"); sp = json.loads((d / "split.json").read_text())
    if len(a) != 20: errs.append(f"expected 20 assets, got {len(a)}")
    if len(r) != 14400: errs.append(f"expected 14400 wide rows, got {len(r)}")
    if set(r.asset_id) != set(a.asset_id): errs.append("asset mismatch between assets and readings")
    if r.duplicated(["asset_id", "timestamp"]).any(): errs.append("duplicate readings")
    if set(sp["heldout_assets"]) & set(sp["dev_assets"]): errs.append("split overlap")
    if not set(e.asset_id) <= set(a.asset_id): errs.append("event for unknown asset")
    if not l.groupby("asset_id").label.max().reindex(e.asset_id).eq(1).all(): errs.append("events without positive labels")
    print("Missing fraction:", round(float(r.isna().mean(numeric_only=True).mean()), 5), "| positive label rate:", round(float(l.label.mean()), 4))
    print("VALID" if not errs else "INVALID: " + "; ".join(errs)); raise SystemExit(1 if errs else 0)
if __name__ == "__main__": argparse.ArgumentParser().parse_args(); main()
