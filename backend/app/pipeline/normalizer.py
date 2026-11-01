from collections.abc import Mapping
from typing import Any

from backend.app.collectors.base import Collector


def normalize_record(
    collector: Collector, raw_record: Mapping[str, Any]
) -> Mapping[str, Any]:
    return collector.normalize(raw_record)
