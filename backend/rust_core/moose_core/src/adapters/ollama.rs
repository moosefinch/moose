//! Ollama Backend Adapter
//!
//! Implementation for Ollama server API.

use std::collections::HashMap;

use async_trait::async_trait;
use futures::StreamExt;
use reqwest::Client;
use serde::{Deserialize, Serialize};
use tokio::sync::mpsc;

use super::{AdapterError, InferenceBackend};
use crate::router::{LlmRequest, LlmResponse, ModelInfo, UsageInfo};

/// Ollama models list response
#[derive(Debug, Deserialize)]
struct OllamaModelsResponse {
    models: Vec<OllamaModel>,
}

#[derive(Debug, Deserialize)]
struct OllamaModel {
    name: String,
    #[serde(default)]
    size: u64,
    #[serde(default)]
    digest: String,
    #[serde(default)]
    details: Option<OllamaModelDetails>,
}

#[derive(Debug, Deserialize)]
struct OllamaModelDetails {
    #[serde(default)]
    parameter_size: String,
    #[serde(default)]
    quantization_level: String,
}

/// Ollama chat response
#[derive(Debug, Deserialize)]
struct OllamaChatResponse {
    message: OllamaMessage,
    #[serde(default)]
    model: String,
    #[serde(default)]
    done: bool,
    #[serde(default)]
    prompt_eval_count: Option<usize>,
    #[serde(default)]
    eval_count: Option<usize>,
}

#[derive(Debug, Deserialize)]
struct OllamaMessage {
    #[serde(default)]
    content: String,
    #[serde(default)]
    tool_calls: Vec<serde_json::Value>,
}

/// Ollama streaming response chunk
#[derive(Debug, Deserialize)]
struct OllamaStreamChunk {
    message: Option<OllamaStreamMessage>,
    #[serde(default)]
    done: bool,
}

#[derive(Debug, Deserialize)]
struct OllamaStreamMessage {
    #[serde(default)]
    content: String,
}

/// Ollama embedding response
#[derive(Debug, Deserialize)]
struct OllamaEmbeddingResponse {
    embedding: Vec<f32>,
}

/// Ollama embeddings response (for batch)
#[derive(Debug, Deserialize)]
struct OllamaEmbeddingsResponse {
    embeddings: Vec<Vec<f32>>,
}

/// Ollama Backend
pub struct OllamaBackend {
    base_url: String,
    client: Client,
}

impl OllamaBackend {
    pub fn new(base_url: String, client: Client) -> Self {
        Self { base_url, client }
    }

    /// Convert OpenAI-style messages to Ollama format
    fn convert_messages(messages: &[serde_json::Value]) -> Vec<serde_json::Value> {
        messages
            .iter()
            .map(|msg| {
                let role = msg.get("role").and_then(|r| r.as_str()).unwrap_or("user");
                let content = msg
                    .get("content")
                    .and_then(|c| c.as_str())
                    .unwrap_or("");

                serde_json::json!({
                    "role": role,
                    "content": content
                })
            })
            .collect()
    }
}

#[async_trait]
impl InferenceBackend for OllamaBackend {
    async fn discover_models(&self) -> Result<HashMap<String, ModelInfo>, AdapterError> {
        let url = format!("{}/api/tags", self.base_url.trim_end_matches('/'));

        let response = self.client.get(&url).send().await?;

        if !response.status().is_success() {
            return Err(AdapterError::ApiError(format!(
                "Failed to list models: {}",
                response.status()
            )));
        }

        let models_response: OllamaModelsResponse = response.json().await?;

        let mut models = HashMap::new();
        for model in models_response.models {
            let id = model.name.clone();
            models.insert(
                id.clone(),
                ModelInfo {
                    id: id.clone(),
                    name: model.name,
                    backend: "ollama".to_string(),
                    context_length: None, // Ollama doesn't expose this directly
                    max_tokens: None,
                    loaded: true,
                },
            );
        }

        Ok(models)
    }

    async fn call_llm(&self, request: LlmRequest) -> Result<LlmResponse, AdapterError> {
        let url = format!("{}/api/chat", self.base_url.trim_end_matches('/'));

        let messages = Self::convert_messages(&request.messages);

        let mut body = serde_json::json!({
            "model": request.model,
            "messages": messages,
            "stream": false,
        });

        if let Some(ref tools) = request.tools {
            body["tools"] = serde_json::json!(tools);
        }

        // Ollama uses options for parameters
        let mut options = serde_json::Map::new();
        if let Some(max_tokens) = request.max_tokens {
            options.insert("num_predict".to_string(), serde_json::json!(max_tokens));
        }
        if let Some(temperature) = request.temperature {
            options.insert("temperature".to_string(), serde_json::json!(temperature));
        }
        if !options.is_empty() {
            body["options"] = serde_json::Value::Object(options);
        }

        let response = self.client.post(&url).json(&body).send().await?;

        if !response.status().is_success() {
            let status = response.status();
            let error_text = response.text().await.unwrap_or_default();
            return Err(AdapterError::ApiError(format!(
                "LLM call failed: {} - {}",
                status, error_text
            )));
        }

        let chat_response: OllamaChatResponse = response.json().await?;

        let prompt_tokens = chat_response.prompt_eval_count.unwrap_or(0);
        let completion_tokens = chat_response.eval_count.unwrap_or(0);

        Ok(LlmResponse {
            content: chat_response.message.content,
            model: chat_response.model,
            finish_reason: if chat_response.done {
                Some("stop".to_string())
            } else {
                None
            },
            tool_calls: chat_response.message.tool_calls,
            usage: Some(UsageInfo {
                prompt_tokens,
                completion_tokens,
                total_tokens: prompt_tokens + completion_tokens,
            }),
        })
    }

    async fn call_llm_stream(
        &self,
        request: LlmRequest,
        tx: mpsc::Sender<String>,
    ) -> Result<String, AdapterError> {
        let url = format!("{}/api/chat", self.base_url.trim_end_matches('/'));

        let messages = Self::convert_messages(&request.messages);

        let mut body = serde_json::json!({
            "model": request.model,
            "messages": messages,
            "stream": true,
        });

        let mut options = serde_json::Map::new();
        if let Some(max_tokens) = request.max_tokens {
            options.insert("num_predict".to_string(), serde_json::json!(max_tokens));
        }
        if let Some(temperature) = request.temperature {
            options.insert("temperature".to_string(), serde_json::json!(temperature));
        }
        if !options.is_empty() {
            body["options"] = serde_json::Value::Object(options);
        }

        let response = self.client.post(&url).json(&body).send().await?;

        if !response.status().is_success() {
            let status = response.status();
            let error_text = response.text().await.unwrap_or_default();
            return Err(AdapterError::ApiError(format!(
                "Stream call failed: {} - {}",
                status, error_text
            )));
        }

        let mut stream = response.bytes_stream();
        let mut full_content = String::new();
        let mut buffer = String::new();

        while let Some(chunk_result) = stream.next().await {
            let chunk = chunk_result?;
            let chunk_str = String::from_utf8_lossy(&chunk);
            buffer.push_str(&chunk_str);

            // Ollama sends newline-delimited JSON
            while let Some(newline_pos) = buffer.find('\n') {
                let line = buffer[..newline_pos].trim().to_string();
                buffer = buffer[newline_pos + 1..].to_string();

                if line.is_empty() {
                    continue;
                }

                if let Ok(chunk) = serde_json::from_str::<OllamaStreamChunk>(&line) {
                    if let Some(message) = chunk.message {
                        if !message.content.is_empty() {
                            full_content.push_str(&message.content);
                            let _ = tx.send(message.content).await;
                        }
                    }

                    if chunk.done {
                        break;
                    }
                }
            }
        }

        Ok(full_content)
    }

    async fn embed(
        &self,
        model_id: &str,
        texts: &[String],
    ) -> Result<Vec<Vec<f32>>, AdapterError> {
        let url = format!("{}/api/embed", self.base_url.trim_end_matches('/'));

        // Ollama's embed endpoint can take multiple inputs
        let body = serde_json::json!({
            "model": model_id,
            "input": texts,
        });

        let response = self.client.post(&url).json(&body).send().await?;

        if !response.status().is_success() {
            let status = response.status();
            let error_text = response.text().await.unwrap_or_default();
            return Err(AdapterError::ApiError(format!(
                "Embedding call failed: {} - {}",
                status, error_text
            )));
        }

        // Try batch response first
        let response_text = response.text().await?;

        if let Ok(batch_response) = serde_json::from_str::<OllamaEmbeddingsResponse>(&response_text) {
            return Ok(batch_response.embeddings);
        }

        // Fall back to single embedding response (older API)
        if let Ok(single_response) = serde_json::from_str::<OllamaEmbeddingResponse>(&response_text) {
            return Ok(vec![single_response.embedding]);
        }

        Err(AdapterError::ApiError("Failed to parse embedding response".to_string()))
    }

    async fn load_model(
        &self,
        model_id: &str,
        _ttl: Option<u64>,
    ) -> Result<bool, AdapterError> {
        // Pull model if not present
        let url = format!("{}/api/pull", self.base_url.trim_end_matches('/'));

        let body = serde_json::json!({
            "name": model_id,
            "stream": false,
        });

        let response = self.client.post(&url).json(&body).send().await?;

        Ok(response.status().is_success())
    }

    async fn unload_model(&self, _model_id: &str) -> Result<bool, AdapterError> {
        // Ollama manages model loading automatically
        Ok(true)
    }
}
