from datetime import datetime, timezone
from enum import Enum
from typing import Literal

from pydantic import BaseModel, Field, model_validator


class MarketKind(str, Enum):
    REAL = "real"
    OTC = "otc"
    UNKNOWN = "unknown"


class Tick(BaseModel):
    provider: str = Field(min_length=1)
    symbol: str = Field(min_length=1)
    market_kind: MarketKind = MarketKind.UNKNOWN
    price: float = Field(gt=0)
    timestamp: datetime
    received_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class Candle(BaseModel):
    provider: str = Field(min_length=1)
    symbol: str = Field(min_length=1)
    market_kind: MarketKind = MarketKind.UNKNOWN
    timeframe_seconds: int = Field(gt=0)
    timestamp: datetime
    open: float = Field(gt=0)
    high: float = Field(gt=0)
    low: float = Field(gt=0)
    close: float = Field(gt=0)
    volume: float | None = Field(default=None, ge=0)
    received_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    @model_validator(mode="after")
    def validate_ohlc(self):
        if self.high < max(self.open, self.close, self.low):
            raise ValueError("high must be >= open, close, and low")
        if self.low > min(self.open, self.close, self.high):
            raise ValueError("low must be <= open, close, and high")
        return self


class FeedHealth(BaseModel):
    provider: str
    status: Literal["healthy", "stale", "disabled", "error"]
    last_event_at: datetime | None = None
    age_seconds: float | None = None
    message: str | None = None


class SignalDecision(BaseModel):
    symbol: str
    decision: Literal["CALL", "PUT", "NO_TRADE"]
    expiry_seconds: int | None = None
    confidence: float = Field(ge=0, le=1)
    rationale: list[str] = Field(default_factory=list)
    generated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
