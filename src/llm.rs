use crate::types::*;
use anyhow::Result;

pub struct LlmClient {
    client: reqwest::Client,
    api_key: String,
    base_url: String,
    model: String,
}

impl LlmClient {
    pub fn new(api_key: String, base_url: String, model: String) -> Self {
        Self {
            client: reqwest::Client::new(),
            api_key,
            base_url,
            model,
        }
    }

    pub fn get_tools() -> Vec<serde_json::Value> {
        vec![
            serde_json::json!({
                "type": "function",
                "function": {
                    "name": "software_analysis",
                    "description": "use the tool to analysis software, all reverse engine job can be dealed by it.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "ScriptFileName": {"type": "string", "description": "IDAPython script filename"},
                            "Code": {"type": "string", "description": "IDAPython script code"}
                        },
                        "required": ["ScriptFileName", "Code"]
                    }
                }
            }),
            serde_json::json!({
                "type": "function",
                "function": {
                    "name": "generate_report",
                    "description": "use the tool to generate a report about the software analysis.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "ReportFileName": {"type": "string", "description": "the report filename"},
                            "Content": {"type": "string", "description": "the report content."}
                        },
                        "required": ["ReportFileName", "Content"]
                    }
                }
            }),
        ]
    }

    pub async fn send(&self, messages: Vec<ApiMessage>) -> Result<ApiMessage> {
        let req = ChatRequest {
            model: self.model.clone(),
            messages,
            tools: Self::get_tools(),
            tool_choice: serde_json::json!("auto"),
        };

        let resp_text = self
            .client
            .post(format!("{}/chat/completions", self.base_url))
            .bearer_auth(&self.api_key)
            .json(&req)
            .send()
            .await?
            .text()
            .await?;

        // 打印原始响应，方便排查
        println!("[API Response] {}", resp_text);

        let resp: ChatResponse = serde_json::from_str(&resp_text)
            .map_err(|e| anyhow::anyhow!("JSON解析失败: {}\n原始响应: {}", e, resp_text))?;

        resp.choices
            .into_iter()
            .next()
            .map(|c| c.message)
            .ok_or_else(|| anyhow::anyhow!("响应中没有choices"))
    }
}
