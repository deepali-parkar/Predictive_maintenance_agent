"""Domain exceptions (never swallowed silently)."""
class SentinelError(Exception): pass
class ConfigError(SentinelError): pass
class DataIngestionError(SentinelError): pass
class ValidationFailed(SentinelError):
    def __init__(self, message, errors=None):
        super().__init__(message); self.errors = errors or []
class NotFoundError(SentinelError): pass
class PermissionDenied(SentinelError): pass
class LLMError(SentinelError): pass
class MCPError(SentinelError): pass
class RetrievalError(SentinelError): pass
