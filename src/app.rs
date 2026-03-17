use eframe::egui;
use std::sync::{Arc, Mutex};
use tokio::sync::mpsc;
use uuid::Uuid;

use crate::llm::LlmClient;
use crate::tools::ToolExecutor;
use crate::types::*;
use crate::views::{
    chat::{ChatEvent, ChatView},
    file_select::FileSelectView,
};

use crate::app::egui::TextureHandle;

pub struct App {
    state: AppState,
    file_select: FileSelectView,
    chat_view: Option<ChatView>,
    messages: Arc<Mutex<Vec<ChatMessage>>>,
    is_loading: Arc<Mutex<bool>>,
    event_tx: mpsc::UnboundedSender<ChatEvent>,
    event_rx: Arc<Mutex<mpsc::UnboundedReceiver<ChatEvent>>>,
    target_file: Option<String>,
    runtime: tokio::runtime::Runtime,
    llm_config: crate::views::file_select::LlmConfig,
    bg_texture: Option<TextureHandle>,
    avatar_ai_texture: Option<TextureHandle>,
    avatar_user_texture: Option<TextureHandle>,
}

fn build_api_messages_from(messages: &[ChatMessage]) -> Vec<ApiMessage> {
    let mut api_msgs = vec![ApiMessage {
        role: "system".to_string(),
        content: Some(
            "你是一名逆向工程师，只能通过调用 software_analysis 工具来完成工作。\
            每次响应都必须调用 software_analysis 工具输出 IDAPython 脚本，脚本必须支持IDA 9.1。\
            禁止直接回复文字，所有分析结果、思路、结论都必须以 IDAPython 脚本的形式通过工具输出。\
            每个脚本执行后，根据执行结果继续生成下一个分析脚本，直到分析完成。\
            分析完成的标志之一是分析完所有start函数调用链中的函数。\
            每个脚本末尾必须调用 idc.qexit(0) 强制退出 IDA 进程。\
            脚本执行的输出结果带有IDA插件加载结果的信息，请忽略掉非脚本定义的输出内容，仅分析脚本中定义的输出内容。\
            所有分析完成后，使用idapython脚本在本地生成一份分析报告。\
            所有idapython脚本执行产生的文件都必须与分析的目标程序在同一目录下。"
                .to_string(),
        ),
        tool_calls: None,
        tool_call_id: None,
    }];

    // 收集所有已有 tool 结果的 tool_call_id
    let responded_ids: std::collections::HashSet<String> = messages
        .iter()
        .filter(|m| m.role == MessageRole::Tool)
        .filter_map(|m| m.tool_call_id.clone())
        .collect();

    for msg in messages.iter() {
        match msg.role {
            MessageRole::User => {
                api_msgs.push(ApiMessage {
                    role: "user".to_string(),
                    content: Some(msg.content.clone()),
                    tool_calls: None,
                    tool_call_id: None,
                });
            }
            MessageRole::Assistant => {
                if msg.tool_calls.is_empty() {
                    if !msg.content.is_empty() {
                        api_msgs.push(ApiMessage {
                            role: "assistant".to_string(),
                            content: Some(msg.content.clone()),
                            tool_calls: None,
                            tool_call_id: None,
                        });
                    }
                } else {
                    // 必须所有 tool_calls 都有响应才加入
                    let all_responded = msg
                        .tool_calls
                        .iter()
                        .all(|tc| responded_ids.contains(&tc.id));

                    if !all_responded {
                        // 有未响应的 tool_call，整条 assistant 消息跳过
                        continue;
                    }

                    let api_tool_calls: Vec<ApiToolCall> = msg
                        .tool_calls
                        .iter()
                        .map(|tc| ApiToolCall {
                            id: tc.id.clone(),
                            call_type: "function".to_string(),
                            function: ApiFunction {
                                name: tc.function_name.clone(),
                                arguments: tc.arguments.to_string(),
                            },
                        })
                        .collect();

                    api_msgs.push(ApiMessage {
                        role: "assistant".to_string(),
                        content: if msg.content.is_empty() {
                            None
                        } else {
                            Some(msg.content.clone())
                        },
                        tool_calls: Some(api_tool_calls),
                        tool_call_id: None,
                    });
                }
            }

            MessageRole::Tool => {
                // 只添加有对应 assistant tool_call 已被包含的 tool 结果
                // 需要确认这条 tool 结果对应的 assistant 消息已经被加入
                let tool_call_id = msg.tool_call_id.as_deref().unwrap_or("");
                let has_parent = api_msgs.iter().any(|m| {
                    m.tool_calls
                        .as_ref()
                        .map(|tcs| tcs.iter().any(|tc| tc.id == tool_call_id))
                        .unwrap_or(false)
                });

                if has_parent {
                    api_msgs.push(ApiMessage {
                        role: "tool".to_string(),
                        content: Some(msg.content.clone()),
                        tool_calls: None,
                        tool_call_id: msg.tool_call_id.clone(),
                    });
                }
            }
        }
    }

    api_msgs
}

fn load_texture(
    cc: &eframe::CreationContext,
    name: &str,
    bytes: &[u8],
) -> Option<egui::TextureHandle> {
    let image = image::load_from_memory(bytes).ok()?.to_rgba8();
    let (w, h) = image.dimensions();
    let pixels = image.into_raw();
    let color_image = egui::ColorImage::from_rgba_unmultiplied([w as usize, h as usize], &pixels);
    Some(
        cc.egui_ctx
            .load_texture(name, color_image, egui::TextureOptions::LINEAR),
    )
}

impl App {
    pub fn new(cc: &eframe::CreationContext) -> Self {
        let mut fonts = egui::FontDefinitions::default();

        fonts.font_data.insert(
            "chinese".to_owned(),
            egui::FontData::from_static(include_bytes!("C:\\Windows\\Fonts\\msyh.ttc")),
        );

        fonts
            .families
            .get_mut(&egui::FontFamily::Proportional)
            .unwrap()
            .push("chinese".to_owned()); 

        fonts
            .families
            .get_mut(&egui::FontFamily::Monospace)
            .unwrap()
            .push("chinese".to_owned());

        cc.egui_ctx.set_fonts(fonts);

        let (tx, rx) = mpsc::unbounded_channel();
        let messages = Arc::new(Mutex::new(Vec::new()));
        let is_loading = Arc::new(Mutex::new(false));
        let runtime = tokio::runtime::Runtime::new().unwrap();

        let bg_texture = load_texture(cc, "background", include_bytes!("../assets/background.jpg"));
        let avatar_ai_texture =
            load_texture(cc, "avatar_ai", include_bytes!("../assets/avatar_ai.png"));
        let avatar_user_texture = load_texture(
            cc,
            "avatar_user",
            include_bytes!("../assets/avatar_user.jpg"),
        );

        Self {
            state: AppState::FileSelect,
            file_select: FileSelectView::new(),
            chat_view: None,
            messages,
            is_loading,
            event_tx: tx,
            event_rx: Arc::new(Mutex::new(rx)),
            target_file: None,
            runtime,
            llm_config: crate::views::file_select::LlmConfig::default(),
            bg_texture,
            avatar_ai_texture,
            avatar_user_texture,
        }
    }

    fn init_chat(&mut self, target: String) {
        self.target_file = Some(target.clone());

        let system_msg = ChatMessage {
            id: Uuid::new_v4().to_string(),
            role: MessageRole::Assistant,
            content: format!(
                "逆星号飞船已加载目标文件：{}。请输入初始提示词开始工作。",
                target
            ),
            tool_calls: vec![],
            tool_call_id: None,
        };

        self.messages.lock().unwrap().push(system_msg);

        self.chat_view = Some(ChatView::new(
            Arc::clone(&self.messages),
            self.event_tx.clone(),
            Arc::clone(&self.is_loading),
            self.avatar_ai_texture.clone(),
            self.avatar_user_texture.clone(),
        ));
    }

    fn build_api_messages(&self) -> Vec<ApiMessage> {
        let messages = self.messages.lock().unwrap();
        build_api_messages_from(&messages)
    }

    fn handle_events(&mut self, ctx: &egui::Context) {
        let events: Vec<ChatEvent> = {
            let mut rx = self.event_rx.lock().unwrap();
            let mut evts = vec![];
            while let Ok(e) = rx.try_recv() {
                evts.push(e);
            }
            evts
        };

        for event in events {
            match event {
                ChatEvent::SendMessage(text) => {
                    self.on_send_message(text, ctx);
                }
                ChatEvent::AppendUserMessage(text) => {
                    self.on_send_message(text, ctx);
                }
                ChatEvent::ApproveToolCall { msg_id, tool_idx } => {
                    self.on_approve_tool_call(msg_id, tool_idx, ctx);
                }
                ChatEvent::RejectToolCall { msg_id, tool_idx } => {
                    self.on_reject_tool_call(msg_id, tool_idx, ctx);
                }
                ChatEvent::ExecuteEditedCode {
                    msg_id,
                    tool_idx,
                    new_code,
                } => {
                    self.on_execute_edited_code(msg_id, tool_idx, new_code, ctx);
                }
            }
        }
    }

    fn on_send_message(&mut self, text: String, ctx: &egui::Context) {
        {
            let mut msgs = self.messages.lock().unwrap();

            // 给所有还未响应的 tool_calls 补占位消息
            let pending_tool_calls: Vec<(String, String)> = msgs
                .iter()
                .filter(|m| m.role == MessageRole::Assistant)
                .flat_map(|m| {
                    m.tool_calls
                        .iter()
                        .filter(|tc| {
                            tc.status == ToolCallStatus::Pending
                                || tc.status == ToolCallStatus::Approved
                        })
                        .map(|tc| (tc.id.clone(), m.id.clone()))
                        .collect::<Vec<_>>()
                })
                .collect();

            for (tc_id, _msg_id) in pending_tool_calls {
                msgs.push(ChatMessage {
                    id: uuid::Uuid::new_v4().to_string(),
                    role: MessageRole::Tool,
                    content: serde_json::json!({
                        "status": "skipped",
                        "message": "用户发送了新消息，该工具调用被跳过。"
                    })
                    .to_string(),
                    tool_calls: vec![],
                    tool_call_id: Some(tc_id),
                });
            }

            // 同时把这些 tool_calls 状态标记为 Rejected，避免 UI 还显示勾叉按钮
            for msg in msgs.iter_mut() {
                if msg.role == MessageRole::Assistant {
                    for tc in msg.tool_calls.iter_mut() {
                        if tc.status == ToolCallStatus::Pending
                            || tc.status == ToolCallStatus::Approved
                        {
                            tc.status = ToolCallStatus::Rejected;
                        }
                    }
                }
            }

            // 添加用户消息
            msgs.push(ChatMessage {
                id: uuid::Uuid::new_v4().to_string(),
                role: MessageRole::User,
                content: text,
                tool_calls: vec![],
                tool_call_id: None,
            });
        }

        self.call_llm(ctx);
    }

    fn on_approve_tool_call(&mut self, msg_id: String, tool_idx: usize, ctx: &egui::Context) {
        {
            let mut msgs = self.messages.lock().unwrap();
            if let Some(msg) = msgs.iter_mut().find(|m| m.id == msg_id) {
                if let Some(tc) = msg.tool_calls.get_mut(tool_idx) {
                    tc.status = ToolCallStatus::Approved;
                }
            }
        }
        self.try_execute_approved_tools(msg_id, ctx);
    }

    fn on_reject_tool_call(&mut self, msg_id: String, tool_idx: usize, ctx: &egui::Context) {
        {
            let mut msgs = self.messages.lock().unwrap();
            if let Some(msg) = msgs.iter_mut().find(|m| m.id == msg_id) {
                if let Some(tc) = msg.tool_calls.get_mut(tool_idx) {
                    tc.status = ToolCallStatus::Rejected;
                }
            }
        }
        self.try_execute_approved_tools(msg_id, ctx);
    }

    fn on_execute_edited_code(
        &mut self,
        msg_id: String,
        tool_idx: usize,
        new_code: String,
        ctx: &egui::Context,
    ) {
        // 更新 Code 字段
        {
            let mut msgs = self.messages.lock().unwrap();
            if let Some(msg) = msgs.iter_mut().find(|m| m.id == msg_id) {
                if let Some(tc) = msg.tool_calls.get_mut(tool_idx) {
                    if let Some(obj) = tc.arguments.as_object_mut() {
                        obj.insert("Code".to_string(), serde_json::Value::String(new_code));
                    } else {
                        tc.arguments = serde_json::json!({ "Code": new_code });
                    }
                    tc.status = ToolCallStatus::Approved;
                    tc.result = None;
                }
            }
        }

        // 直接触发执行
        self.try_execute_approved_tools(msg_id, ctx);
    }

    fn try_execute_approved_tools(&mut self, msg_id: String, ctx: &egui::Context) {
        let all_decided = {
            let msgs = self.messages.lock().unwrap();
            msgs.iter()
                .find(|m| m.id == msg_id)
                .map(|m| {
                    m.tool_calls
                        .iter()
                        .all(|tc| tc.status != ToolCallStatus::Pending)
                })
                .unwrap_or(false)
        };

        if !all_decided {
            return;
        }

        let approved_tools: Vec<(usize, ToolCall)> = {
            let msgs = self.messages.lock().unwrap();
            msgs.iter()
                .find(|m| m.id == msg_id)
                .map(|m| {
                    m.tool_calls
                        .iter()
                        .enumerate()
                        .filter(|(_, tc)| tc.status == ToolCallStatus::Approved)
                        .map(|(i, tc)| (i, tc.clone()))
                        .collect()
                })
                .unwrap_or_default()
        };

        if approved_tools.is_empty() {
            // 补全所有 rejected tool call 的占位消息
            {
                let msgs_snapshot = self.messages.lock().unwrap();
                let rejected: Vec<ToolCall> = msgs_snapshot
                    .iter()
                    .find(|m| m.id == msg_id)
                    .map(|m| {
                        m.tool_calls
                            .iter()
                            .filter(|tc| tc.status == ToolCallStatus::Rejected)
                            .cloned()
                            .collect()
                    })
                    .unwrap_or_default();
                drop(msgs_snapshot);

                let mut msgs = self.messages.lock().unwrap();
                for tc in rejected {
                    msgs.push(ChatMessage {
                        id: Uuid::new_v4().to_string(),
                        role: MessageRole::Tool,
                        content: serde_json::json!({
                            "status": "rejected",
                            "message": "用户拒绝了该工具调用，请跳过此步骤继续。"
                        })
                        .to_string(),
                        tool_calls: vec![],
                        tool_call_id: Some(tc.id.clone()),
                    });
                }
            }
            self.call_llm(ctx);
            return;
        }

        {
            let mut msgs = self.messages.lock().unwrap();
            if let Some(msg) = msgs.iter_mut().find(|m| m.id == msg_id) {
                for (i, _) in &approved_tools {
                    if let Some(tc) = msg.tool_calls.get_mut(*i) {
                        tc.status = ToolCallStatus::Executing;
                    }
                }
            }
        }

        let target = self.target_file.clone().unwrap_or_default();
        let messages_arc = Arc::clone(&self.messages);
        let is_loading = Arc::clone(&self.is_loading);
        let ctx = ctx.clone();

        // *is_loading.lock().unwrap() = true;
        let api_key = self.llm_config.api_key.clone();
        let base_url = self.llm_config.base_url.clone();
        let model = self.llm_config.model.clone();
        let ida_path = self.llm_config.ida_path.clone();

        self.runtime.spawn(async move {
            let executor = ToolExecutor::new(target, ida_path);

            for (tool_idx, tc) in approved_tools {
                let result_str = match executor.execute(&tc) {
                    Ok(s) => s,
                    Err(e) => format!("执行失败: {}", e),
                };
                //同意
                {
                    let mut msgs = messages_arc.lock().unwrap();
                    if let Some(msg) = msgs.iter_mut().find(|m| m.id == msg_id) {
                        if let Some(tool_call) = msg.tool_calls.get_mut(tool_idx) {
                            tool_call.status = ToolCallStatus::Done;
                            // tool_call.result = Some(result_str.chars().take(1000).collect());
                            tool_call.result = Some(result_str.clone());
                        }
                    }
                    msgs.push(ChatMessage {
                        id: Uuid::new_v4().to_string(),
                        role: MessageRole::Tool,
                        content: serde_json::json!({
                            "status": "success",
                            "ida_output": result_str,
                            "next_hint": "根据以上执行结果，继续生成下一个分析脚本。"
                        })
                        .to_string(),
                        tool_calls: vec![],
                        tool_call_id: Some(tc.id.clone()),
                    });
                }
                //拒绝
                {
                    let rejected_tools: Vec<ToolCall> = {
                        let msgs = messages_arc.lock().unwrap();
                        msgs.iter()
                            .find(|m| m.id == msg_id)
                            .map(|m| {
                                m.tool_calls
                                    .iter()
                                    .filter(|tc| tc.status == ToolCallStatus::Rejected)
                                    .cloned()
                                    .collect()
                            })
                            .unwrap_or_default()
                    };

                    let mut msgs = messages_arc.lock().unwrap();
                    for tc in rejected_tools {
                        msgs.push(ChatMessage {
                            id: Uuid::new_v4().to_string(),
                            role: MessageRole::Tool,
                            content: serde_json::json!({
                                "status": "rejected",
                                "message": "用户拒绝了该工具调用，请跳过此步骤继续。"
                            })
                            .to_string(),
                            tool_calls: vec![],
                            tool_call_id: Some(tc.id.clone()),
                        });
                    }
                }
            }

            let api_messages = {
                let msgs = messages_arc.lock().unwrap();
                build_api_messages_from(&msgs)
            };

            let client = LlmClient::new(api_key, base_url, model.clone());

            match client.send(api_messages).await {
                Ok(api_msg) => {
                    let tool_calls: Vec<ToolCall> = api_msg
                        .tool_calls
                        .as_ref()
                        .map(|tcs| {
                            tcs.iter()
                                .map(|tc| {
                                    let args = serde_json::from_str(&tc.function.arguments)
                                        .unwrap_or(serde_json::Value::Null);
                                    ToolCall {
                                        id: tc.id.clone(),
                                        function_name: tc.function.name.clone(),
                                        arguments: args,
                                        status: ToolCallStatus::Pending,
                                        result: None,
                                    }
                                })
                                .collect()
                        })
                        .unwrap_or_default();

                    messages_arc.lock().unwrap().push(ChatMessage {
                        id: Uuid::new_v4().to_string(),
                        role: MessageRole::Assistant,
                        content: api_msg.content.unwrap_or_default(),
                        tool_calls,
                        tool_call_id: None,
                    });
                }
                Err(e) => {
                    messages_arc.lock().unwrap().push(ChatMessage {
                        id: Uuid::new_v4().to_string(),
                        role: MessageRole::Assistant,
                        content: format!("❌ API调用失败: {}", e),
                        tool_calls: vec![],
                        tool_call_id: None,
                    });
                }
            }

            *is_loading.lock().unwrap() = false;
            ctx.request_repaint();
        });
    }

    fn call_llm(&mut self, ctx: &egui::Context) {
        let api_messages = self.build_api_messages();
        let messages_arc = Arc::clone(&self.messages);
        let is_loading = Arc::clone(&self.is_loading);
        let ctx = ctx.clone();

        let api_key = self.llm_config.api_key.clone();
        let base_url = self.llm_config.base_url.clone();
        let model = self.llm_config.model.clone();

        *is_loading.lock().unwrap() = true;

        self.runtime.spawn(async move {
            let client = LlmClient::new(api_key, base_url, model);

            // 发送请求，等待 API 响应，匹配成功或失败
            match client.send(api_messages).await {
                Ok(api_msg) => {
                    // API 调用成功
                    let tool_calls: Vec<ToolCall> = api_msg
                        .tool_calls
                        .as_ref()
                        .map(|tcs| {
                            // 如果有 tool_calls 则遍历转换，没有则返回空 Vec
                            tcs.iter()
                                .map(|tc| {
                                    let args = serde_json::from_str(&tc.function.arguments)// 将 arguments 字符串解析为 JSON，解析失败则用 Null
                                        .unwrap_or(serde_json::Value::Null);
                                    ToolCall {
                                        // 构建内部 ToolCall 结构
                                        id: tc.id.clone(), // tool call 唯一 id
                                        function_name: tc.function.name.clone(), // 函数名
                                        arguments: args,   // 解析后的参数
                                        status: ToolCallStatus::Pending, // 初始状态为待确认
                                        result: None,      // 尚未执行，无结果
                                    }
                                })
                                .collect()
                        })
                        .unwrap_or_default(); // tool_calls 为 None 时返回空 Vec

                    messages_arc.lock().unwrap().push(ChatMessage {
                        id: Uuid::new_v4().to_string(),               // 生成唯一消息 id
                        role: MessageRole::Assistant,                 // 标记为 assistant 角色
                        content: api_msg.content.unwrap_or_default(), // 文字内容，没有则为空字符串
                        tool_calls,                                   // 附带的 tool call 列表
                        tool_call_id: None, // assistant 消息不需要 tool_call_id
                    });
                }
                Err(e) => {
                    messages_arc.lock().unwrap().push(ChatMessage {
                        id: Uuid::new_v4().to_string(),
                        role: MessageRole::Assistant,
                        content: format!("❌ API调用失败: {}", e),
                        tool_calls: vec![],
                        tool_call_id: None,
                    });
                }
            }

            *is_loading.lock().unwrap() = false;
            ctx.request_repaint();
        });
    }
}

impl eframe::App for App {
    fn update(&mut self, ctx: &egui::Context, _frame: &mut eframe::Frame) {
        // 设置所有面板背景透明
        let mut style = (*ctx.style()).clone();
        style.visuals.panel_fill = egui::Color32::TRANSPARENT;
        style.visuals.window_fill = egui::Color32::TRANSPARENT;
        ctx.set_style(style);

        // 绘制背景图到最底层
        if let Some(ref bg) = self.bg_texture {
            let screen = ctx.screen_rect();
            let painter = ctx.layer_painter(egui::LayerId::background());
            painter.image(
                bg.id(),
                screen,
                egui::Rect::from_min_max(egui::pos2(0.0, 0.0), egui::pos2(1.0, 1.0)),
                egui::Color32::from_rgba_unmultiplied(255, 255, 255, 180),
            );
        }

        self.handle_events(ctx);

        if let Some(chat) = self.chat_view.as_ref() {
            if chat.auto_approve {
                let auto_events = chat.collect_auto_approve_events();
                for event in auto_events {
                    match event {
                        ChatEvent::ApproveToolCall { msg_id, tool_idx } => {
                            self.on_approve_tool_call(msg_id, tool_idx, ctx);
                        }
                        _ => {}
                    }
                }
            }
        }

        match self.state {
            AppState::FileSelect => {
                if let Some(path) = self.file_select.show(ctx) {
                    self.llm_config = self.file_select.config.clone();
                    self.init_chat(path);
                    self.state = AppState::Chat;
                }
            }
            AppState::Chat => {
                if let Some(chat) = self.chat_view.as_mut() {
                    chat.show(ctx);
                }
            }
        }
    }
}
