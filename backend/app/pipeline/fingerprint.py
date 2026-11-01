import hashlib
import json
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any

INCIDENTAL_FIELDS = frozenset(
    {"observed_at", "collected_at", "first_observed_at", "last_observed_at"}
)


def _canonicalize(value: Any) -> Any:
    if isinstance(value, Decimal):
        return format(value.normalize(), "f")
    if isinstance(value, datetime):
        normalized = value.astimezone(timezone.utc) if value.tzinfo else value
        return normalized.isoformat()
    if isinstance(value, dict):
        return {
            key: _canonicalize(item)
            for key, item in sorted(value.items())
            if key not in INCIDENTAL_FIELDS
        }
    if isinstance(value, (list, tuple)):
        return [_canonicalize(item) for item in value]
    return value


def content_fingerprint(values: dict[str, Any]) -> str:
    canonical = json.dumps(
        _canonicalize(values),
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()
