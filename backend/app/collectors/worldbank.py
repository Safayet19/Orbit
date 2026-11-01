import json
import logging
import time
from collections.abc import Mapping
from decimal import Decimal
from typing import Any

import httpx

from backend.app.collectors.base import Collector, RecordNormalizationError
from backend.app.schemas.records import (
    WORLD_BANK_SOURCE_ID,
    WORLD_BANK_SOURCE_URL,
    WorldBankInflationRecord,
)

LOGGER = logging.getLogger(__name__)
REQUEST_TIMEOUT_SECONDS = 20.0
RETRY_ATTEMPTS = 3
MAX_PAGES = 100
PAGE_SIZE = 1000
RETRYABLE_STATUS_CODES = frozenset({429, 500, 502, 503, 504})


class CollectorError(RuntimeError):
    """Raised when a source cannot be collected safely."""


class WorldBankInflationCollector(Collector):
    source_id = WORLD_BANK_SOURCE_ID
    category = "economic_indicators"
    record_model = WorldBankInflationRecord

    def __init__(
        self,
        client: httpx.Client | None = None,
        retry_delay: float = 0.5,
    ) -> None:
        self._owns_client = client is None
        self._client = client or httpx.Client(
            timeout=httpx.Timeout(REQUEST_TIMEOUT_SECONDS),
            follow_redirects=False,
        )
        self._retry_delay = retry_delay

    def close(self) -> None:
        if self._owns_client:
            self._client.close()

    def _request_page(self, page: int) -> tuple[dict[str, Any], list[Any]]:
        for attempt in range(RETRY_ATTEMPTS):
            try:
                response = self._client.get(
                    WORLD_BANK_SOURCE_URL,
                    params={
                        "format": "json",
                        "per_page": PAGE_SIZE,
                        "page": page,
                    },
                )
                if (
                    response.status_code in RETRYABLE_STATUS_CODES
                    and attempt + 1 < RETRY_ATTEMPTS
                ):
                    time.sleep(self._retry_delay * (2**attempt))
                    continue
                response.raise_for_status()
                payload = json.loads(response.content, parse_float=Decimal)
                return self._parse_page(payload, page)
            except httpx.HTTPStatusError as exc:
                raise CollectorError(
                    f"World Bank request failed with HTTP {exc.response.status_code}."
                ) from None
            except (httpx.TimeoutException, httpx.NetworkError) as exc:
                if attempt + 1 < RETRY_ATTEMPTS:
                    LOGGER.warning(
                        "source_request_retry source=%s attempt=%d error_type=%s",
                        self.source_id,
                        attempt + 1,
                        type(exc).__name__,
                    )
                    time.sleep(self._retry_delay * (2**attempt))
                    continue
                raise CollectorError(
                    f"World Bank request failed ({type(exc).__name__})."
                ) from None
            except (json.JSONDecodeError, UnicodeDecodeError, TypeError) as exc:
                raise CollectorError(
                    f"World Bank returned invalid JSON ({type(exc).__name__})."
                ) from None
        raise CollectorError("World Bank request exhausted its retry limit.")

    @staticmethod
    def _parse_page(payload: object, requested_page: int) -> tuple[dict[str, Any], list[Any]]:
        if not isinstance(payload, list) or len(payload) != 2:
            raise CollectorError("World Bank response has an unsupported format.")

        metadata, records = payload
        if not isinstance(metadata, dict):
            raise CollectorError("World Bank response metadata is malformed.")
        if not isinstance(records, list):
            total = metadata.get("total")
            if records is None and total == 0:
                records = []
            else:
                raise CollectorError("World Bank response records are malformed.")
        if any(not isinstance(record, Mapping) for record in records):
            raise CollectorError("World Bank response contains a malformed record.")

        page = metadata.get("page")
        pages = metadata.get("pages")
        if (
            isinstance(page, bool)
            or not isinstance(page, int)
            or page != requested_page
            or isinstance(pages, bool)
            or not isinstance(pages, int)
            or pages < 0
            or pages > MAX_PAGES
        ):
            raise CollectorError("World Bank pagination metadata is invalid.")
        return metadata, records

    def fetch_records(self) -> list[Mapping[str, Any]]:
        metadata, records = self._request_page(1)
        total_pages = metadata["pages"]
        if total_pages == 0:
            return []

        results = [record for record in records if record.get("value") is not None]
        for page in range(2, total_pages + 1):
            _, page_records = self._request_page(page)
            results.extend(
                record for record in page_records if record.get("value") is not None
            )
        return results

    def normalize(self, raw_record: Mapping[str, Any]) -> Mapping[str, Any]:
        country = raw_record.get("country")
        indicator = raw_record.get("indicator")
        country_code = raw_record.get("countryiso3code")
        year_value = raw_record.get("date")

        if not isinstance(country, Mapping) or not isinstance(indicator, Mapping):
            raise RecordNormalizationError("country_or_indicator")

        country_identifier = country.get("id")
        indicator_identifier = indicator.get("id")
        if not isinstance(year_value, str):
            raise RecordNormalizationError("year")

        try:
            year = int(year_value)
        except ValueError:
            raise RecordNormalizationError("year") from None

        if not isinstance(country_code, str):
            raise RecordNormalizationError("country_code")
        if not isinstance(country_identifier, str) or country_identifier != "BD":
            raise RecordNormalizationError("country_identifier")
        if (
            not isinstance(indicator_identifier, str)
            or indicator_identifier != "FP.CPI.TOTL.ZG"
        ):
            raise RecordNormalizationError("indicator_identifier")

        return {
            "source_id": self.source_id,
            "external_record_id": (
                f"{self.source_id}:{country_code}:"
                f"{indicator_identifier}:{year}"
            ),
            "country_code": country_code,
            "indicator_code": indicator_identifier,
            "year": year,
            "value": raw_record.get("value"),
            "source_url": WORLD_BANK_SOURCE_URL,
        }
