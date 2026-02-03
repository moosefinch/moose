//! Shared Workspace - Mission-scoped collaboration

use std::collections::HashMap;
use std::sync::Arc;
use chrono::Utc;
use dashmap::DashMap;
use parking_lot::RwLock;
use pyo3::prelude::*;
use rusqlite::{params, Connection};
use thiserror::Error;
use uuid::Uuid;

#[derive(Debug, Error)]
pub enum WorkspaceError {
    #[error("Database error: {0}")]
    DatabaseError(#[from] rusqlite::Error),
    #[error("JSON error: {0}")]
    JsonError(#[from] serde_json::Error),
}

impl From<WorkspaceError> for PyErr {
    fn from(err: WorkspaceError) -> PyErr {
        pyo3::exceptions::PyRuntimeError::new_err(err.to_string())
    }
}

struct SharedWorkspaceInner { conn: Connection }

#[pyclass]
pub struct SharedWorkspace {
    inner: Arc<RwLock<SharedWorkspaceInner>>,
    cache: Arc<DashMap<String, Vec<HashMap<String, String>>>>,
}

impl SharedWorkspace {
    fn init_schema(conn: &Connection) -> Result<(), WorkspaceError> {
        conn.execute_batch(r#"
            CREATE TABLE IF NOT EXISTS workspace_entries (
                id TEXT PRIMARY KEY, mission_id TEXT NOT NULL, agent_id TEXT NOT NULL,
                entry_type TEXT NOT NULL, title TEXT NOT NULL, content TEXT NOT NULL,
                tags TEXT NOT NULL DEFAULT '[]', reference_list TEXT NOT NULL DEFAULT '[]', created_at TEXT NOT NULL
            );
            CREATE INDEX IF NOT EXISTS idx_workspace_mission ON workspace_entries(mission_id);
        "#)?;
        Ok(())
    }
}

#[pymethods]
impl SharedWorkspace {
    #[new]
    #[pyo3(signature = (db_path=None))]
    fn new(db_path: Option<String>) -> PyResult<Self> {
        let db_path = db_path.unwrap_or_else(|| "backend/workspace.db".to_string());
        let conn = Connection::open(&db_path)?;
        conn.execute_batch("PRAGMA journal_mode=WAL; PRAGMA synchronous=NORMAL;")?;
        Self::init_schema(&conn)?;
        Ok(Self { inner: Arc::new(RwLock::new(SharedWorkspaceInner { conn })), cache: Arc::new(DashMap::new()) })
    }

    fn add(&self, mission_id: String, agent_id: String, entry_type: String, title: String, content: String) -> PyResult<String> {
        let id = Uuid::new_v4().to_string()[..12].to_string();
        let now = Utc::now().to_rfc3339();
        let inner = self.inner.write();
        inner.conn.execute(
            "INSERT INTO workspace_entries (id, mission_id, agent_id, entry_type, title, content, created_at) VALUES (?1, ?2, ?3, ?4, ?5, ?6, ?7)",
            params![id, mission_id, agent_id, entry_type, title, content, now],
        )?;
        Ok(id)
    }

    #[pyo3(signature = (mission_id, agent_id=None, entry_type=None))]
    fn query(&self, mission_id: String, agent_id: Option<String>, entry_type: Option<String>) -> PyResult<Vec<HashMap<String, String>>> {
        let inner = self.inner.read();
        let mut sql = "SELECT id, agent_id, entry_type, title, content FROM workspace_entries WHERE mission_id = ?1".to_string();
        if agent_id.is_some() { sql.push_str(" AND agent_id = ?2"); }
        if entry_type.is_some() { sql.push_str(if agent_id.is_some() { " AND entry_type = ?3" } else { " AND entry_type = ?2" }); }
        sql.push_str(" ORDER BY created_at ASC");
        let mut stmt = inner.conn.prepare(&sql)?;
        let results: Vec<HashMap<String, String>> = match (agent_id.as_ref(), entry_type.as_ref()) {
            (Some(a), Some(t)) => stmt.query_map(params![mission_id, a, t], |row| {
                let mut m = HashMap::new();
                m.insert("id".to_string(), row.get::<_, String>(0)?);
                m.insert("agent_id".to_string(), row.get::<_, String>(1)?);
                m.insert("entry_type".to_string(), row.get::<_, String>(2)?);
                m.insert("title".to_string(), row.get::<_, String>(3)?);
                m.insert("content".to_string(), row.get::<_, String>(4)?);
                Ok(m)
            })?.filter_map(|r| r.ok()).collect(),
            (Some(a), None) => stmt.query_map(params![mission_id, a], |row| {
                let mut m = HashMap::new();
                m.insert("id".to_string(), row.get::<_, String>(0)?);
                m.insert("agent_id".to_string(), row.get::<_, String>(1)?);
                m.insert("entry_type".to_string(), row.get::<_, String>(2)?);
                m.insert("title".to_string(), row.get::<_, String>(3)?);
                m.insert("content".to_string(), row.get::<_, String>(4)?);
                Ok(m)
            })?.filter_map(|r| r.ok()).collect(),
            (None, Some(t)) => stmt.query_map(params![mission_id, t], |row| {
                let mut m = HashMap::new();
                m.insert("id".to_string(), row.get::<_, String>(0)?);
                m.insert("agent_id".to_string(), row.get::<_, String>(1)?);
                m.insert("entry_type".to_string(), row.get::<_, String>(2)?);
                m.insert("title".to_string(), row.get::<_, String>(3)?);
                m.insert("content".to_string(), row.get::<_, String>(4)?);
                Ok(m)
            })?.filter_map(|r| r.ok()).collect(),
            (None, None) => stmt.query_map(params![mission_id], |row| {
                let mut m = HashMap::new();
                m.insert("id".to_string(), row.get::<_, String>(0)?);
                m.insert("agent_id".to_string(), row.get::<_, String>(1)?);
                m.insert("entry_type".to_string(), row.get::<_, String>(2)?);
                m.insert("title".to_string(), row.get::<_, String>(3)?);
                m.insert("content".to_string(), row.get::<_, String>(4)?);
                Ok(m)
            })?.filter_map(|r| r.ok()).collect(),
        };
        Ok(results)
    }

    fn get_mission_summary(&self, mission_id: String) -> PyResult<String> {
        let entries = self.query(mission_id.clone(), None, None)?;
        if entries.is_empty() { return Ok(format!("No entries for mission {}", mission_id)); }
        let mut summary = format!("=== Mission {} Summary ===\n\n", mission_id);
        for e in entries {
            summary.push_str(&format!("### {} ({})\n{}\n\n", e.get("title").unwrap_or(&String::new()), e.get("agent_id").unwrap_or(&String::new()), e.get("content").unwrap_or(&String::new())));
        }
        Ok(summary)
    }

    fn clear_mission(&self, mission_id: String) -> PyResult<u64> {
        self.cache.remove(&mission_id);
        let inner = self.inner.write();
        let count = inner.conn.execute("DELETE FROM workspace_entries WHERE mission_id = ?1", params![mission_id])?;
        Ok(count as u64)
    }

    fn count(&self) -> PyResult<u64> {
        let inner = self.inner.read();
        let count: u64 = inner.conn.query_row("SELECT COUNT(*) FROM workspace_entries", [], |row| row.get(0))?;
        Ok(count)
    }

    fn clear(&self) -> PyResult<()> {
        self.cache.clear();
        let inner = self.inner.write();
        inner.conn.execute("DELETE FROM workspace_entries", [])?;
        Ok(())
    }
}
