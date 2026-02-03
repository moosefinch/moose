//! Inference Router - Multi-backend model multiplexing

use std::collections::HashMap;
use std::sync::Arc;
use pyo3::prelude::*;
use reqwest::Client;
use serde::{Deserialize, Serialize};
use thiserror::Error;
use tokio::sync::Mutex as TokioMutex;

#[derive(Debug, Error)]
pub enum RouterError {
    #[error("Backend not found: {0}")]
    BackendNotFound(String),
    #[error("Model not found: {0}")]
    ModelNotFound(String),
    #[error("HTTP error: {0}")]
    HttpError(#[from] reqwest::Error),
    #[error("JSON error: {0}")]
    JsonError(#[from] serde_json::Error),
    #[error("API error: {0}")]
    ApiError(String),
}

impl From<RouterError> for PyErr {
    fn from(err: RouterError) -> PyErr {
        pyo3::exceptions::PyRuntimeError::new_err(err.to_string())
    }
}

#[derive(Debug, Clone, Serialize, Deserialize)]
struct ChatResponse { choices: Vec<ChatChoice>, model: String }
#[derive(Debug, Clone, Serialize, Deserialize)]
struct ChatChoice { message: ChatMessage, finish_reason: Option<String> }
#[derive(Debug, Clone, Serialize, Deserialize)]
struct ChatMessage { content: Option<String> }
#[derive(Debug, Clone, Serialize, Deserialize)]
struct EmbedResponse { data: Vec<EmbedData> }
#[derive(Debug, Clone, Serialize, Deserialize)]
struct EmbedData { embedding: Vec<f32> }

struct Backend { base_url: String, api_key: Option<String> }
struct RouterInner { backends: HashMap<String, Backend>, model_map: HashMap<String, (String, String)> }

#[pyclass]
pub struct InferenceRouter {
    inner: Arc<TokioMutex<RouterInner>>,
    http_client: Client,
}

#[pymethods]
impl InferenceRouter {
    #[new]
    fn new() -> Self {
        Self {
            inner: Arc::new(TokioMutex::new(RouterInner { backends: HashMap::new(), model_map: HashMap::new() })),
            http_client: Client::builder().pool_max_idle_per_host(10).timeout(std::time::Duration::from_secs(300)).build().unwrap(),
        }
    }

    fn add_backend(&self, name: String, base_url: String, api_key: Option<String>) {
        pyo3_async_runtimes::tokio::get_runtime().block_on(async {
            let mut inner = self.inner.lock().await;
            inner.backends.insert(name, Backend { base_url, api_key });
        });
    }

    fn add_model_mapping(&self, key: String, backend_name: String, model_id: String) {
        pyo3_async_runtimes::tokio::get_runtime().block_on(async {
            let mut inner = self.inner.lock().await;
            inner.model_map.insert(key, (backend_name, model_id));
        });
    }

    fn call_llm<'py>(&self, py: Python<'py>, model_key_or_id: String, messages: Vec<HashMap<String, String>>, max_tokens: Option<usize>, temperature: Option<f64>) -> PyResult<Bound<'py, PyAny>> {
        let inner_arc = self.inner.clone();
        let client = self.http_client.clone();
        pyo3_async_runtimes::tokio::future_into_py(py, async move {
            let inner = inner_arc.lock().await;
            let (backend_name, model_id) = inner.model_map.get(&model_key_or_id).cloned().unwrap_or_else(|| {
                inner.backends.keys().next().map(|k| (k.clone(), model_key_or_id.clone())).unwrap_or_default()
            });
            let backend = inner.backends.get(&backend_name).ok_or_else(|| RouterError::BackendNotFound(backend_name.clone()))?;
            let url = format!("{}/v1/chat/completions", backend.base_url.trim_end_matches('/'));
            let msgs: Vec<serde_json::Value> = messages.iter().map(|m| serde_json::json!({"role": m.get("role").unwrap_or(&"user".to_string()), "content": m.get("content").unwrap_or(&String::new())})).collect();
            let mut body = serde_json::json!({"model": model_id, "messages": msgs, "stream": false});
            if let Some(mt) = max_tokens { body["max_tokens"] = serde_json::json!(mt); }
            if let Some(t) = temperature { body["temperature"] = serde_json::json!(t); }
            let mut req = client.post(&url).json(&body);
            if let Some(ref key) = backend.api_key { req = req.header("Authorization", format!("Bearer {}", key)); }
            drop(inner);
            let response = req.send().await?;
            if !response.status().is_success() { return Err(RouterError::ApiError(format!("HTTP {}", response.status())).into()); }
            let chat: ChatResponse = response.json().await?;
            let content = chat.choices.first().and_then(|c| c.message.content.clone()).unwrap_or_default();
            let mut result = HashMap::new();
            result.insert("content".to_string(), content);
            result.insert("model".to_string(), chat.model);
            result.insert("finish_reason".to_string(), chat.choices.first().and_then(|c| c.finish_reason.clone()).unwrap_or_default());
            Ok(result)
        })
    }

    fn embed<'py>(&self, py: Python<'py>, model_key_or_id: String, texts: Vec<String>) -> PyResult<Bound<'py, PyAny>> {
        let inner_arc = self.inner.clone();
        let client = self.http_client.clone();
        pyo3_async_runtimes::tokio::future_into_py(py, async move {
            let inner = inner_arc.lock().await;
            let (backend_name, model_id) = inner.model_map.get(&model_key_or_id).cloned().unwrap_or_else(|| {
                inner.backends.keys().next().map(|k| (k.clone(), model_key_or_id.clone())).unwrap_or_default()
            });
            let backend = inner.backends.get(&backend_name).ok_or_else(|| RouterError::BackendNotFound(backend_name.clone()))?;
            let url = format!("{}/v1/embeddings", backend.base_url.trim_end_matches('/'));
            let body = serde_json::json!({"model": model_id, "input": texts});
            let mut req = client.post(&url).json(&body);
            if let Some(ref key) = backend.api_key { req = req.header("Authorization", format!("Bearer {}", key)); }
            drop(inner);
            let response = req.send().await?;
            if !response.status().is_success() { return Err(RouterError::ApiError(format!("HTTP {}", response.status())).into()); }
            let embed: EmbedResponse = response.json().await?;
            let embeddings: Vec<Vec<f32>> = embed.data.into_iter().map(|d| d.embedding).collect();
            Ok(embeddings)
        })
    }

    fn list_backends(&self) -> Vec<String> {
        pyo3_async_runtimes::tokio::get_runtime().block_on(async {
            let inner = self.inner.lock().await;
            inner.backends.keys().cloned().collect()
        })
    }

    fn get_model_mapping(&self) -> HashMap<String, (String, String)> {
        pyo3_async_runtimes::tokio::get_runtime().block_on(async {
            let inner = self.inner.lock().await;
            inner.model_map.clone()
        })
    }
}
