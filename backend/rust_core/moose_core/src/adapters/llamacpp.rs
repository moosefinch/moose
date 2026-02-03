//! llama.cpp Backend Adapter
//!
//! Implementation for llama.cpp server API.

use std::collections::HashMap;

use async_trait::async_trait;
use futures::StreamExt;
use reqwest::Client;
use serde::{Deserialize, Serialize};
use tokio::sync::mpsc;

use super::{AdapterError, InferenceBackend};
use crate::router::{LlmRequest, LlmResponse, ModelInfo, UsageInfo};

/// llama.cpp model list response
#[derive(Debug, Deserialize)]
struct LlamaCppModelsResponse {
    data: Vec<LlamaCppModel>,
}

#[derive(Debug, Deserialize)]
struct LlamaCppModel {
    id: String,
    #[serde(default)]
    object: String,
}

/// llama.cpp completion response
#[derive(Debug, Deserialize)]
struct LlamaCppCompletionResponse {
    choices: Vec<LlamaCppChoice>,
    #[serde(default)]
    model: String,
    usage: Option<LlamaCppUsage>,
}

#[derive(Debug, Deserialize)]
struct LlamaCppChoice {
    message: LlamaCppMessage,
    #[serde(default)]
    finish_reason: Option<String>,
}

#[derive(Debug, Deserialize)]
struct LlamaCppMessage {
    content: Option<String>,
    #[serde(default)]
    tool_calls: Vec<serde_json::Value>,
}

#[derive(Debug, Deserialize)]
struct LlamaCppUsage {
    prompt_tokens: usize,
    completion_tokens: usize,
    total_tokens: usize,
}

/// llama.cpp streaming chunk
#[derive(Debug, Deserialize)]
struct LlamaCppStreamChunk {
    choices: Vec<LlamaCppStreamChoice>,
}

#[derive(Debug, Deserialize)]
struct LlamaCppStreamChoice {
    delta: LlamaCppDelta,
    #[serde(default)]
    finish_reason: Option<String>,
}

#[derive(Debug, Deserialize)]
struct LlamaCppDelta {
    content: Option<String>,
}

/// llama.cpp embedding response
#[derive(Debug, Deserialize)]
struct LlamaCppEmbeddingResponse {
    data: Vec<LlamaCppEmbeddingData>,
}

#[derive(Debug, Deserialize)]
struct LlamaCppEmbeddingData {
    embedding: Vec<f32>,
}

/// llama.cpp Backend
pub struct LlamaCppBackend {
    base_url: String,
    client: Client,
}

impl LlamaCppBackend {
    pub fn new(base_url: String, client: Client) -> Self {
        Self { base_url, client }
    }
}

#[async_trait]
impl InferenceBackend for LlamaCppBackend {
    async fn discover_models(&self) -> Result<HashMap<String, ModelInfo>, AdapterError> {
        let url = format!("{}/v1/models", self.base_url.trim_end_matches('/'));

        let response = self.client.get(&url).send().await?;

        if !response.status().is_success() {
            return Err(AdapterError::ApiError(format!(
                "Failed to list models: {}",
                response.status()
            )));
        }

        let models_response: LlamaCppModelsResponse = response.json().await?;

        let mut models = HashMap::new();
        for model in models_response.data {
            models.insert(
                model.id.clone(),
                ModelInfo {
                    id: model.id.clone(),
                    name: model.id,
                    backend: "llamacpp".to_string(),
                    context_length: None,
                    max_tokens: None,
                    loaded: true,
                },
            );
        }

        Ok(models)
    }

    async fn call_llm(&self, request: LlmRequest) -> Result<LlmResponse, AdapterError> {
        let url = format!("{}/v1/chat/completions", self.base_url.trim_end_matches('/'));

        let mut body = serde_json::json!({
            "model": request.model,
            "messages": request.messages,
            "stream": false,
        });

        if let Some(max_tokens) = request.max_tokens {
            body["max_tokens"] = serde_json::json!(max_tokens);
        }

        if let Some(temperature) = request.temperature {
            body["temperature"] = serde_json::json!(temperature);
        }

        if let Some(ref tools) = request.tools {
            body["tools"] = serde_json::json!(tools);
        }

        if let Some(ref tool_choice) = request.tool_choice {
            body["tool_choice"] = serde_json::json!(tool_choice);
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

        let completion: LlamaCppCompletionResponse = response.json().await?;

        let choice = completion
            .choices
            .into_iter()
            .next()
            .ok_or_else(|| AdapterError::ApiError("No choices in response".to_string()))?;

        Ok(LlmResponse {
            content: choice.message.content.unwrap_or_default(),
            model: completion.model,
            finish_reason: choice.finish_reason,
            tool_calls: choice.message.tool_calls,
            usage: completion.usage.map(|u| UsageInfo {
                prompt_tokens: u.prompt_tokens,
                completion_tokens: u.completion_tokens,
                total_tokens: u.total_tokens,
            }),
        })
    }

    async fn call_llm_stream(
        &self,
        request: LlmRequest,
        tx: mpsc::Sender<String>,
    ) -> Result<String, AdapterError> {
        let url = format!("{}/v1/chat/completions", self.base_url.trim_end_matches('/'));

        let mut body = serde_json::json!({
            "model": request.model,
            "messages": request.messages,
            "stream": true,
        });

        if let Some(max_tokens) = request.max_tokens {
            body["max_tokens"] = serde_json::json!(max_tokens);
        }

        if let Some(temperature) = request.temperature {
            body["temperature"] = serde_json::json!(temperature);
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

            // Process SSE lines
            while let Some(newline_pos) = buffer.find('\n') {
                let line = buffer[..newline_pos].trim().to_string();
                buffer = buffer[newline_pos + 1..].to_string();

                if line.starts_with("data: ") {
                    let data = &line[6..];
                    if data == "[DONE]" {
                        continue;
                    }

                    if let Ok(chunk) = serde_json::from_str::<LlamaCppStreamChunk>(data) {
                        for choice in chunk.choices {
                            if let Some(content) = choice.delta.content {
                                full_content.push_str(&content);
                                let _ = tx.send(content).await;
                            }
                        }
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
        let url = format!("{}/v1/embeddings", self.base_url.trim_end_matches('/'));

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

        let embed_response: LlamaCppEmbeddingResponse = response.json().await?;

        Ok(embed_response.data.into_iter().map(|d| d.embedding).collect())
    }

    async fn load_model(
        &self,
        _model_id: &str,
        _ttl: Option<u64>,
    ) -> Result<bool, AdapterError> {
        // llama.cpp typically has models pre-loaded
        Ok(true)
    }

    async fn unload_model(&self, _model_id: &str) -> Result<bool, AdapterError> {
        // llama.cpp doesn't support dynamic unloading via API
        Ok(true)
    }
}
