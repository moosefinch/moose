//! OpenAI-Compatible Backend Adapter
//!
//! Implementation for OpenAI API and compatible services (e.g., LM Studio, vLLM).

use std::collections::HashMap;

use async_trait::async_trait;
use futures::StreamExt;
use reqwest::Client;
use serde::{Deserialize, Serialize};
use tokio::sync::mpsc;

use super::{AdapterError, InferenceBackend};
use crate::router::{LlmRequest, LlmResponse, ModelInfo, UsageInfo};

/// OpenAI models list response
#[derive(Debug, Deserialize)]
struct OpenAIModelsResponse {
    data: Vec<OpenAIModel>,
}

#[derive(Debug, Deserialize)]
struct OpenAIModel {
    id: String,
    #[serde(default)]
    object: String,
    #[serde(default)]
    owned_by: String,
}

/// OpenAI chat completion response
#[derive(Debug, Deserialize)]
struct OpenAIChatResponse {
    id: Option<String>,
    choices: Vec<OpenAIChoice>,
    #[serde(default)]
    model: String,
    usage: Option<OpenAIUsage>,
}

#[derive(Debug, Deserialize)]
struct OpenAIChoice {
    message: OpenAIMessage,
    #[serde(default)]
    finish_reason: Option<String>,
    #[serde(default)]
    index: usize,
}

#[derive(Debug, Deserialize)]
struct OpenAIMessage {
    #[serde(default)]
    content: Option<String>,
    #[serde(default)]
    tool_calls: Option<Vec<OpenAIToolCall>>,
}

#[derive(Debug, Clone, Deserialize, Serialize)]
struct OpenAIToolCall {
    id: String,
    #[serde(rename = "type")]
    call_type: String,
    function: OpenAIFunctionCall,
}

#[derive(Debug, Clone, Deserialize, Serialize)]
struct OpenAIFunctionCall {
    name: String,
    arguments: String,
}

#[derive(Debug, Deserialize)]
struct OpenAIUsage {
    prompt_tokens: usize,
    completion_tokens: usize,
    total_tokens: usize,
}

/// OpenAI streaming chunk
#[derive(Debug, Deserialize)]
struct OpenAIStreamChunk {
    choices: Vec<OpenAIStreamChoice>,
}

#[derive(Debug, Deserialize)]
struct OpenAIStreamChoice {
    delta: OpenAIDelta,
    #[serde(default)]
    finish_reason: Option<String>,
}

#[derive(Debug, Deserialize)]
struct OpenAIDelta {
    #[serde(default)]
    content: Option<String>,
    #[serde(default)]
    tool_calls: Option<Vec<OpenAIToolCallDelta>>,
}

#[derive(Debug, Deserialize)]
struct OpenAIToolCallDelta {
    #[serde(default)]
    index: usize,
    #[serde(default)]
    id: Option<String>,
    #[serde(default)]
    function: Option<OpenAIFunctionDelta>,
}

#[derive(Debug, Deserialize)]
struct OpenAIFunctionDelta {
    #[serde(default)]
    name: Option<String>,
    #[serde(default)]
    arguments: Option<String>,
}

/// OpenAI embedding response
#[derive(Debug, Deserialize)]
struct OpenAIEmbeddingResponse {
    data: Vec<OpenAIEmbeddingData>,
    #[serde(default)]
    model: String,
    usage: Option<OpenAIUsage>,
}

#[derive(Debug, Deserialize)]
struct OpenAIEmbeddingData {
    embedding: Vec<f32>,
    #[serde(default)]
    index: usize,
}

/// OpenAI-Compatible Backend
pub struct OpenAICompatBackend {
    base_url: String,
    api_key: Option<String>,
    client: Client,
}

impl OpenAICompatBackend {
    pub fn new(base_url: String, api_key: Option<String>, client: Client) -> Self {
        Self {
            base_url,
            api_key,
            client,
        }
    }

    fn build_request(&self, method: reqwest::Method, url: &str) -> reqwest::RequestBuilder {
        let mut builder = self.client.request(method, url);

        if let Some(ref api_key) = self.api_key {
            builder = builder.header("Authorization", format!("Bearer {}", api_key));
        }

        builder.header("Content-Type", "application/json")
    }
}

#[async_trait]
impl InferenceBackend for OpenAICompatBackend {
    async fn discover_models(&self) -> Result<HashMap<String, ModelInfo>, AdapterError> {
        let url = format!("{}/v1/models", self.base_url.trim_end_matches('/'));

        let response = self
            .build_request(reqwest::Method::GET, &url)
            .send()
            .await?;

        if !response.status().is_success() {
            return Err(AdapterError::ApiError(format!(
                "Failed to list models: {}",
                response.status()
            )));
        }

        let models_response: OpenAIModelsResponse = response.json().await?;

        let mut models = HashMap::new();
        for model in models_response.data {
            models.insert(
                model.id.clone(),
                ModelInfo {
                    id: model.id.clone(),
                    name: model.id,
                    backend: "openai".to_string(),
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

        let response = self
            .build_request(reqwest::Method::POST, &url)
            .json(&body)
            .send()
            .await?;

        if !response.status().is_success() {
            let status = response.status();
            let error_text = response.text().await.unwrap_or_default();
            return Err(AdapterError::ApiError(format!(
                "LLM call failed: {} - {}",
                status, error_text
            )));
        }

        let chat_response: OpenAIChatResponse = response.json().await?;

        let choice = chat_response
            .choices
            .into_iter()
            .next()
            .ok_or_else(|| AdapterError::ApiError("No choices in response".to_string()))?;

        // Convert tool calls to JSON values
        let tool_calls: Vec<serde_json::Value> = choice
            .message
            .tool_calls
            .unwrap_or_default()
            .into_iter()
            .map(|tc| {
                serde_json::json!({
                    "id": tc.id,
                    "type": tc.call_type,
                    "function": {
                        "name": tc.function.name,
                        "arguments": tc.function.arguments,
                    }
                })
            })
            .collect();

        Ok(LlmResponse {
            content: choice.message.content.unwrap_or_default(),
            model: chat_response.model,
            finish_reason: choice.finish_reason,
            tool_calls,
            usage: chat_response.usage.map(|u| UsageInfo {
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

        let response = self
            .build_request(reqwest::Method::POST, &url)
            .json(&body)
            .send()
            .await?;

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

                    if let Ok(chunk) = serde_json::from_str::<OpenAIStreamChunk>(data) {
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

        let response = self
            .build_request(reqwest::Method::POST, &url)
            .json(&body)
            .send()
            .await?;

        if !response.status().is_success() {
            let status = response.status();
            let error_text = response.text().await.unwrap_or_default();
            return Err(AdapterError::ApiError(format!(
                "Embedding call failed: {} - {}",
                status, error_text
            )));
        }

        let embed_response: OpenAIEmbeddingResponse = response.json().await?;

        // Sort by index to ensure correct order
        let mut embeddings: Vec<(usize, Vec<f32>)> = embed_response
            .data
            .into_iter()
            .map(|d| (d.index, d.embedding))
            .collect();
        embeddings.sort_by_key(|(i, _)| *i);

        Ok(embeddings.into_iter().map(|(_, e)| e).collect())
    }

    async fn load_model(
        &self,
        _model_id: &str,
        _ttl: Option<u64>,
    ) -> Result<bool, AdapterError> {
        // Most OpenAI-compatible APIs don't support explicit model loading
        Ok(true)
    }

    async fn unload_model(&self, _model_id: &str) -> Result<bool, AdapterError> {
        // Most OpenAI-compatible APIs don't support explicit model unloading
        Ok(true)
    }
}
