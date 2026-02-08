import sqlite3
from pathlib import Path

SCHEMA = """
CREATE TABLE IF NOT EXISTS miner_snapshot (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  miner_id TEXT NOT NULL,
  ts INTEGER NOT NULL,

  hashrate_th REAL,
  best_diff REAL,
  best_session_diff REAL,

  pool TEXT,
  user TEXT,

  asic_temp REAL,
  vrm_temp REAL,

  volts REAL,
  amps REAL,
  watts REAL,

  frequency REAL,
  core_v REAL,

  shares_accepted INTEGER,
  shares_rejected INTEGER,
  error_pct REAL,

  uptime_s INTEGER,
  fan_rpm INTEGER,
  wifi_rssi INTEGER,

  status TEXT
);

CREATE INDEX IF NOT EXISTS idx_snapshot_miner_ts
ON miner_snapshot(miner_id, ts);
"""

MIGRATIONS = [
    ("ALTER TABLE miner_snapshot ADD COLUMN best_session_diff REAL", "best_session_diff"),
    ("ALTER TABLE miner_snapshot ADD COLUMN user TEXT", "user"),
    ("ALTER TABLE miner_snapshot ADD COLUMN frequency REAL", "frequency"),
    ("ALTER TABLE miner_snapshot ADD COLUMN core_v REAL", "core_v"),
    ("ALTER TABLE miner_snapshot ADD COLUMN shares_accepted INTEGER", "shares_accepted"),
    ("ALTER TABLE miner_snapshot ADD COLUMN shares_rejected INTEGER", "shares_rejected"),
    ("ALTER TABLE miner_snapshot ADD COLUMN error_pct REAL", "error_pct"),
    ("ALTER TABLE miner_snapshot ADD COLUMN uptime_s INTEGER", "uptime_s"),
    ("ALTER TABLE miner_snapshot ADD COLUMN fan_rpm INTEGER", "fan_rpm"),
    ("ALTER TABLE miner_snapshot ADD COLUMN wifi_rssi INTEGER", "wifi_rssi"),
    ("ALTER TABLE miner_snapshot ADD COLUMN pool TEXT", "pool"),
    ("ALTER TABLE miner_snapshot ADD COLUMN volts REAL", "volts"),
    ("ALTER TABLE miner_snapshot ADD COLUMN amps REAL", "amps"),
    ("ALTER TABLE miner_snapshot ADD COLUMN watts REAL", "watts"),
    ("ALTER TABLE miner_snapshot ADD COLUMN asic_temp REAL", "asic_temp"),
    ("ALTER TABLE miner_snapshot ADD COLUMN vrm_temp REAL", "vrm_temp"),
    ("ALTER TABLE miner_snapshot ADD COLUMN hashrate_th REAL", "hashrate_th"),
    ("ALTER TABLE miner_snapshot ADD COLUMN best_diff REAL", "best_diff"),
]

def connect(db_path: str) -> sqlite3.Connection:
    Path(db_path).parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db_path, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn

def _has_column(conn: sqlite3.Connection, table: str, col: str) -> bool:
    rows = conn.execute(f"PRAGMA table_info({table})").fetchall()
    return any(r["name"] == col for r in rows)

def init_db(conn: sqlite3.Connection) -> None:
    conn.executescript(SCHEMA)
    conn.commit()

    # migracje dla istniejącej bazy
    for sql, col in MIGRATIONS:
        try:
            if not _has_column(conn, "miner_snapshot", col):
                conn.execute(sql)
                conn.commit()
        except Exception:
            pass
