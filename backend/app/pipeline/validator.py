from collections.abc import Mapping
from typing import Any

from pydantic import BaseModel

from backend.app.collectors.base import Collector


def validate_record(
    collector: Collector, normalized_record: Mapping[str, Any]
) -> BaseModel:
    return collector.record_model.model_validate(normalized_record)
