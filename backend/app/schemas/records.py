from datetime import datetime
from decimal import Decimal, InvalidOperation
from typing import Literal

from pydantic import (
    AnyHttpUrl,
    BaseModel,
    ConfigDict,
    Field,
    field_validator,
    model_validator,
)

WORLD_BANK_SOURCE_ID = "worldbank-bd-inflation"
WORLD_BANK_SOURCE_URL = (
    "https://api.worldbank.org/v2/country/BGD/indicator/FP.CPI.TOTL.ZG"
)


class WorldBankInflationRecord(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    source_id: Literal["worldbank-bd-inflation"] = WORLD_BANK_SOURCE_ID
    external_record_id: str = Field(min_length=1, max_length=200)
    country_code: Literal["BGD"] = "BGD"
    indicator_code: Literal["FP.CPI.TOTL.ZG"] = "FP.CPI.TOTL.ZG"
    year: int = Field(ge=1900, le=2100)
    value: Decimal = Field(max_digits=38, decimal_places=18)
    source_url: AnyHttpUrl
    observed_at: datetime

    @field_validator("value", mode="before")
    @classmethod
    def parse_numeric_value(cls, value: object) -> Decimal:
        if isinstance(value, bool) or value is None:
            raise ValueError("value must be numeric")
        try:
            result = value if isinstance(value, Decimal) else Decimal(str(value))
        except (InvalidOperation, ValueError):
            raise ValueError("value must be numeric") from None
        if not result.is_finite():
            raise ValueError("value must be finite")
        return result

    @field_validator("observed_at")
    @classmethod
    def require_timezone(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("observed_at must include a timezone")
        return value

    @model_validator(mode="after")
    def validate_external_identifier(self) -> "WorldBankInflationRecord":
        expected = (
            f"{self.source_id}:{self.country_code}:"
            f"{self.indicator_code}:{self.year}"
        )
        if self.external_record_id != expected:
            raise ValueError("external_record_id does not match the observation")
        if str(self.source_url) != WORLD_BANK_SOURCE_URL:
            raise ValueError("source_url does not match the registered source")
        return self


class WorldBankIndicatorRecord(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    source_id: str = Field(min_length=1, max_length=120)
    external_record_id: str = Field(min_length=1, max_length=200)
    country_code: Literal["BGD"] = "BGD"
    indicator_code: str = Field(pattern=r"^[A-Z0-9.]+$", min_length=1, max_length=30)
    unit: str = Field(min_length=1, max_length=40)
    year: int = Field(ge=1900, le=2100)
    value: Decimal = Field(max_digits=38, decimal_places=18)
    source_url: AnyHttpUrl
    observed_at: datetime

    @field_validator("value", mode="before")
    @classmethod
    def parse_numeric_value(cls, value: object) -> Decimal:
        if isinstance(value, bool) or value is None:
            raise ValueError("value must be numeric")
        try:
            result = value if isinstance(value, Decimal) else Decimal(str(value))
        except (InvalidOperation, ValueError):
            raise ValueError("value must be numeric") from None
        if not result.is_finite():
            raise ValueError("value must be finite")
        return result

    @field_validator("observed_at")
    @classmethod
    def require_timezone(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("observed_at must include a timezone")
        return value

    @model_validator(mode="after")
    def validate_source_identity(self) -> "WorldBankIndicatorRecord":
        expected = (
            f"{self.source_id}:{self.country_code}:"
            f"{self.indicator_code}:{self.year}"
        )
        expected_url = (
            "https://api.worldbank.org/v2/country/BGD/indicator/"
            f"{self.indicator_code}"
        )
        if self.external_record_id != expected:
            raise ValueError("external_record_id does not match the observation")
        if str(self.source_url) != expected_url:
            raise ValueError("source_url does not match the indicator")
        return self
