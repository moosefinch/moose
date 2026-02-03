//! Vector Memory Engine
//!
//! High-performance semantic memory store with SIMD-accelerated cosine similarity search.

use std::collections::HashMap;
use std::fs::{File, OpenOptions};
use std::io::{BufRead, BufReader, BufWriter, Write};
use std::path::PathBuf;
use std::sync::Arc;

use chrono::Utc;
use ndarray::{Array1, Array2};
use once_cell::sync::Lazy;
use parking_lot::RwLock;
use pyo3::prelude::*;
use pyo3::types::PyDict;
use regex::Regex;
use reqwest::Client;
use serde::{Deserialize, Serialize};
use thiserror::Error;
use tokio::sync::Mutex as TokioMutex;

const MAX_MEMORY_ENTRIES: usize = 10_000;
const DEFAULT_MEMORY_PATH: &str = "backend/memory.jsonl";
static TAG_REGEX: Lazy<Regex> = Lazy::new(|| Regex::new(r"^[a-zA-Z0-9_\-]+$").unwrap());
const MAX_TAGS: usize = 20;
const MAX_TAG_LENGTH: usize = 50;

#[derive(Debug, Error)]
pub enum VectorMemoryError {
    #[error("Embedder not configured")]
    EmbedderNotConfigured,
    #[error("HTTP request failed: {0}")]
    HttpError(#[from] reqwest::Error),
    #[error("JSON parsing error: {0}")]
    JsonError(#[from] serde_json::Error),
    #[error("IO error: {0}")]
    IoError(#[from] std::io::Error),
    #[error("Invalid tag: {0}")]
    InvalidTag(String),
    #[error("Embedding API error: {0}")]
    EmbeddingApiError(String),
}

impl From<VectorMemoryError> for PyErr {
    fn from(err: VectorMemoryError) -> PyErr {
        pyo3::exceptions::PyRuntimeError::new_err(err.to_string())
    }
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct MemoryEntry {
    pub text: String,
    pub vector: Vec<f32>,
    pub tags: String,
    pub timestamp: f64,
    pub source: String,
    pub temporal_type: String,
    pub valid_from: f64,
    pub valid_to: f64,
    pub entity_type: String,
    pub entity_id: String,
}

#[derive(Debug, Deserialize)]
struct EmbeddingResponse {
    data: Vec<EmbeddingData>,
}

#[derive(Debug, Deserialize)]
struct EmbeddingData {
    embedding: Vec<f32>,
}

struct VectorMemoryInner {
    entries: Vec<MemoryEntry>,
    vectors: Option<Array2<f32>>,
    api_base: Option<String>,
    embed_model: Option<String>,
    persistence_path: PathBuf,
}

#[pyclass]
pub struct VectorMemory {
    inner: Arc<RwLock<VectorMemoryInner>>,
    http_client: Client,
    async_lock: Arc<TokioMutex<()>>,
}

impl VectorMemory {
    fn validate_tags(tags: &str) -> Result<(), VectorMemoryError> {
        if tags.is_empty() {
            return Ok(());
        }
        let tag_list: Vec<&str> = tags.split(',').map(|s| s.trim()).collect();
        if tag_list.len() > MAX_TAGS {
            return Err(VectorMemoryError::InvalidTag(format!("Too many tags (max {})", MAX_TAGS)));
        }
        for tag in tag_list {
            if tag.len() > MAX_TAG_LENGTH || !TAG_REGEX.is_match(tag) {
                return Err(VectorMemoryError::InvalidTag(format!("Invalid tag: '{}'", tag)));
            }
        }
        Ok(())
    }

    fn load_from_disk(path: &PathBuf) -> Result<Vec<MemoryEntry>, VectorMemoryError> {
        if !path.exists() {
            return Ok(Vec::new());
        }
        let file = File::open(path)?;
        let reader = BufReader::new(file);
        let mut entries = Vec::new();
        for line in reader.lines() {
            let line = line?;
            if line.trim().is_empty() {
                continue;
            }
            if let Ok(entry) = serde_json::from_str::<MemoryEntry>(&line) {
                entries.push(entry);
            }
        }
        Ok(entries)
    }

    fn save_to_disk(path: &PathBuf, entries: &[MemoryEntry]) -> Result<(), VectorMemoryError> {
        let file = OpenOptions::new().write(true).create(true).truncate(true).open(path)?;
        let mut writer = BufWriter::new(file);
        for entry in entries {
            writeln!(writer, "{}", serde_json::to_string(entry)?)?;
        }
        writer.flush()?;
        Ok(())
    }

    fn build_vector_matrix(entries: &[MemoryEntry]) -> Option<Array2<f32>> {
        if entries.is_empty() {
            return None;
        }
        let dim = entries[0].vector.len();
        if dim == 0 {
            return None;
        }
        let mut matrix = Array2::zeros((entries.len(), dim));
        for (i, entry) in entries.iter().enumerate() {
            for (j, &val) in entry.vector.iter().enumerate() {
                matrix[[i, j]] = val;
            }
        }
        for mut row in matrix.rows_mut() {
            let norm: f32 = row.iter().map(|x| x * x).sum::<f32>().sqrt();
            if norm > 0.0 {
                row.mapv_inplace(|x| x / norm);
            }
        }
        Some(matrix)
    }

    fn cosine_similarity(vectors: &Array2<f32>, query: &Array1<f32>) -> Array1<f32> {
        let norm: f32 = query.iter().map(|x| x * x).sum::<f32>().sqrt();
        let query_norm = if norm > 0.0 { query.mapv(|x| x / norm) } else { query.clone() };
        vectors.dot(&query_norm)
    }

    async fn embed_internal(client: &Client, api_base: &str, model: &str, text: &str) -> Result<Vec<f32>, VectorMemoryError> {
        let url = format!("{}/v1/embeddings", api_base.trim_end_matches('/'));
        let payload = serde_json::json!({"model": model, "input": text});
        let response = client.post(&url).json(&payload).send().await?;
        if !response.status().is_success() {
            return Err(VectorMemoryError::EmbeddingApiError(format!("HTTP {}", response.status())));
        }
        let embed_response: EmbeddingResponse = response.json().await?;
        embed_response.data.into_iter().next().map(|d| d.embedding)
            .ok_or_else(|| VectorMemoryError::EmbeddingApiError("No embedding in response".to_string()))
    }
}

#[pymethods]
impl VectorMemory {
    #[new]
    #[pyo3(signature = (persistence_path=None))]
    fn new(persistence_path: Option<String>) -> PyResult<Self> {
        let path = PathBuf::from(persistence_path.unwrap_or_else(|| DEFAULT_MEMORY_PATH.to_string()));
        let entries = Self::load_from_disk(&path).map_err(|e| pyo3::exceptions::PyIOError::new_err(e.to_string()))?;
        let vectors = Self::build_vector_matrix(&entries);
        let inner = VectorMemoryInner { entries, vectors, api_base: None, embed_model: None, persistence_path: path };
        Ok(Self {
            inner: Arc::new(RwLock::new(inner)),
            http_client: Client::builder().pool_max_idle_per_host(10).build().unwrap(),
            async_lock: Arc::new(TokioMutex::new(())),
        })
    }

    fn set_embedder(&self, api_base: String, model_id: String) {
        let mut inner = self.inner.write();
        inner.api_base = Some(api_base);
        inner.embed_model = Some(model_id);
    }

    fn embed<'py>(&self, py: Python<'py>, text: String) -> PyResult<Bound<'py, PyAny>> {
        let (api_base, model) = {
            let inner = self.inner.read();
            (inner.api_base.clone().ok_or(VectorMemoryError::EmbedderNotConfigured)?,
             inner.embed_model.clone().ok_or(VectorMemoryError::EmbedderNotConfigured)?)
        };
        let client = self.http_client.clone();
        pyo3_async_runtimes::tokio::future_into_py(py, async move {
            Self::embed_internal(&client, &api_base, &model, &text).await.map_err(|e| e.into())
        })
    }

    #[pyo3(signature = (text, tags=None, temporal_type=None, valid_from=None, valid_to=None, entity_type=None, entity_id=None, source=None))]
    fn store<'py>(&self, py: Python<'py>, text: String, tags: Option<String>, temporal_type: Option<String>,
        valid_from: Option<f64>, valid_to: Option<f64>, entity_type: Option<String>, entity_id: Option<String>, source: Option<String>,
    ) -> PyResult<Bound<'py, PyAny>> {
        let tags = tags.unwrap_or_default();
        Self::validate_tags(&tags)?;
        let inner_arc = self.inner.clone();
        let client = self.http_client.clone();
        let async_lock = self.async_lock.clone();
        pyo3_async_runtimes::tokio::future_into_py(py, async move {
            let _guard = async_lock.lock().await;
            let (api_base, model) = {
                let inner = inner_arc.read();
                (inner.api_base.clone().ok_or(VectorMemoryError::EmbedderNotConfigured)?,
                 inner.embed_model.clone().ok_or(VectorMemoryError::EmbedderNotConfigured)?)
            };
            let vector = Self::embed_internal(&client, &api_base, &model, &text).await?;
            let entry = MemoryEntry {
                text, vector, tags, timestamp: Utc::now().timestamp_millis() as f64 / 1000.0,
                source: source.unwrap_or_else(|| "internal".to_string()),
                temporal_type: temporal_type.unwrap_or_default(),
                valid_from: valid_from.unwrap_or(0.0), valid_to: valid_to.unwrap_or(0.0),
                entity_type: entity_type.unwrap_or_default(), entity_id: entity_id.unwrap_or_default(),
            };
            let index = {
                let mut inner = inner_arc.write();
                while inner.entries.len() >= MAX_MEMORY_ENTRIES { inner.entries.remove(0); }
                inner.entries.push(entry);
                inner.vectors = Self::build_vector_matrix(&inner.entries);
                let _ = Self::save_to_disk(&inner.persistence_path, &inner.entries);
                inner.entries.len() - 1
            };
            Ok(index)
        })
    }

    #[pyo3(signature = (query, top_k=None, temporal_filter=None))]
    fn search<'py>(&self, py: Python<'py>, query: String, top_k: Option<usize>, temporal_filter: Option<String>) -> PyResult<Bound<'py, PyAny>> {
        let top_k = top_k.unwrap_or(5);
        let inner_arc = self.inner.clone();
        let client = self.http_client.clone();
        pyo3_async_runtimes::tokio::future_into_py(py, async move {
            let (api_base, model, entries, vectors) = {
                let inner = inner_arc.read();
                (inner.api_base.clone().ok_or(VectorMemoryError::EmbedderNotConfigured)?,
                 inner.embed_model.clone().ok_or(VectorMemoryError::EmbedderNotConfigured)?,
                 inner.entries.clone(), inner.vectors.clone())
            };
            if entries.is_empty() { return Ok(Vec::<(HashMap<String, String>, f64)>::new()); }
            let vectors = match vectors { Some(v) => v, None => return Ok(Vec::new()) };
            let query_vec = Self::embed_internal(&client, &api_base, &model, &query).await?;
            let query_arr = Array1::from_vec(query_vec);
            let similarities = Self::cosine_similarity(&vectors, &query_arr);
            let mut scored: Vec<(usize, f32)> = similarities.iter().enumerate().map(|(i, &s)| (i, s)).collect();
            scored.sort_by(|a, b| b.1.partial_cmp(&a.1).unwrap_or(std::cmp::Ordering::Equal));
            let now = Utc::now().timestamp_millis() as f64 / 1000.0;
            let filtered: Vec<(usize, f32)> = if let Some(ref filter) = temporal_filter {
                scored.into_iter().filter(|(i, _)| {
                    let e = &entries[*i];
                    match filter.as_str() {
                        "current" => (e.valid_from == 0.0 || e.valid_from <= now) && (e.valid_to == 0.0 || e.valid_to >= now),
                        "historical" => e.valid_to > 0.0 && e.valid_to < now,
                        _ => true,
                    }
                }).collect()
            } else { scored };
            let results: Vec<(HashMap<String, String>, f64)> = filtered.into_iter().take(top_k).map(|(i, score)| {
                let e = &entries[i];
                let mut map = HashMap::new();
                map.insert("text".to_string(), e.text.clone());
                map.insert("tags".to_string(), e.tags.clone());
                map.insert("timestamp".to_string(), e.timestamp.to_string());
                map.insert("source".to_string(), e.source.clone());
                (map, score as f64)
            }).collect();
            Ok(results)
        })
    }

    fn count(&self) -> usize { self.inner.read().entries.len() }

    fn clear(&self) -> PyResult<()> {
        let mut inner = self.inner.write();
        inner.entries.clear();
        inner.vectors = None;
        if inner.persistence_path.exists() { std::fs::remove_file(&inner.persistence_path)?; }
        Ok(())
    }
}
