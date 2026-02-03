"""
Temporal Reasoning Tools — versioned state tracking, timeline queries,
scenario management, and trend prediction.
"""

import hashlib
import json
import sqlite3
import time
from enum import Enum
from pathlib import Path
from typing import Optional

DB_PATH = Path(__file__).parent / "gps.db"


class StateType(Enum):
    FACT = "fact"
    HISTORICAL = "historical"
    HYPOTHETICAL = "hypothetical"
    PREDICTION = "prediction"


_initialized = False


def _init_tables():
    global _initialized
    if _initialized:
        return
    conn = sqlite3.connect(DB_PATH)
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS temporal_snapshots (
            id TEXT PRIMARY KEY,
            entity_type TEXT NOT NULL,
            entity_id TEXT NOT NULL,
            state_type TEXT NOT NULL,
            snapshot_data TEXT NOT NULL,
            confidence REAL DEFAULT 1.0,
            source TEXT DEFAULT 'system',
            valid_from REAL,
            valid_to REAL,
            created_at REAL NOT NULL
        );
        CREATE TABLE IF NOT EXISTS temporal_scenarios (
            id TEXT PRIMARY KEY,
            name TEXT NOT NULL,
            base_snapshot_id TEXT,
            changes TEXT,
            outcome_analysis TEXT,
            created_at REAL NOT NULL,
            FOREIGN KEY (base_snapshot_id) REFERENCES temporal_snapshots(id)
        );
        CREATE INDEX IF NOT EXISTS idx_temporal_entity ON temporal_snapshots(entity_type, entity_id);
        CREATE INDEX IF NOT EXISTS idx_temporal_valid ON temporal_snapshots(valid_from, valid_to);
        CREATE INDEX IF NOT EXISTS idx_temporal_type ON temporal_snapshots(state_type);
    """)
    conn.commit()
    conn.close()
    _initialized = True


def _conn():
    _init_tables()
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def _gen_id(prefix=""):
    return prefix + hashlib.sha256(f"{prefix}{time.time()}".encode()).hexdigest()[:12]


def record_state(entity_type: str, entity_id: str, state_type: str, data: str,
                 confidence: float = 1.0, source: str = "system",
                 valid_from: float = 0.0, valid_to: float = 0.0) -> str:
    """Store a versioned state snapshot for an entity. state_type: fact/historical/hypothetical/prediction. Returns snapshot ID."""
    sid = _gen_id("snap_")
    now = time.time()
    vf = valid_from if valid_from > 0 else now
    vt = valid_to if valid_to > 0 else None
    if state_type == "fact":
        c = _conn()
        c.execute("UPDATE temporal_snapshots SET valid_to = ? WHERE entity_type = ? AND entity_id = ? AND state_type = 'fact' AND valid_to IS NULL", (now, entity_type, entity_id))
        c.commit()
        c.close()
    c = _conn()
    c.execute("INSERT INTO temporal_snapshots (id, entity_type, entity_id, state_type, snapshot_data, confidence, source, valid_from, valid_to, created_at) VALUES (?,?,?,?,?,?,?,?,?,?)",
              (sid, entity_type, entity_id, state_type, data, confidence, source, vf, vt, now))
    c.commit()
    c.close()
    return json.dumps({"snapshot_id": sid})


def query_timeline(entity_type: str, entity_id: str, time_from: float = 0.0,
                   time_to: float = 0.0, state_type: str = "") -> str:
    """Get state history for an entity over a time range."""
    c = _conn()
    q = "SELECT * FROM temporal_snapshots WHERE entity_type = ? AND entity_id = ?"
    params = [entity_type, entity_id]
    if time_from > 0:
        q += " AND (valid_to IS NULL OR valid_to >= ?)"
        params.append(time_from)
    if time_to > 0:
        q += " AND valid_from <= ?"
        params.append(time_to)
    if state_type:
        q += " AND state_type = ?"
        params.append(state_type)
    q += " ORDER BY valid_from ASC"
    rows = c.execute(q, params).fetchall()
    c.close()
    snaps = [{"id": r["id"], "state_type": r["state_type"], "data": r["snapshot_data"],
              "confidence": r["confidence"], "valid_from": r["valid_from"],
              "valid_to": r["valid_to"]} for r in rows]
    return json.dumps({"snapshots": snaps, "count": len(snaps)})


def get_current_state(entity_type: str, entity_id: str) -> str:
    """Get the latest FACT state for an entity (no valid_to = still current)."""
    c = _conn()
    row = c.execute("SELECT * FROM temporal_snapshots WHERE entity_type = ? AND entity_id = ? AND state_type = 'fact' AND valid_to IS NULL ORDER BY valid_from DESC LIMIT 1",
                    (entity_type, entity_id)).fetchone()
    c.close()
    if not row:
        return json.dumps({"state": None})
    return json.dumps({"state": {"id": row["id"], "data": row["snapshot_data"], "confidence": row["confidence"], "valid_from": row["valid_from"]}})


def create_scenario(name: str, base_snapshot_id: str = "", changes: str = "{}") -> str:
    """Fork a hypothetical scenario from a base snapshot."""
    sid = _gen_id("scen_")
    c = _conn()
    c.execute("INSERT INTO temporal_scenarios (id, name, base_snapshot_id, changes, outcome_analysis, created_at) VALUES (?,?,?,?,NULL,?)",
              (sid, name, base_snapshot_id or None, changes, time.time()))
    c.commit()
    c.close()
    return json.dumps({"scenario_id": sid})


def compare_scenarios(scenario_ids: str) -> str:
    """Compare scenarios side by side. scenario_ids is comma-separated."""
    ids = [s.strip() for s in scenario_ids.split(",") if s.strip()]
    c = _conn()
    results = []
    for sid in ids:
        row = c.execute("SELECT * FROM temporal_scenarios WHERE id = ?", (sid,)).fetchone()
        if row:
            base_data = None
            if row["base_snapshot_id"]:
                snap = c.execute("SELECT snapshot_data FROM temporal_snapshots WHERE id = ?", (row["base_snapshot_id"],)).fetchone()
                if snap:
                    base_data = snap["snapshot_data"]
            results.append({"id": row["id"], "name": row["name"], "base_data": base_data, "changes": row["changes"], "outcome": row["outcome_analysis"]})
    c.close()
    return json.dumps({"scenarios": results, "count": len(results)})


def predict_trend(entity_type: str, entity_id: str, data_points: str, horizon: str = "30d") -> str:
    """Record a prediction about future state (LLM does analysis, this stores it)."""
    return record_state(entity_type, entity_id, "prediction",
                        json.dumps({"data_points": data_points, "horizon": horizon}),
                        confidence=0.6, source="prediction_engine")


def get_temporal_tools() -> list:
    """Return temporal tool functions for registration."""
    return [record_state, query_timeline, get_current_state, create_scenario, compare_scenarios, predict_trend]
