//! Backend Adapters
//!
//! Implementations of the InferenceBackend trait for different LLM backends.

mod llamacpp;
mod ollama;
mod openai;

pub use llamacpp::LlamaCppBackend;
pub use ollama::OllamaBackend;
pub use openai::OpenAICompatBackend;

use std::collections::HashMap;

use async_trait::async_trait;
use thiserror::Error;
use tokio::sync::mpsc;

use crate::router::{LlmRequest, LlmResponse, ModelInfo};

#[derive(Debug, Error)]
pub enum AdapterError {
    #[error("HTTP error: {0}")]
    HttpError(#[from] reqwest::Error),

    #[error("JSON error: {0}")]
    JsonError(#[from] serde_json::Error),

    #[error("API error: {0}")]
    ApiError(String),

    #[error("Model not found: {0}")]
    ModelNotFound(String),

    #[error("Streaming error: {0}")]
    StreamError(String),

    #[error("Channel error: {0}")]
    ChannelError(String),
}

impl From<AdapterError> for pyo3::PyErr {
    fn from(err: AdapterError) -> pyo3::PyErr {
        pyo3::exceptions::PyRuntimeError::new_err(err.to_string())
    }
}

/// Trait for inference backend implementations
#[async_trait]
pub trait InferenceBackend: Send + Sync {
    /// Discover available models
    async fn discover_models(&self) -> Result<HashMap<String, ModelInfo>, AdapterError>;

    /// Call the LLM (non-streaming)
    async fn call_llm(&self, request: LlmRequest) -> Result<LlmResponse, AdapterError>;

    /// Call the LLM with streaming response
    async fn call_llm_stream(
        &self,
        request: LlmRequest,
        tx: mpsc::Sender<String>,
    ) -> Result<String, AdapterError>;

    /// Generate embeddings
    async fn embed(
        &self,
        model_id: &str,
        texts: &[String],
    ) -> Result<Vec<Vec<f32>>, AdapterError>;

    /// Load a model into memory
    async fn load_model(
        &self,
        model_id: &str,
        ttl: Option<u64>,
    ) -> Result<bool, AdapterError>;

    /// Unload a model from memory
    async fn unload_model(&self, model_id: &str) -> Result<bool, AdapterError>;
}
