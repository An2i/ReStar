use eframe::egui;
use std::sync::{Arc, Mutex};
use tokio::sync::mpsc;

use crate::types::*;

pub enum ChatEvent {
    SendMessage(String),
    ApproveToolCall {
        msg_id: String,
        tool_idx: usize,
    },
    RejectToolCall {
        msg_id: String,
        tool_idx: usize,
    },
    ExecuteEditedCode {
        msg_id: String,
        tool_idx: usize,
        new_code: String,
    }, // 编辑代码后直接执行
    AppendUserMessage(String), // 用户主动补充提示词
}

pub struct ChatView {
    pub messages: Arc<Mutex<Vec<ChatMessage>>>,
    pub input_text: String,
    pub event_tx: mpsc::UnboundedSender<ChatEvent>,
    pub is_loading: Arc<Mutex<bool>>,

    editing_msg_id: Option<String>,
    editing_tool_idx: Option<usize>,
    pub is_editing_tool: bool, // true=来自tool call编辑，false=用户主动输入

    input_height: f32,

    pub avatar_ai: Option<egui::TextureHandle>, //头像
    pub avatar_user: Option<egui::TextureHandle>,

    pub auto_approve: bool, //自动化逆向标志
}

fn code_block(ui: &mut egui::Ui, code: &str) {
    egui::Frame::none()
        .fill(egui::Color32::from_rgb(30, 30, 30))
        .rounding(4.0)
        .inner_margin(egui::Margin::symmetric(10.0, 8.0))
        .show(ui, |ui| {
            ui.set_max_width(ui.available_width());
            for (i, line) in code.lines().enumerate() {
                ui.horizontal(|ui| {
                    ui.label(
                        egui::RichText::new(format!("{:>4} ", i + 1))
                            .monospace()
                            .size(11.0)
                            .color(egui::Color32::from_rgb(100, 100, 100)),
                    );
                    ui.add(
                        egui::Label::new(
                            egui::RichText::new(line)
                                .monospace()
                                .size(11.0)
                                .color(egui::Color32::from_rgb(220, 120, 170)),
                        )
                        .wrap(),
                    );
                });
            }
        });
}

fn output_block(ui: &mut egui::Ui, text: &str) {
    egui::Frame::none()
        .fill(egui::Color32::from_rgb(30, 30, 30))
        .rounding(4.0)
        .inner_margin(egui::Margin::symmetric(10.0, 8.0))
        .show(ui, |ui| {
            ui.set_max_width(ui.available_width());
            ui.add(
                egui::Label::new(
                    egui::RichText::new(text)
                        .monospace()
                        .size(11.0)
                        .color(egui::Color32::from_rgb(220, 120, 100)),
                )
                .wrap(),
            );
        });
}

fn render_avatar(ui: &mut egui::Ui, texture: &Option<egui::TextureHandle>, fallback: &str) {
    if let Some(ref tex) = texture {
        ui.add(
            egui::Image::new(tex)
                .max_size(egui::vec2(32.0, 32.0))
                .rounding(16.0), // 圆形头像
        );
    } else {
        ui.label(fallback);
    }
}

impl ChatView {
    pub fn new(
        messages: Arc<Mutex<Vec<ChatMessage>>>,
        event_tx: mpsc::UnboundedSender<ChatEvent>,
        is_loading: Arc<Mutex<bool>>,
        avatar_ai: Option<egui::TextureHandle>,
        avatar_user: Option<egui::TextureHandle>,
    ) -> Self {
        Self {
            messages,
            input_text: String::new(),
            event_tx,
            is_loading,
            is_editing_tool: false,
            editing_msg_id: None,
            editing_tool_idx: None,
            input_height: 120.0,
            avatar_ai,
            avatar_user,
            auto_approve: false,
        }
    }

    pub fn show(&mut self, ctx: &egui::Context) {
        let loading = *self.is_loading.lock().unwrap();

        // 顶部状态栏
        egui::TopBottomPanel::top("top_bar")
            .frame(egui::Frame::none().fill(egui::Color32::from_rgba_unmultiplied(0, 0, 0, 160)))
            .show(ctx, |ui| {
                ui.horizontal(|ui| {
                    ui.heading("AI 逆向驾驶舱");
                    if loading {
                        ui.spinner();
                        ui.label("飞行中...");
                    }
                    ui.with_layout(egui::Layout::right_to_left(egui::Align::Center), |ui| {
                        let btn_text = if self.auto_approve {
                            egui::RichText::new("自动 On").color(egui::Color32::from_rgb(93,	211,	158))
                        } else {
                            egui::RichText::new("自动 Off").color(egui::Color32::from_rgb(255,	239,	159))
                        };
                        if ui.button(btn_text).clicked() {
                            self.auto_approve = !self.auto_approve;
                        }
                    });
                });
            });

        // 底部输入区--编辑框
        let max_input_height = ctx.available_rect().height() * 0.7; // 最多占窗口60%
        let clamped_height = self.input_height.min(max_input_height); // 将输入框高度限制在最大值以内，防止超出可用空间

        egui::TopBottomPanel::bottom("input_panel")
            .frame(
                egui::Frame::none().fill(egui::Color32::from_rgba_unmultiplied(200, 200, 200, 0)),
            )
            .exact_height(self.input_height)
            .show(ctx, |ui| {
                // 拖拽手柄放在最顶部
                let (handle_rect, handle_resp) = ui.allocate_exact_size(
                    egui::vec2(ui.available_width(), 6.0),
                    egui::Sense::drag(),
                );

                let handle_color = if handle_resp.hovered() || handle_resp.dragged() {
                    egui::Color32::from_rgb(100, 120, 220)
                } else {
                    egui::Color32::from_rgb(70, 70, 70)
                };
                ui.painter().rect_filled(handle_rect, 2.0, handle_color);

                if handle_resp.hovered() || handle_resp.dragged() {
                    ui.ctx().set_cursor_icon(egui::CursorIcon::ResizeVertical);
                }

                if handle_resp.dragged() {
                    self.input_height = (self.input_height - handle_resp.drag_delta().y)
                        .max(60.0)
                        .min(600.0);
                }

                ui.add_space(4.0);

                ui.horizontal(|ui| {
                    let is_editing_code = self.is_editing_tool;
                    // let text_width = ui.available_width() - 80.0;
                    let text_height = clamped_height - 20.0;

                    let total_width = ui.available_width();
                    let btn_width = 90.0;
                    let input_width =
                        (total_width - btn_width - ui.spacing().item_spacing.x).max(100.0);

                    // 用 ScrollArea 包裹 TextEdit
                    egui::ScrollArea::vertical()
                        .id_salt("input_scroll")
                        .max_height(text_height)
                        .min_scrolled_height(text_height)
                        .show(ui, |ui| {
                            let input = if is_editing_code {
                                egui::TextEdit::multiline(&mut self.input_text)
                                    // .desired_rows(1)
                                    // .desired_width(text_width)
                                    // .min_size(egui::vec2(text_width, text_height))
                                    .font(egui::TextStyle::Monospace)
                                    .hint_text("编辑代码后发送直接执行...")
                                    .desired_rows(10)
                                    .desired_width(input_width)
                                    .code_editor()
                            } else {
                                egui::TextEdit::multiline(&mut self.input_text)
                                    .desired_rows(5)
                                    .desired_width(input_width)
                                    // .min_size(egui::vec2(text_width, text_height))
                                    .hint_text("输入补充提示词发送给大模型...")
                            };
                            ui.add(input);
                        });

                    let btn_label = if loading { "⏳" } else { "发送" };
                    ui.with_layout(egui::Layout::top_down(egui::Align::Center), |ui| {
                        let send_btn = ui.add_enabled(
                            !loading && !self.input_text.trim().is_empty(),
                            egui::Button::new(egui::RichText::new(btn_label).size(20.0))
                                .min_size(egui::vec2(btn_width - 10.0, 70.0))
                                .fill(egui::Color32::from_rgb(132, 112, 255)),
                        );
                        if send_btn.clicked() {
                            let text = self.input_text.trim().to_string();
                            if !text.is_empty() {
                                if self.is_editing_tool {
                                    if let (Some(msg_id), Some(tool_idx)) =
                                        (self.editing_msg_id.take(), self.editing_tool_idx.take())
                                    {
                                        let _ = self.event_tx.send(ChatEvent::ExecuteEditedCode {
                                            msg_id,
                                            tool_idx,
                                            new_code: text,
                                        });
                                    }
                                    self.is_editing_tool = false;
                                } else {
                                    let _ = self.event_tx.send(ChatEvent::AppendUserMessage(text));
                                }
                                self.input_text.clear();
                            }
                        }

                        if self.editing_msg_id.is_some() {
                            if ui
                                .add(
                                    egui::Button::new(egui::RichText::new("取消").size(16.0))
                                        .min_size(egui::vec2(btn_width - 10.0, 35.0))
                                        .fill(egui::Color32::from_rgb(255, 236, 139)),
                                )
                                .clicked()
                            {
                                self.editing_msg_id = None;
                                self.editing_tool_idx = None;
                                self.is_editing_tool = false;
                                self.input_text.clear();
                            }
                        }
                    });
                });
            });

        // 对话区域
        egui::CentralPanel::default()
            .frame(
                egui::Frame::none().fill(egui::Color32::from_rgba_unmultiplied(200, 200, 200, 0)),
            )
            .show(ctx, |ui| {
                egui::ScrollArea::vertical()
                    .auto_shrink([false; 2])
                    .stick_to_bottom(true)
                    .show(ui, |ui| {
                        let messages = self.messages.lock().unwrap().clone();
                        for msg in &messages {
                            self.render_message(ui, msg);
                            ui.add_space(8.0);
                        }
                    });
            });
    }

    pub fn collect_auto_approve_events(&self) -> Vec<ChatEvent> {
        if !self.auto_approve {
            return vec![];
        }

        let msgs = self.messages.lock().unwrap();
        let mut events = vec![];
        for msg in msgs.iter() {
            for (idx, tc) in msg.tool_calls.iter().enumerate() {
                if tc.status == ToolCallStatus::Pending {
                    events.push(ChatEvent::ApproveToolCall {
                        msg_id: msg.id.clone(),
                        tool_idx: idx,
                    });
                }
            }
        }
        events
    }

    fn render_message(&mut self, ui: &mut egui::Ui, msg: &ChatMessage) {
        match msg.role {
            MessageRole::User => {
                ui.with_layout(egui::Layout::right_to_left(egui::Align::TOP), |ui| {
                    egui::Frame::none()
                        .fill(ui.visuals().selection.bg_fill)
                        .rounding(8.0)
                        .inner_margin(egui::Margin::symmetric(12.0, 8.0))
                        .show(ui, |ui| {
                            ui.set_max_width(ui.available_width() * 0.75);
                            ui.add(egui::Label::new(&msg.content).wrap());
                        });
                });
            }

            MessageRole::Assistant => {
                ui.with_layout(egui::Layout::left_to_right(egui::Align::TOP), |ui| {
                    // ui.label("逆星");
                    render_avatar(ui, &self.avatar_ai, "逆星");
                    // 在 vertical 之前捕获，减去图标宽度
                    let content_width = ui.available_width() - 40.0;
                    ui.vertical(|ui| {
                        if !msg.content.is_empty() {
                            egui::Frame::none()
                                .fill(egui::Color32::from_rgb(28, 28, 28))
                                .rounding(8.0)
                                .inner_margin(egui::Margin::symmetric(12.0, 8.0))
                                .show(ui, |ui| {
                                    ui.set_max_width(content_width);
                                    ui.add(egui::Label::new(&msg.content).wrap());
                                });
                            ui.add_space(4.0);
                        }

                        for (idx, tool_call) in msg.tool_calls.iter().enumerate() {
                            // 直接传 content_width，不再在内部重新获取
                            self.render_tool_call(ui, msg, idx, tool_call);
                            ui.add_space(4.0);
                        }
                    });
                });
            }

            MessageRole::Tool => {
                ui.with_layout(egui::Layout::left_to_right(egui::Align::TOP), |ui| {
                    // ui.label("结果");
                    render_avatar(ui, &self.avatar_user, "结果");

                    egui::Frame::none()
                        .fill(egui::Color32::from_rgb(28, 28, 28))
                        .rounding(8.0)
                        .inner_margin(egui::Margin::symmetric(12.0, 8.0))
                        .show(ui, |ui| {
                            ui.set_max_width(ui.available_width() - 40.0);
                            let output = serde_json::from_str::<serde_json::Value>(&msg.content)
                                .ok()
                                .and_then(|v| {
                                    v.get("ida_output")
                                        .and_then(|v| v.as_str())
                                        .map(|s| s.to_string())
                                })
                                .unwrap_or_else(|| msg.content.clone());

                            ui.label(
                                egui::RichText::new("📤 IDA 输出")
                                    .size(11.0)
                                    .color(egui::Color32::GRAY),
                            );

                            let area_id = format!("tool_msg_{}", msg.id);
                            egui::ScrollArea::vertical()
                                .id_salt(&area_id)
                                .max_height(300.0)
                                .show(ui, |ui| {
                                    output_block(ui, &output);
                                });
                        });
                });
            }
        }
    }

    fn render_tool_call(
        &mut self,
        ui: &mut egui::Ui,
        msg: &ChatMessage,
        idx: usize,
        tool_call: &ToolCall,
    ) {
        let is_editing =
            self.editing_msg_id.as_deref() == Some(&msg.id) && self.editing_tool_idx == Some(idx);

        let frame_color = match tool_call.status {
            ToolCallStatus::Pending => egui::Color32::from_rgb(60, 60, 30),
            ToolCallStatus::Approved | ToolCallStatus::Executing => {
                egui::Color32::from_rgb(30, 60, 30)
            }
            ToolCallStatus::Done => egui::Color32::from_rgb(20, 80, 150),
            ToolCallStatus::Rejected => egui::Color32::from_rgb(60, 30, 30),
        };

        // 限制整行最大宽度
        // let available_width = ui.available_width();
        // let btn_width = 20.0;
        // let frame_max_width = available_width - btn_width;

        ui.horizontal(|ui| {
            let frame = egui::Frame::none()
                .fill(if is_editing {
                    egui::Color32::from_rgb(50, 50, 80)
                } else {
                    frame_color
                })
                .rounding(8.0)
                .inner_margin(egui::Margin::symmetric(12.0, 8.0));

            let resp = frame.show(ui, |ui| {
                // ui.set_max_width(frame_max_width); // 限制frame内容宽度
                ui.vertical(|ui| {
                    ui.label(
                        egui::RichText::new(format!(
                            "🔧 {} ({})",
                            tool_call.function_name,
                            match tool_call.status {
                                ToolCallStatus::Pending => "待确认",
                                ToolCallStatus::Approved => "已通过",
                                ToolCallStatus::Executing => "执行中",
                                ToolCallStatus::Done => "已完成",
                                ToolCallStatus::Rejected => "已拒绝",
                            }
                        ))
                        .strong(),
                    );

                    // arguments 加滚动+换行
                    egui::ScrollArea::vertical()
                        .id_salt(format!("tool_content_{}_{}", msg.id, idx))
                        .min_scrolled_height(200.0)
                        .max_height(600.0)
                        .show(ui, |ui| {
                            if tool_call.function_name == "generate_report" {
                                // generate_report 专用显示
                                if let Some(filename) = tool_call
                                    .arguments
                                    .get("ReportFileName")
                                    .and_then(|v| v.as_str())
                                {
                                    ui.label(
                                        egui::RichText::new(format!("📋 报告文件：{}", filename))
                                            .size(11.0)
                                            .color(egui::Color32::GRAY),
                                    );
                                    ui.add_space(4.0);
                                }
                                if let Some(content) =
                                    tool_call.arguments.get("Content").and_then(|v| v.as_str())
                                {
                                    ui.label(
                                        egui::RichText::new("📄 报告内容")
                                            .size(11.0)
                                            .color(egui::Color32::GRAY),
                                    );
                                    output_block(ui, content);
                                }
                            } else {
                                // software_analysis 及其他 tool 显示 Code
                                if let Some(code) =
                                    tool_call.arguments.get("Code").and_then(|v| v.as_str())
                                {
                                    ui.label(
                                        egui::RichText::new("📄 IDAPython 脚本")
                                            .size(11.0)
                                            .color(egui::Color32::GRAY),
                                    );
                                    code_block(ui, code);
                                } else {
                                    ui.add(
                                        egui::Label::new(
                                            egui::RichText::new(tool_call.arguments.to_string())
                                                .monospace()
                                                .size(11.0),
                                        )
                                        .wrap(),
                                    );
                                }
                            }
                        });
                });
            });

            if resp.response.interact(egui::Sense::click()).clicked()
                && tool_call.status == ToolCallStatus::Pending
            {
                self.editing_msg_id = Some(msg.id.clone());
                self.editing_tool_idx = Some(idx);
                self.is_editing_tool = true;
                self.input_text = tool_call
                    .arguments
                    .get("Code")
                    .and_then(|v| v.as_str())
                    .unwrap_or(&tool_call.arguments.to_string())
                    .to_string();
            }

            if tool_call.status == ToolCallStatus::Pending {
                // ui.set_max_width(frame_max_width); //限制frame内容宽度
                ui.vertical(|ui| {
                    ui.add_space(4.0);
                    if ui
                        .button(egui::RichText::new("✓").color(egui::Color32::LIGHT_GREEN))
                        .on_hover_text("通过")
                        .clicked()
                    {
                        let _ = self.event_tx.send(ChatEvent::ApproveToolCall {
                            msg_id: msg.id.clone(),
                            tool_idx: idx,
                        });
                    }
                    if ui
                        .button(egui::RichText::new("✗").color(egui::Color32::LIGHT_RED))
                        .on_hover_text("拒绝")
                        .clicked()
                    {
                        let _ = self.event_tx.send(ChatEvent::RejectToolCall {
                            msg_id: msg.id.clone(),
                            tool_idx: idx,
                        });
                    }
                });
            }
        });
    }
}
