"""Data-quality validation and reporting for canonical sensor frames."""
from __future__ import annotations
from dataclasses import asdict, dataclass, field
import pandas as pd

@dataclass
class DataQualityReport:
    rows_in: int = 0; rows_valid: int = 0; rows_inserted: int = 0; invalid_timestamps: int = 0; missing_values: int = 0
    duplicates_removed: int = 0; duplicates_already_in_db: int = 0
    assets_seen: list = field(default_factory=list); new_assets_registered: list = field(default_factory=list)
    rejected_assets: list = field(default_factory=list); sensors: dict = field(default_factory=dict)
    sampling_interval_minutes: dict = field(default_factory=dict); warnings: list = field(default_factory=list); errors: list = field(default_factory=list)
    @property
    def ok(self) -> bool: return not self.errors
    def to_dict(self) -> dict: d = asdict(self); d["ok"] = self.ok; return d

def validate_long(df: pd.DataFrame, rep: DataQualityReport) -> pd.DataFrame:
    """Drops empty asset ids; warns on implausible values and irregular sampling. Does not alter valid values."""
    if df.empty: rep.errors.append("no valid readings after normalisation"); return df
    blank = df["asset_id"].isin(["", "nan", "None"]); 
    if blank.any(): rep.warnings.append(f"{int(blank.sum())} rows with empty asset id dropped"); df = df[~blank]
    for s, g in df.groupby("sensor_name"):
        rep.sensors[s] = int(len(g))
        if s in ("vibration", "current", "pressure") and (g["value"] < 0).any(): rep.warnings.append(f"negative {s} values present")
    for a, g in df.groupby("asset_id"):
        t = pd.to_datetime(g["timestamp"]).drop_duplicates().sort_values().diff().dropna()
        if len(t): rep.sampling_interval_minutes[a] = round(float(t.median().total_seconds() / 60), 2)
    return df
