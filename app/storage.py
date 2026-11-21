from __future__ import annotations

import json
import os
import sqlite3
from pathlib import Path
from typing import Any

from app.feeds.normalization import candle_timestamp, parse_timestamp


class CandleStore:
    """Small local SQLite OHLC cache; no paid database service required."""

    def __init__(self, path: str | None = None):
        self.path = path or os.getenv("BINARYAI_DB_PATH", "data/market.db")
        if self.path != ":memory:":
            Path(self.path).parent.mkdir(parents=True, exist_ok=True)
        self._initialize()

    def _connect(self):
        connection = sqlite3.connect(self.path, timeout=15)
        connection.row_factory = sqlite3.Row
        return connection

    def _initialize(self):
        with self._connect() as db:
            db.execute("PRAGMA journal_mode=WAL")
            db.execute("""
                CREATE TABLE IF NOT EXISTS candles (
                    id INTEGER PRIMARY KEY,
                    provider TEXT NOT NULL,
                    symbol TEXT NOT NULL,
                    interval TEXT NOT NULL,
                    timestamp_utc TEXT NOT NULL,
                    payload TEXT NOT NULL,
                    stored_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    UNIQUE(provider, symbol, interval, timestamp_utc)
                )
            """)
            db.execute("""
                CREATE INDEX IF NOT EXISTS idx_candles_lookup
                ON candles(provider, symbol, interval, timestamp_utc)
            """)

    @staticmethod
    def _timestamp(row: dict[str, Any]) -> str | None:
        parsed = candle_timestamp(row)
        return parsed.isoformat() if parsed else None

    def upsert(self, provider: str, symbol: str, interval: str,
               candles: list[dict[str, Any]]) -> dict[str, int]:
        inserted = updated = skipped = 0
        with self._connect() as db:
            for candle in candles:
                stamp = self._timestamp(candle)
                if not stamp:
                    skipped += 1
                    continue
                cursor = db.execute("""
                    INSERT INTO candles(provider, symbol, interval, timestamp_utc, payload)
                    VALUES (?, ?, ?, ?, ?)
                    ON CONFLICT(provider, symbol, interval, timestamp_utc)
                    DO UPDATE SET payload=excluded.payload, stored_at=CURRENT_TIMESTAMP
                """, (provider, symbol.upper(), interval, stamp,
                      json.dumps(candle, separators=(",", ":"), default=str)))
                if cursor.rowcount:
                    # SQLite reports one affected row for both insert and update;
                    # count as stored, not as a unique new market event.
                    inserted += 1
        return {"stored": inserted, "skipped_invalid_timestamp": skipped}

    def get(self, provider: str, symbol: str, interval: str,
            limit: int = 500, since: str | None = None) -> list[dict[str, Any]]:
        query = """SELECT payload FROM candles
                   WHERE provider=? AND symbol=? AND interval=?"""
        params: list[Any] = [provider, symbol.upper(), interval]
        if since:
            parsed = parse_timestamp(since)
            if not parsed:
                raise ValueError("since must be an ISO-8601 timestamp")
            query += " AND timestamp_utc >= ?"
            params.append(parsed.isoformat())
        query += " ORDER BY timestamp_utc DESC LIMIT ?"
        params.append(min(max(limit, 1), 10000))
        with self._connect() as db:
            rows = db.execute(query, params).fetchall()
        return [json.loads(row["payload"]) for row in reversed(rows)]

    def count(self, provider: str | None = None) -> int:
        with self._connect() as db:
            if provider:
                row = db.execute("SELECT COUNT(*) AS n FROM candles WHERE provider=?", (provider,)).fetchone()
            else:
                row = db.execute("SELECT COUNT(*) AS n FROM candles").fetchone()
        return int(row["n"])
