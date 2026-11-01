import json
import logging
import time
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from decimal import Decimal
from email.utils import parsedate_to_datetime
from typing import Any

import httpx

from backend.app.collectors.base import Collector, RecordNormalizationError
from backend.app.schemas.records import (
    WORLD_BANK_SOURCE_ID,
    WORLD_BANK_SOURCE_URL,
    WorldBankIndicatorRecord,
    WorldBankInflationRecord,
)

LOGGER = logging.getLogger(__name__)
REQUEST_TIMEOUT_SECONDS = 20.0
RETRY_ATTEMPTS = 3
MAX_PAGES = 100
PAGE_SIZE = 1000
RETRYABLE_STATUS_CODES = frozenset({429, 500, 502, 503, 504})
WORLD_BANK_ROOT = "https://api.worldbank.org/v2/country/BGD/indicator/"


@dataclass(frozen=True)
class IndicatorSpec:
    source_id: str
    name: str
    indicator_code: str
    category: str
    unit: str
    priority: int
    base_interval_seconds: int = 30 * 24 * 60 * 60
    minimum_interval_seconds: int = 7 * 24 * 60 * 60
    maximum_interval_seconds: int = 90 * 24 * 60 * 60

    @property
    def endpoint(self) -> str:
        return WORLD_BANK_ROOT + self.indicator_code


INDICATOR_SPECS: tuple[IndicatorSpec, ...] = (
    IndicatorSpec(
        source_id=WORLD_BANK_SOURCE_ID,
        name="World Bank Bangladesh Inflation",
        indicator_code="FP.CPI.TOTL.ZG",
        category="economic_indicators",
        unit="percent",
        priority=8,
    ),
    IndicatorSpec(
        source_id="worldbank-bd-gdp-growth",
        name="World Bank Bangladesh GDP Growth",
        indicator_code="NY.GDP.MKTP.KD.ZG",
        category="economic_indicators",
        unit="percent",
        priority=6,
    ),
    IndicatorSpec(
        source_id="worldbank-bd-population",
        name="World Bank Bangladesh Population",
        indicator_code="SP.POP.TOTL",
        category="demographics",
        unit="people",
        priority=4,
    ),
)
INDICATORS_BY_SOURCE = {spec.source_id: spec for spec in INDICATOR_SPECS}


class CollectorError(RuntimeError):
    """A sanitized upstream failure with a stable recovery category."""

    def __init__(
        self,
        message: str,
        category: str = "upstream_failure",
        retry_after_seconds: float | None = None,
    ) -> None:
        self.category = category
        self.retry_after_seconds = retry_after_seconds
        super().__init__(message)


class WorldBankIndicatorCollector(Collector):
    category = "economic_indicators"
    record_model = WorldBankIndicatorRecord

    def __init__(
        self,
        spec: IndicatorSpec,
        client: httpx.Client | None = None,
        retry_delay: float = 0.5,
    ) -> None:
        self.spec = spec
        self.source_id = spec.source_id
        self.category = spec.category
        self._owns_client = client is None
        self._client = client or httpx.Client(
            timeout=httpx.Timeout(REQUEST_TIMEOUT_SECONDS),
            follow_redirects=False,
        )
        self._retry_delay = retry_delay

    def close(self) -> None:
        if self._owns_client:
            self._client.close()

    @staticmethod
    def _retry_after(response: httpx.Response) -> float | None:
        value = response.headers.get("Retry-After")
        if value is None:
            return None
        try:
            return max(0.0, min(float(value), 6 * 60 * 60))
        except ValueError:
            try:
                date = parsedate_to_datetime(value)
                return max(0.0, min(date.timestamp() - time.time(), 6 * 60 * 60))
            except (TypeError, ValueError, OverflowError):
                return None

    def _request_page(self, page: int) -> tuple[dict[str, Any], list[Any]]:
        for attempt in range(RETRY_ATTEMPTS):
            try:
                response = self._client.get(
                    self.spec.endpoint,
                    params={
                        "format": "json",
                        "per_page": PAGE_SIZE,
                        "page": page,
                    },
                )
                if response.status_code in RETRYABLE_STATUS_CODES:
                    retry_after = self._retry_after(response)
                    if attempt + 1 < RETRY_ATTEMPTS:
                        delay = retry_after if retry_after is not None else self._retry_delay * (2**attempt)
                        time.sleep(min(delay, 30))
                        continue
                    category = "rate_limited" if response.status_code == 429 else "upstream_server_error"
                    raise CollectorError(
                        f"World Bank request failed with HTTP {response.status_code}.",
                        category,
                        retry_after,
                    )
                if response.status_code in {401, 403}:
                    raise CollectorError(
                        f"World Bank request was rejected with HTTP {response.status_code}.",
                        "permission_denied",
                    )
                if response.status_code == 404:
                    raise CollectorError("World Bank indicator endpoint was not found.", "endpoint_missing")
                response.raise_for_status()
                payload = json.loads(response.content, parse_float=Decimal)
                return self._parse_page(payload, page)
            except CollectorError:
                raise
            except httpx.HTTPStatusError as exc:
                raise CollectorError(
                    f"World Bank request failed with HTTP {exc.response.status_code}.",
                    "upstream_http_error",
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
                category = "temporary_network_failure"
                raise CollectorError(
                    f"World Bank request failed ({type(exc).__name__}).",
                    category,
                ) from None
            except (json.JSONDecodeError, UnicodeDecodeError, TypeError) as exc:
                raise CollectorError(
                    f"World Bank returned invalid JSON ({type(exc).__name__}).",
                    "unexpected_response",
                ) from None
        raise CollectorError("World Bank request exhausted its retry limit.")

    @staticmethod
    def _parse_page(payload: object, requested_page: int) -> tuple[dict[str, Any], list[Any]]:
        if not isinstance(payload, list) or len(payload) != 2:
            raise CollectorError(
                "World Bank response has an unsupported format.",
                "unexpected_response",
            )
        metadata, records = payload
        if not isinstance(metadata, dict):
            raise CollectorError("World Bank response metadata is malformed.", "unexpected_response")
        if not isinstance(records, list):
            total = metadata.get("total")
            if records is None and total == 0:
                records = []
            else:
                raise CollectorError("World Bank response records are malformed.", "unexpected_response")
        if any(not isinstance(record, Mapping) for record in records):
            raise CollectorError("World Bank response contains a malformed record.", "unexpected_response")
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
            raise CollectorError("World Bank pagination metadata is invalid.", "unexpected_response")
        return metadata, records

    def fetch_records(self) -> list[Mapping[str, Any]]:
        metadata, records = self._request_page(1)
        total_pages = metadata["pages"]
        if total_pages == 0:
            return []
        results = [record for record in records if record.get("value") is not None]
        for page in range(2, total_pages + 1):
            _, page_records = self._request_page(page)
            results.extend(record for record in page_records if record.get("value") is not None)
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
        if not isinstance(country_code, str) or country_code != "BGD":
            raise RecordNormalizationError("country_code")
        if not isinstance(country_identifier, str) or country_identifier != "BD":
            raise RecordNormalizationError("country_identifier")
        if (
            not isinstance(indicator_identifier, str)
            or indicator_identifier != self.spec.indicator_code
        ):
            raise RecordNormalizationError("indicator_identifier")
        result: dict[str, Any] = {
            "source_id": self.source_id,
            "external_record_id": (
                f"{self.source_id}:{country_code}:"
                f"{indicator_identifier}:{year}"
            ),
            "country_code": country_code,
            "indicator_code": indicator_identifier,
            "year": year,
            "value": raw_record.get("value"),
            "source_url": self.spec.endpoint,
        }
        if self.spec.source_id != WORLD_BANK_SOURCE_ID:
            result["unit"] = self.spec.unit
        return result


class WorldBankInflationCollector(WorldBankIndicatorCollector):
    source_id = WORLD_BANK_SOURCE_ID
    category = "economic_indicators"
    record_model = WorldBankInflationRecord

    def __init__(
        self,
        client: httpx.Client | None = None,
        retry_delay: float = 0.5,
    ) -> None:
        super().__init__(
            INDICATORS_BY_SOURCE[WORLD_BANK_SOURCE_ID],
            client=client,
            retry_delay=retry_delay,
        )


def create_world_bank_collector(source_id: str) -> WorldBankIndicatorCollector:
    spec = INDICATORS_BY_SOURCE.get(source_id)
    if spec is None:
        raise ValueError("Source does not have an approved World Bank collector.")
    if source_id == WORLD_BANK_SOURCE_ID:
        return WorldBankInflationCollector()
    return WorldBankIndicatorCollector(spec)


def register_world_bank_sources(session: Any, now: Any) -> None:
    from sqlalchemy import select

    from backend.app.db.models import Source, SourceSchedule

    for spec in INDICATOR_SPECS:
        source = session.scalar(
            select(Source).where(Source.source_key == spec.source_id).with_for_update()
        )
        if source is None:
            source = Source(
                source_key=spec.source_id,
                name=spec.name,
                source_type="api",
                official_url=spec.endpoint,
                category=spec.category,
                collection_config={
                    "provider": "World Bank",
                    "indicator_code": spec.indicator_code,
                    "country_code": "BGD",
                    "unit": spec.unit,
                },
                licensing_metadata={
                    "source": "World Bank Open Data",
                    "official_api": True,
                },
                enabled=True,
            )
            session.add(source)
            session.flush()
        schedule = session.get(SourceSchedule, source.id)
        if schedule is None:
            session.add(
                SourceSchedule(
                    source_id=source.id,
                    mode="adaptive",
                    enabled=True,
                    base_interval_seconds=spec.base_interval_seconds,
                    minimum_interval_seconds=spec.minimum_interval_seconds,
                    maximum_interval_seconds=spec.maximum_interval_seconds,
                    maximum_retries=5,
                    priority=spec.priority,
                    next_due_at=now,
                    health_status="unknown",
                )
            )
