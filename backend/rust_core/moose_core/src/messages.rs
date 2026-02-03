//! Message Bus - SQLite-backed inter-agent communication

use std::collections::HashMap;
use std::sync::Arc;
use chrono::Utc;
use dashmap::DashMap;
use once_cell::sync::Lazy;
use parking_lot::Mutex;
use pyo3::prelude::*;
use regex::Regex;
use rusqlite::{params, Connection, OptionalExtension};
use thiserror::Error;
use uuid::Uuid;

static INJECTION_PATTERNS: Lazy<Vec<Regex>> = Lazy::new(|| vec![
    Regex::new(r"(?i)ignore\s+(all\s+)?previous\s+instructions?").unwrap(),
    Regex::new(r"(?i)system:\s*").unwrap(),
    Regex::new(r"(?i)jailbreak").unwrap(),
]);

#[derive(Debug, Error)]
pub enum MessageBusError {
    #[error("Database error: {0}")]
    DatabaseError(#[from] rusqlite::Error),
    #[error("JSON error: {0}")]
    JsonError(#[from] serde_json::Error),
}

impl From<MessageBusError> for PyErr {
    fn from(err: MessageBusError) -> PyErr {
        pyo3::exceptions::PyRuntimeError::new_err(err.to_string())
    }
}

struct MessageBusInner { conn: Connection }

#[pyclass]
pub struct MessageBus {
    inner: Arc<Mutex<MessageBusInner>>,
    cache: Arc<DashMap<String, Vec<HashMap<String, String>>>>,
}

impl MessageBus {
    fn init_schema(conn: &Connection) -> Result<(), MessageBusError> {
        conn.execute_batch(r#"
            CREATE TABLE IF NOT EXISTS agent_messages (
                id TEXT PRIMARY KEY, msg_type TEXT NOT NULL, sender TEXT NOT NULL, recipient TEXT NOT NULL,
                mission_id TEXT, parent_msg_id TEXT, priority INTEGER NOT NULL DEFAULT 1,
                content TEXT NOT NULL, payload TEXT NOT NULL DEFAULT '{}', created_at TEXT NOT NULL, processed_at TEXT
            );
            CREATE INDEX IF NOT EXISTS idx_messages_recipient ON agent_messages(recipient);
            CREATE INDEX IF NOT EXISTS idx_messages_processed ON agent_messages(processed_at);
        "#)?;
        Ok(())
    }

    fn detect_injection(content: &str) -> bool {
        INJECTION_PATTERNS.iter().any(|p| p.is_match(content))
    }
}

#[pymethods]
impl MessageBus {
    #[new]
    #[pyo3(signature = (db_path=None))]
    fn new(db_path: Option<String>) -> PyResult<Self> {
        let db_path = db_path.unwrap_or_else(|| "backend/messages.db".to_string());
        let conn = Connection::open(&db_path).map_err(MessageBusError::from)?;
        conn.execute_batch("PRAGMA journal_mode=WAL; PRAGMA synchronous=NORMAL;").map_err(MessageBusError::from)?;
        Self::init_schema(&conn)?;
        Ok(Self { inner: Arc::new(Mutex::new(MessageBusInner { conn })), cache: Arc::new(DashMap::new()) })
    }

    #[pyo3(signature = (msg_type, sender, recipient, mission_id, content, priority=None))]
    fn send(&self, msg_type: String, sender: String, recipient: String, mission_id: String, content: String, priority: Option<i32>) -> PyResult<String> {
        let id = Uuid::new_v4().to_string()[..12].to_string();
        let now = Utc::now().to_rfc3339();
        let priority = priority.unwrap_or(1);
        let has_injection = Self::detect_injection(&content);
        let payload = if has_injection { r#"{"_injection_warning": true}"# } else { "{}" };
        let inner = self.inner.lock();
        inner.conn.execute(
            "INSERT INTO agent_messages (id, msg_type, sender, recipient, mission_id, priority, content, payload, created_at) VALUES (?1, ?2, ?3, ?4, ?5, ?6, ?7, ?8, ?9)",
            params![id, msg_type, sender, recipient, mission_id, priority, content, payload, now],
        ).map_err(MessageBusError::from)?;
        Ok(id)
    }

    fn pop_next(&self, agent_id: String) -> PyResult<Option<HashMap<String, String>>> {
        let inner = self.inner.lock();
        let now = Utc::now().to_rfc3339();
        let msg: Option<(String, String, String, String)> = inner.conn.query_row(
            "SELECT id, msg_type, sender, content FROM agent_messages WHERE recipient = ?1 AND processed_at IS NULL ORDER BY priority DESC, created_at ASC LIMIT 1",
            params![agent_id], |row| Ok((row.get(0)?, row.get(1)?, row.get(2)?, row.get(3)?))
        ).optional().map_err(MessageBusError::from)?;
        if let Some((id, msg_type, sender, content)) = msg {
            inner.conn.execute("UPDATE agent_messages SET processed_at = ?1 WHERE id = ?2", params![now, id]).map_err(MessageBusError::from)?;
            let mut map = HashMap::new();
            map.insert("id".to_string(), id);
            map.insert("msg_type".to_string(), msg_type);
            map.insert("sender".to_string(), sender);
            map.insert("content".to_string(), content);
            Ok(Some(map))
        } else { Ok(None) }
    }

    fn has_pending(&self, agent_id: String) -> PyResult<bool> {
        let inner = self.inner.lock();
        let count: u64 = inner.conn.query_row("SELECT COUNT(*) FROM agent_messages WHERE recipient = ?1 AND processed_at IS NULL", params![agent_id], |row| row.get(0)).map_err(MessageBusError::from)?;
        Ok(count > 0)
    }

    fn agents_with_pending_messages(&self) -> PyResult<Vec<String>> {
        let inner = self.inner.lock();
        let mut stmt = inner.conn.prepare("SELECT DISTINCT recipient FROM agent_messages WHERE processed_at IS NULL").map_err(MessageBusError::from)?;
        let agents: Vec<String> = stmt.query_map([], |row| row.get(0)).map_err(MessageBusError::from)?.filter_map(|r| r.ok()).collect();
        Ok(agents)
    }

    fn count(&self) -> PyResult<u64> {
        let inner = self.inner.lock();
        let count: u64 = inner.conn.query_row("SELECT COUNT(*) FROM agent_messages", [], |row| row.get(0)).map_err(MessageBusError::from)?;
        Ok(count)
    }

    fn clear(&self) -> PyResult<()> {
        self.cache.clear();
        let inner = self.inner.lock();
        inner.conn.execute("DELETE FROM agent_messages", []).map_err(MessageBusError::from)?;
        Ok(())
    }
}
