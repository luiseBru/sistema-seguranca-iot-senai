"""Persistencia SQLite para leituras e alertas do sistema."""

from __future__ import annotations

import sqlite3
import threading
from datetime import datetime, timezone
from pathlib import Path


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


class Database:
    """Pequena camada de acesso ao SQLite, segura para as threads usadas pelo MQTT."""

    def __init__(self, path: str | Path):
        self.path = Path(path)
        self._connection: sqlite3.Connection | None = None
        self._lock = threading.RLock()

    def connect(self) -> None:
        with self._lock:
            if self._connection is not None:
                return
            self.path.parent.mkdir(parents=True, exist_ok=True)
            connection = sqlite3.connect(self.path, check_same_thread=False)
            connection.row_factory = sqlite3.Row
            connection.execute("PRAGMA journal_mode=WAL")
            connection.execute("PRAGMA foreign_keys=ON")
            connection.execute("PRAGMA busy_timeout=5000")
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS readings (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    device_id TEXT NOT NULL,
                    measured_at TEXT NOT NULL,
                    received_at TEXT NOT NULL,
                    distance_cm REAL NOT NULL,
                    situation TEXT NOT NULL CHECK (situation IN ('NORMAL', 'ALERTA')),
                    source TEXT NOT NULL,
                    sequence_number INTEGER
                );

                CREATE INDEX IF NOT EXISTS idx_readings_device_time
                    ON readings(device_id, measured_at DESC);

                CREATE TABLE IF NOT EXISTS alerts (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    device_id TEXT NOT NULL,
                    started_at TEXT NOT NULL,
                    ended_at TEXT,
                    min_distance_cm REAL NOT NULL,
                    last_distance_cm REAL NOT NULL,
                    acknowledged_at TEXT,
                    acknowledged_by TEXT
                );

                CREATE INDEX IF NOT EXISTS idx_alerts_device_time
                    ON alerts(device_id, started_at DESC);
                """
            )
            connection.commit()
            self._connection = connection

    def close(self) -> None:
        with self._lock:
            if self._connection is not None:
                self._connection.close()
                self._connection = None

    def _get_connection(self) -> sqlite3.Connection:
        if self._connection is None:
            self.connect()
        assert self._connection is not None
        return self._connection

    def record_reading(
        self,
        *,
        device_id: str,
        measured_at: str,
        distance_cm: float,
        situation: str,
        source: str,
        sequence_number: int | None = None,
    ) -> int:
        received_at = utc_now()
        with self._lock:
            connection = self._get_connection()
            cursor = connection.execute(
                """
                INSERT INTO readings (
                    device_id, measured_at, received_at, distance_cm,
                    situation, source, sequence_number
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    device_id,
                    measured_at,
                    received_at,
                    distance_cm,
                    situation,
                    source,
                    sequence_number,
                ),
            )
            self._update_alert(
                connection,
                device_id=device_id,
                measured_at=measured_at,
                distance_cm=distance_cm,
                situation=situation,
            )
            connection.commit()
            return int(cursor.lastrowid)

    @staticmethod
    def _update_alert(
        connection: sqlite3.Connection,
        *,
        device_id: str,
        measured_at: str,
        distance_cm: float,
        situation: str,
    ) -> None:
        current = connection.execute(
            """
            SELECT id, min_distance_cm
            FROM alerts
            WHERE device_id = ? AND ended_at IS NULL
            ORDER BY id DESC
            LIMIT 1
            """,
            (device_id,),
        ).fetchone()

        if situation == "ALERTA":
            if current is None:
                connection.execute(
                    """
                    INSERT INTO alerts (
                        device_id, started_at, min_distance_cm, last_distance_cm
                    ) VALUES (?, ?, ?, ?)
                    """,
                    (device_id, measured_at, distance_cm, distance_cm),
                )
            else:
                connection.execute(
                    """
                    UPDATE alerts
                    SET min_distance_cm = ?, last_distance_cm = ?
                    WHERE id = ?
                    """,
                    (min(float(current["min_distance_cm"]), distance_cm), distance_cm, current["id"]),
                )
        elif current is not None:
            connection.execute(
                """
                UPDATE alerts
                SET ended_at = ?, last_distance_cm = ?
                WHERE id = ?
                """,
                (measured_at, distance_cm, current["id"]),
            )

    def get_readings(self, *, limit: int = 120, device_id: str | None = None) -> list[dict]:
        limit = max(1, min(limit, 1000))
        with self._lock:
            connection = self._get_connection()
            if device_id:
                rows = connection.execute(
                    """
                    SELECT * FROM readings
                    WHERE device_id = ?
                    ORDER BY id DESC LIMIT ?
                    """,
                    (device_id, limit),
                ).fetchall()
            else:
                rows = connection.execute(
                    "SELECT * FROM readings ORDER BY id DESC LIMIT ?",
                    (limit,),
                ).fetchall()
        return [dict(row) for row in reversed(rows)]

    def get_alerts(self, *, limit: int = 50, device_id: str | None = None) -> list[dict]:
        limit = max(1, min(limit, 500))
        with self._lock:
            connection = self._get_connection()
            if device_id:
                rows = connection.execute(
                    """
                    SELECT * FROM alerts
                    WHERE device_id = ?
                    ORDER BY id DESC LIMIT ?
                    """,
                    (device_id, limit),
                ).fetchall()
            else:
                rows = connection.execute(
                    "SELECT * FROM alerts ORDER BY id DESC LIMIT ?",
                    (limit,),
                ).fetchall()
        return [dict(row) for row in rows]

    def acknowledge_alert(self, alert_id: int, operator: str) -> dict | None:
        acknowledged_at = utc_now()
        with self._lock:
            connection = self._get_connection()
            cursor = connection.execute(
                """
                UPDATE alerts
                SET acknowledged_at = ?, acknowledged_by = ?
                WHERE id = ?
                """,
                (acknowledged_at, operator, alert_id),
            )
            if cursor.rowcount == 0:
                return None
            connection.commit()
            row = connection.execute("SELECT * FROM alerts WHERE id = ?", (alert_id,)).fetchone()
        return dict(row) if row else None
