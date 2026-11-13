"""Structured JSON logging with correlation ids propagated via contextvars."""
import contextvars, json, logging, os, uuid
from datetime import datetime, timezone

_cid: contextvars.ContextVar[str] = contextvars.ContextVar("correlation_id", default="-")

def new_correlation_id(prefix: str = "corr") -> str:
    return f"{prefix}-{uuid.uuid4().hex[:12]}"

def set_correlation_id(cid: str) -> None: _cid.set(cid)
def get_correlation_id() -> str: return _cid.get()

class _JsonFormatter(logging.Formatter):
    def format(self, record):
        d = {"ts": datetime.now(timezone.utc).isoformat(timespec="seconds"), "level": record.levelname,
             "logger": record.name, "correlation_id": get_correlation_id(), "msg": record.getMessage()}
        extra = getattr(record, "ctx", None)
        if extra: d.update(extra)
        if record.exc_info: d["exc"] = self.formatException(record.exc_info)
        return json.dumps(d, default=str)

def get_logger(name: str) -> logging.Logger:
    root = logging.getLogger("sentinel")
    if not root.handlers:
        h = logging.StreamHandler(); h.setFormatter(_JsonFormatter()); root.addHandler(h)
        root.setLevel(os.getenv("SENTINEL_LOG_LEVEL", "INFO")); root.propagate = False
    return logging.getLogger(f"sentinel.{name}")
