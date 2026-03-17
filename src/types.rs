use serde::{Deserialize, Serialize};

#[derive(Debug, Clone, PartialEq)]
pub enum AppState {
    FileSelect,
    Chat,
}

#[derive(Debug, Clone, PartialEq)]
pub enum MessageRole {
    User,
    Assistant,
    Tool,
}

#[derive(Debug, Clone, PartialEq)]
pub enum ToolCallStatus {
    Pending,   // 等待用户确认（勾/叉）
    Approved,  // 已通过，执行中或已完成
    Rejected,  // 已拒绝
    Executing, // 执行中
    Done,      // 执行完成
}

#[derive(Debug, Clone)]
pub struct ToolCall {
    pub id: String,
    pub function_name: String,
    pub arguments: serde_json::Value,
    pub status: ToolCallStatus,
    pub result: Option<String>,
}

#[derive(Debug, Clone)]
pub struct ChatMessage {
    pub id: String,
    pub role: MessageRole,
    pub content: String,
    pub tool_calls: Vec<ToolCall>,
    pub tool_call_id: Option<String>, // for tool result messages
}

// ===== OpenAI API 结构 =====

#[derive(Debug, Serialize, Deserialize, Clone)]
pub struct ApiMessage {
    pub role: String,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub content: Option<String>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub tool_calls: Option<Vec<ApiToolCall>>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub tool_call_id: Option<String>,
}

#[derive(Debug, Serialize, Deserialize, Clone)]
pub struct ApiToolCall {
    pub id: String,
    #[serde(rename = "type")]
    pub call_type: String,
    pub function: ApiFunction,
}

#[derive(Debug, Serialize, Deserialize, Clone)]
pub struct ApiFunction {
    pub name: String,
    pub arguments: String,
}

#[derive(Debug, Serialize, Deserialize)]
pub struct ChatRequest {
    pub model: String,
    pub messages: Vec<ApiMessage>,
    pub tools: Vec<serde_json::Value>,
    pub tool_choice: serde_json::Value,
}

#[derive(Debug, Deserialize)]
pub struct ChatResponse {
    pub choices: Vec<Choice>,
}

#[derive(Debug, Deserialize)]
pub struct Choice {
    pub message: ApiMessage,
    pub finish_reason: Option<String>,
}
