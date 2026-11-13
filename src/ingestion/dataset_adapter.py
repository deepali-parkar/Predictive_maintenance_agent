"""Public facade of the Dataset Adapter (column mapping + normalisation + validation + SQLite ingestion)."""
from src.ingestion.column_mapping import ColumnMap, detect_columns
from src.ingestion.ingestion_service import ingest_csv, ingest_dataframe, ingest_maintenance, ingest_spares, load_mapping
from src.ingestion.normalization import to_long
from src.ingestion.validation import DataQualityReport
__all__ = ["ColumnMap", "detect_columns", "ingest_csv", "ingest_dataframe", "ingest_maintenance", "ingest_spares", "load_mapping", "to_long", "DataQualityReport"]
