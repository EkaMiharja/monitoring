"""Persistent storage for QoS samples received from remote VM agents."""
from __future__ import annotations

import math
import sqlite3
from contextlib import closing
from datetime import datetime, timezone, timedelta
from pathlib import Path


FIELD_ALIASES = {
    "delay_ms": ("delay_ms", "delay", "latency_ms"),
    "packet_loss_percent": ("packet_loss_percent", "packet_loss", "loss_percent"),
    "throughput_mbps": ("throughput_mbps", "throughput", "bandwidth_mbps"),
    "jitter_ms": ("jitter_ms", "jitter"),
    "cpu_percent": ("cpu_percent", "cpu", "cpu_usage"),
    "memory_percent": ("memory_percent", "mem_percent", "memory", "mem", "memory_usage"),
}

LIMITS = {
    "delay_ms": (0.0, 3_600_000.0),
    "packet_loss_percent": (0.0, 100.0),
    "throughput_mbps": (0.0, 1_000_000.0),
    "jitter_ms": (0.0, 3_600_000.0),
    "cpu_percent": (0.0, 100.0),
    "memory_percent": (0.0, 100.0),
}

QOS_KEYS = {
    "delay": "delay_ms",
    "jitter": "jitter_ms",
    "packet_loss": "packet_loss_percent",
    "throughput": "throughput_mbps",
}

RESOURCE_KEYS = {"cpu": "cpu_percent", "memory": "memory_percent"}


class RemoteMetricsStore:
    """SQLite-backed store. A new connection is opened for each operation."""

    def __init__(self, db_path=None):
        if db_path:
            self.path = Path(db_path)
        else:
            self.path = Path(__file__).resolve().parents[1] / "instance" / "remote_metrics.db"
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._ensure_schema()

    def _connect(self):
        connection = sqlite3.connect(str(self.path), timeout=5)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA busy_timeout=5000")
        return connection

    def _ensure_schema(self):
        with closing(self._connect()) as connection, connection:
            connection.execute("PRAGMA journal_mode=WAL")
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS remote_qos_samples (
                    host TEXT NOT NULL,
                    timestamp TEXT NOT NULL,
                    timestamp_epoch REAL NOT NULL,
                    delay_ms REAL,
                    packet_loss_percent REAL,
                    throughput_mbps REAL,
                    jitter_ms REAL,
                    cpu_percent REAL,
                    memory_percent REAL,
                    PRIMARY KEY (host, timestamp)
                )
                """
            )
            connection.execute(
                "CREATE INDEX IF NOT EXISTS idx_remote_qos_host_epoch "
                "ON remote_qos_samples(host, timestamp_epoch)"
            )

    @staticmethod
    def _normalise_timestamp(value):
        if value is None or value == "":
            parsed = datetime.now(timezone.utc)
        else:
            if not isinstance(value, str) or len(value) > 80:
                raise ValueError("timestamp harus berupa string ISO-8601 yang valid.")
            try:
                parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
            except ValueError as exc:
                raise ValueError("timestamp harus berupa string ISO-8601 yang valid.") from exc
            if parsed.tzinfo is None:
                parsed = parsed.replace(tzinfo=timezone.utc)
            parsed = parsed.astimezone(timezone.utc)
        return parsed.isoformat(timespec="milliseconds"), parsed.timestamp()

    @staticmethod
    def _number(value, key):
        if value is None:
            return None
        if isinstance(value, bool):
            raise ValueError(f"Field {key} harus berupa angka.")
        try:
            number = float(value)
        except (TypeError, ValueError) as exc:
            raise ValueError(f"Field {key} harus berupa angka.") from exc
        if not math.isfinite(number):
            raise ValueError(f"Field {key} harus berupa angka terbatas.")
        low, high = LIMITS[key]
        if number < low or number > high:
            raise ValueError(f"Field {key} di luar rentang {low} sampai {high}.")
        return round(number, 3)

    def add_sample(self, payload, host_id="qos-vm"):
        if not isinstance(payload, dict):
            raise ValueError("Body JSON harus berupa objek.")

        values_source = dict(payload)
        nested = payload.get("metrics")
        if isinstance(nested, dict):
            values_source.update(nested)

        values = {}
        for field, aliases in FIELD_ALIASES.items():
            raw_value = None
            for alias in aliases:
                if alias in values_source:
                    raw_value = values_source[alias]
                    break
            values[field] = self._number(raw_value, field)

        accepted = [key for key, value in values.items() if value is not None]
        if not accepted:
            raise ValueError("JSON tidak berisi metrik QoS atau resource yang dikenali.")

        timestamp, timestamp_epoch = self._normalise_timestamp(
            payload.get("timestamp") or payload.get("time")
        )
        host = str(host_id or "qos-vm").strip()[:100] or "qos-vm"
        fields = [
            "delay_ms", "packet_loss_percent", "throughput_mbps",
            "jitter_ms", "cpu_percent", "memory_percent",
        ]
        args = [host, timestamp, timestamp_epoch] + [values[field] for field in fields]
        update_clause = ", ".join(
            f"{field}=COALESCE(excluded.{field}, remote_qos_samples.{field})"
            for field in fields
        )
        with closing(self._connect()) as connection, connection:
            connection.execute(
                f"""
                INSERT INTO remote_qos_samples
                    (host, timestamp, timestamp_epoch, {', '.join(fields)})
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(host, timestamp) DO UPDATE SET
                    timestamp_epoch=excluded.timestamp_epoch, {update_clause}
                """,
                args,
            )
        return {
            "host": host,
            "timestamp": timestamp,
            "accepted_metrics": accepted,
        }

    def series(self, metric, host_id, window_seconds=300, max_points=120):
        if metric not in LIMITS:
            raise ValueError("Nama metrik tidak dikenal.")
        cutoff = datetime.now(timezone.utc).timestamp() - max(1, int(window_seconds))
        limit = max(1, min(int(max_points), 2000))
        with closing(self._connect()) as connection, connection:
            rows = connection.execute(
                f"""
                SELECT timestamp, {metric} AS value
                FROM remote_qos_samples
                WHERE host=? AND timestamp_epoch>=? AND {metric} IS NOT NULL
                ORDER BY timestamp_epoch DESC LIMIT ?
                """,
                (host_id, cutoff, limit),
            ).fetchall()
        rows.reverse()
        return [{"t": row["timestamp"], "value": round(float(row["value"]), 3)} for row in rows]

    def qos_series(self, host_id, window_seconds=300, max_points=120):
        return {
            key: self.series(field, host_id, window_seconds, max_points)
            for key, field in QOS_KEYS.items()
        }

    def resource_series(self, host_id, window_seconds=300, max_points=120):
        return {
            key: self.series(field, host_id, window_seconds, max_points)
            for key, field in RESOURCE_KEYS.items()
        }

    def latest(self, host_id):
        with closing(self._connect()) as connection, connection:
            row = connection.execute(
                """
                SELECT timestamp, delay_ms, packet_loss_percent, throughput_mbps,
                       jitter_ms, cpu_percent, memory_percent
                FROM remote_qos_samples WHERE host=?
                ORDER BY timestamp_epoch DESC LIMIT 1
                """,
                (host_id,),
            ).fetchone()
        return dict(row) if row else None
