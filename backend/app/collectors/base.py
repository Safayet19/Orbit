from abc import ABC, abstractmethod
from collections.abc import Mapping, Sequence
from typing import Any

from pydantic import BaseModel


class RecordNormalizationError(ValueError):
    def __init__(self, field: str) -> None:
        self.field = field
        super().__init__("Source record could not be normalized.")


class Collector(ABC):
    source_id: str
    category: str
    record_model: type[BaseModel]

    @abstractmethod
    def fetch_records(self) -> Sequence[Mapping[str, Any]]:
        """Fetch all records for one complete source response."""

    @abstractmethod
    def normalize(self, raw_record: Mapping[str, Any]) -> Mapping[str, Any]:
        """Map one source record to the registered validation schema."""

    def close(self) -> None:
        """Release resources owned by the collector."""
