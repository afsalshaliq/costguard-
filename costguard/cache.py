import os
import sqlite3
import time
from pathlib import Path


SCHEMA = """CREATE TABLE IF NOT EXISTS pricing_cache (
    sku TEXT NOT NULL,
    region TEXT NOT NULL,
    currency TEXT NOT NULL DEFAULT 'USD',
    hourly_rate REAL NOT NULL,
    cached_at INTEGER NOT NULL,
    PRIMARY KEY (sku, region, currency)
)"""


class PricingCache:
    def __init__(self, path="./pricing_cache.db", ttl_days=None, warnings=None):
        self.path = Path(path)
        self.ttl_days = ttl_days
        self.warnings = warnings if warnings is not None else []
        self.cache_hits = 0
        self.api_lookups = 0
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.connection = None
        try:
            self.connection = sqlite3.connect(self.path)
            self.connection.execute(SCHEMA)
            self.connection.commit()
        except sqlite3.DatabaseError as exc:
            if self.connection:
                self.connection.close()
            self.connection = None
            try:
                os.remove(self.path)
                self.warnings.append(f"[WARN] Corrupt cache database recreated: {exc}")
            except OSError:
                raise
            self.connection = sqlite3.connect(self.path)
            self.connection.execute(SCHEMA)
            self.connection.commit()

    def get(self, sku, region, currency):
        row = self.connection.execute(
            "SELECT hourly_rate, cached_at FROM pricing_cache WHERE sku=? AND region=? AND currency=?",
            (sku, region, currency),
        ).fetchone()
        if row is None:
            return None
        rate, cached_at = row
        if self.ttl_days is not None and time.time() - cached_at > self.ttl_days * 86400:
            return None
        self.cache_hits += 1
        return rate

    def put(self, sku, region, currency, hourly_rate):
        self.connection.execute(
            "INSERT OR REPLACE INTO pricing_cache (sku, region, currency, hourly_rate, cached_at) VALUES (?, ?, ?, ?, ?)",
            (sku, region, currency, float(hourly_rate), int(time.time())),
        )
        self.connection.commit()

    def clear(self):
        self.connection.execute("DELETE FROM pricing_cache")
        self.connection.commit()

    def close(self):
        if self.connection is not None:
            self.connection.close()
            self.connection = None
