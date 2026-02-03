//! GPU Scheduler - Mission orchestration with dependency resolution

use std::collections::HashMap;
use std::sync::atomic::{AtomicBool, Ordering};
use std::sync::Arc;
use chrono::Utc;
use dashmap::DashMap;
use pyo3::prelude::*;
use thiserror::Error;
use uuid::Uuid;

#[derive(Debug, Error)]
pub enum SchedulerError {
    #[error("Mission not found: {0}")]
    MissionNotFound(String),
    #[error("Mission already exists: {0}")]
    MissionAlreadyExists(String),
    #[error("Timeout: {0}")]
    Timeout(String),
}

impl From<SchedulerError> for PyErr {
    fn from(err: SchedulerError) -> PyErr {
        pyo3::exceptions::PyRuntimeError::new_err(err.to_string())
    }
}

#[derive(Debug, Clone)]
struct Task {
    id: String, agent_id: String, description: String, depends_on: Vec<String>, status: String, result: Option<String>,
}

#[derive(Debug, Clone)]
struct Mission {
    id: String, status: String, tasks: HashMap<String, Task>, completed_tasks: usize, total_tasks: usize,
    levels: Vec<Vec<String>>, current_level: usize, created_at: String, completed_at: Option<String>,
}

impl Mission {
    fn build_levels(tasks: &HashMap<String, Task>) -> Vec<Vec<String>> {
        let mut levels = Vec::new();
        let mut remaining: HashMap<String, Vec<String>> = tasks.iter().map(|(id, t)| (id.clone(), t.depends_on.clone())).collect();
        while !remaining.is_empty() {
            let ready: Vec<String> = remaining.iter().filter(|(_, deps)| deps.iter().all(|d| !remaining.contains_key(d))).map(|(id, _)| id.clone()).collect();
            if ready.is_empty() && !remaining.is_empty() { levels.push(remaining.keys().cloned().collect()); break; }
            for id in &ready { remaining.remove(id); }
            if !ready.is_empty() { levels.push(ready); }
        }
        levels
    }
}

#[pyclass]
pub struct Scheduler {
    missions: Arc<DashMap<String, Mission>>,
    running: Arc<AtomicBool>,
}

#[pymethods]
impl Scheduler {
    #[new]
    #[pyo3(signature = (poll_interval_ms=None))]
    fn new(_poll_interval_ms: Option<u64>) -> Self {
        Self { missions: Arc::new(DashMap::new()), running: Arc::new(AtomicBool::new(false)) }
    }

    #[pyo3(signature = (mission_id, tasks, synthesize=None, user_message=None))]
    fn submit_mission(&self, mission_id: String, tasks: Vec<HashMap<String, String>>, _synthesize: Option<bool>, _user_message: Option<String>) -> PyResult<()> {
        if self.missions.contains_key(&mission_id) { return Err(SchedulerError::MissionAlreadyExists(mission_id).into()); }
        let mut task_map = HashMap::new();
        for t in tasks {
            let id = t.get("id").cloned().unwrap_or_else(|| Uuid::new_v4().to_string()[..8].to_string());
            let depends: Vec<String> = t.get("depends_on").map(|s| s.split(',').map(|x| x.trim().to_string()).filter(|x| !x.is_empty()).collect()).unwrap_or_default();
            task_map.insert(id.clone(), Task { id, agent_id: t.get("agent_id").cloned().unwrap_or_default(), description: t.get("task").cloned().unwrap_or_default(), depends_on: depends, status: "pending".to_string(), result: None });
        }
        let total = task_map.len();
        let levels = Mission::build_levels(&task_map);
        self.missions.insert(mission_id.clone(), Mission { id: mission_id, status: "running".to_string(), tasks: task_map, completed_tasks: 0, total_tasks: total, levels, current_level: 0, created_at: Utc::now().to_rfc3339(), completed_at: None });
        Ok(())
    }

    fn get_mission(&self, mission_id: String) -> PyResult<Option<HashMap<String, String>>> {
        if let Some(m) = self.missions.get(&mission_id) {
            let mut map = HashMap::new();
            map.insert("id".to_string(), m.id.clone());
            map.insert("status".to_string(), m.status.clone());
            map.insert("completed_tasks".to_string(), m.completed_tasks.to_string());
            map.insert("total_tasks".to_string(), m.total_tasks.to_string());
            map.insert("current_level".to_string(), m.current_level.to_string());
            Ok(Some(map))
        } else { Ok(None) }
    }

    fn complete_task(&self, mission_id: String, task_id: String, result: Option<String>) -> PyResult<bool> {
        if let Some(mut m) = self.missions.get_mut(&mission_id) {
            let task_result = result.clone();
            if let Some(task) = m.tasks.get_mut(&task_id) {
                task.status = "completed".to_string();
                task.result = task_result;
            }
            m.completed_tasks += 1;
            let current_level = m.current_level;
            if current_level < m.levels.len() {
                let level_complete = m.levels[current_level].iter().all(|tid| m.tasks.get(tid).map(|t| t.status == "completed" || t.status == "failed").unwrap_or(true));
                if level_complete { m.current_level += 1; if m.current_level >= m.levels.len() { m.status = "completed".to_string(); m.completed_at = Some(Utc::now().to_rfc3339()); } }
            }
            Ok(true)
        } else { Ok(false) }
    }

    fn fail_task(&self, mission_id: String, task_id: String, error: String) -> PyResult<bool> {
        if let Some(mut m) = self.missions.get_mut(&mission_id) {
            if let Some(task) = m.tasks.get_mut(&task_id) { task.status = "failed".to_string(); task.result = Some(error); }
            m.status = "failed".to_string(); m.completed_at = Some(Utc::now().to_rfc3339());
            Ok(true)
        } else { Ok(false) }
    }

    fn get_ready_tasks(&self, mission_id: String) -> PyResult<Vec<HashMap<String, String>>> {
        if let Some(m) = self.missions.get(&mission_id) {
            let mut ready = Vec::new();
            if m.current_level < m.levels.len() {
                for tid in &m.levels[m.current_level] {
                    if let Some(t) = m.tasks.get(tid) {
                        if t.status == "pending" {
                            let mut map = HashMap::new();
                            map.insert("id".to_string(), t.id.clone());
                            map.insert("agent_id".to_string(), t.agent_id.clone());
                            map.insert("task".to_string(), t.description.clone());
                            ready.push(map);
                        }
                    }
                }
            }
            Ok(ready)
        } else { Ok(Vec::new()) }
    }

    fn start_task(&self, mission_id: String, task_id: String) -> PyResult<bool> {
        if let Some(mut m) = self.missions.get_mut(&mission_id) {
            if let Some(t) = m.tasks.get_mut(&task_id) { if t.status == "pending" { t.status = "running".to_string(); return Ok(true); } }
        }
        Ok(false)
    }

    fn stop_loop(&self) { self.running.store(false, Ordering::SeqCst); }
    fn is_running(&self) -> bool { self.running.load(Ordering::SeqCst) }
    fn list_missions(&self) -> Vec<String> { self.missions.iter().map(|e| e.key().clone()).collect() }
    fn mission_count(&self) -> usize { self.missions.len() }

    fn cancel_mission(&self, mission_id: String) -> PyResult<bool> {
        if let Some(mut m) = self.missions.get_mut(&mission_id) {
            if m.status == "running" { m.status = "failed".to_string(); m.completed_at = Some(Utc::now().to_rfc3339()); return Ok(true); }
        }
        Ok(false)
    }

    fn clear_completed(&self) -> usize {
        let to_remove: Vec<String> = self.missions.iter().filter(|e| e.value().status == "completed" || e.value().status == "failed").map(|e| e.key().clone()).collect();
        let count = to_remove.len();
        for id in to_remove { self.missions.remove(&id); }
        count
    }
}
