//! Episodic Memory - SQLite-backed with importance decay

use std::collections::HashMap;
use std::sync::Arc;
use chrono::{Duration, Utc};
use parking_lot::Mutex;
use pyo3::prelude::*;
use rusqlite::{params, Connection};
use serde::{Deserialize, Serialize};
use thiserror::Error;
use uuid::Uuid;

const DEFAULT_DECAY_RATE: f64 = 0.05;
const MIN_IMPORTANCE_THRESHOLD: f64 = 0.1;
const DEFAULT_MIN_AGE_DAYS: u64 = 30;

#[derive(Debug, Error)]
pub enum EpisodicMemoryError {
    #[error("Database error: {0}")]
    DatabaseError(#[from] rusqlite::Error),
    #[error("JSON error: {0}")]
    JsonError(#[from] serde_json::Error),
    #[error("Not found: {0}")]
    NotFound(String),
}

impl From<EpisodicMemoryError> for PyErr {
    fn from(err: EpisodicMemoryError) -> PyErr {
        pyo3::exceptions::PyRuntimeError::new_err(err.to_string())
    }
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct EpisodicEntry {
    pub id: String,
    pub content: String,
    pub memory_type: String,
    pub domain: Option<String>,
    pub importance: f64,
    pub access_count: u64,
    pub created_at: String,
}

struct EpisodicMemoryInner {
    conn: Connection,
}

#[pyclass]
pub struct EpisodicMemory {
    inner: Arc<Mutex<EpisodicMemoryInner>>,
}

impl EpisodicMemory {
    fn init_schema(conn: &Connection) -> Result<(), EpisodicMemoryError> {
        conn.execute_batch(r#"
            CREATE TABLE IF NOT EXISTS episodic_memories (
                id TEXT PRIMARY KEY, content TEXT NOT NULL, memory_type TEXT NOT NULL,
                domain TEXT, importance REAL NOT NULL DEFAULT 1.0, access_count INTEGER NOT NULL DEFAULT 0,
                last_accessed TEXT NOT NULL, created_at TEXT NOT NULL, updated_at TEXT NOT NULL,
                entity_type TEXT, entity_id TEXT, supersedes TEXT, superseded_by TEXT, metadata TEXT NOT NULL DEFAULT '{}'
            );
            CREATE INDEX IF NOT EXISTS idx_episodic_memory_type ON episodic_memories(memory_type);
            CREATE INDEX IF NOT EXISTS idx_episodic_importance ON episodic_memories(importance);
        "#)?;
        Ok(())
    }
}

#[pymethods]
impl EpisodicMemory {
    #[new]
    fn new(db_path: String) -> PyResult<Self> {
        let conn = Connection::open(&db_path).map_err(EpisodicMemoryError::from)?;
        conn.execute_batch("PRAGMA journal_mode=WAL; PRAGMA synchronous=NORMAL;").map_err(EpisodicMemoryError::from)?;
        Self::init_schema(&conn)?;
        Ok(Self { inner: Arc::new(Mutex::new(EpisodicMemoryInner { conn })) })
    }

    #[pyo3(signature = (content, memory_type, domain=None, importance=None))]
    fn store(&self, content: String, memory_type: String, domain: Option<String>, importance: Option<f64>) -> PyResult<String> {
        let id = Uuid::new_v4().to_string()[..12].to_string();
        let now = Utc::now().to_rfc3339();
        let importance = importance.unwrap_or(1.0);
        let inner = self.inner.lock();
        inner.conn.execute(
            "INSERT INTO episodic_memories (id, content, memory_type, domain, importance, access_count, last_accessed, created_at, updated_at, metadata) VALUES (?1, ?2, ?3, ?4, ?5, 0, ?6, ?6, ?6, '{}')",
            params![id, content, memory_type, domain, importance, now],
        ).map_err(EpisodicMemoryError::from)?;
        Ok(id)
    }

    #[pyo3(signature = (query, top_k=None))]
    fn search(&self, query: String, top_k: Option<usize>) -> PyResult<Vec<HashMap<String, String>>> {
        let top_k = top_k.unwrap_or(10);
        let inner = self.inner.lock();
        let query_pattern = format!("%{}%", query);
        let mut stmt = inner.conn.prepare("SELECT id, content, memory_type, importance FROM episodic_memories WHERE content LIKE ?1 AND superseded_by IS NULL ORDER BY importance DESC LIMIT ?2").map_err(EpisodicMemoryError::from)?;
        let results: Vec<HashMap<String, String>> = stmt.query_map(params![query_pattern, top_k as i64], |row| {
            let mut map = HashMap::new();
            map.insert("id".to_string(), row.get::<_, String>(0)?);
            map.insert("content".to_string(), row.get::<_, String>(1)?);
            map.insert("memory_type".to_string(), row.get::<_, String>(2)?);
            map.insert("importance".to_string(), row.get::<_, f64>(3)?.to_string());
            Ok(map)
        }).map_err(EpisodicMemoryError::from)?.filter_map(|r| r.ok()).collect();
        Ok(results)
    }

    #[pyo3(signature = (decay_rate=None))]
    fn decay_importance(&self, decay_rate: Option<f64>) -> PyResult<u64> {
        let decay = decay_rate.unwrap_or(DEFAULT_DECAY_RATE);
        let inner = self.inner.lock();
        let count = inner.conn.execute("UPDATE episodic_memories SET importance = importance * ?1", params![1.0 - decay]).map_err(EpisodicMemoryError::from)?;
        Ok(count as u64)
    }

    #[pyo3(signature = (min_age_days=None, min_importance=None))]
    fn evict_low_importance(&self, min_age_days: Option<u64>, min_importance: Option<f64>) -> PyResult<u64> {
        let min_importance = min_importance.unwrap_or(MIN_IMPORTANCE_THRESHOLD);
        let cutoff = Utc::now() - Duration::days(min_age_days.unwrap_or(DEFAULT_MIN_AGE_DAYS) as i64);
        let inner = self.inner.lock();
        let count = inner.conn.execute("DELETE FROM episodic_memories WHERE importance < ?1 AND created_at < ?2 AND superseded_by IS NULL", params![min_importance, cutoff.to_rfc3339()]).map_err(EpisodicMemoryError::from)?;
        Ok(count as u64)
    }

    fn count(&self) -> PyResult<u64> {
        let inner = self.inner.lock();
        let count: u64 = inner.conn.query_row("SELECT COUNT(*) FROM episodic_memories", [], |row| row.get(0)).map_err(EpisodicMemoryError::from)?;
        Ok(count)
    }

    fn clear(&self) -> PyResult<()> {
        let inner = self.inner.lock();
        inner.conn.execute("DELETE FROM episodic_memories", []).map_err(EpisodicMemoryError::from)?;
        Ok(())
    }
}
