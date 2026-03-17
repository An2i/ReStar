use eframe::egui;
use serde::{Deserialize, Serialize};
use std::path::PathBuf;

#[derive(Clone, Serialize, Deserialize)]
pub struct LlmConfig {
    pub provider: LlmProvider,
    pub api_key: String,
    pub base_url: String,
    pub model: String,
    pub ida_path: String,
}

#[derive(Clone, PartialEq, Serialize, Deserialize)]
pub enum LlmProvider {
    DeepSeek,
    DeepSeekLocal,
    Claude,
    OpenAI,
    Custom,
}

fn config_path() -> PathBuf {
    // 和可执行文件同目录
    let mut path = std::env::current_exe()
        .unwrap_or_else(|_| PathBuf::from("."))
        .parent()
        .unwrap_or(std::path::Path::new("."))
        .to_path_buf();
    path.push("ai_assistant_config.json");
    path
}

fn save_config(config: &LlmConfig) {
    if let Ok(json) = serde_json::to_string_pretty(config) {
        let _ = std::fs::write(config_path(), json);
    }
}

fn load_config() -> Option<LlmConfig> {
    let path = config_path();
    let json = std::fs::read_to_string(path).ok()?;
    serde_json::from_str(&json).ok()
}

impl LlmProvider {
    fn label(&self) -> &str {
        match self {
            LlmProvider::DeepSeek => "DeepSeek (官方)",
            LlmProvider::DeepSeekLocal => "DeepSeek (本地)",
            LlmProvider::Claude => "Claude (Anthropic)",
            LlmProvider::OpenAI => "OpenAI",
            LlmProvider::Custom => "自定义",
        }
    }

    fn default_base_url(&self) -> &str {
        match self {
            LlmProvider::DeepSeek => "https://api.deepseek.com",
            LlmProvider::DeepSeekLocal => "http://localhost:11434/v1",
            LlmProvider::Claude => "https://api.anthropic.com/v1",
            LlmProvider::OpenAI => "https://api.openai.com/v1",
            LlmProvider::Custom => "",
        }
    }

    fn default_model(&self) -> &str {
        match self {
            LlmProvider::DeepSeek => "deepseek-chat",
            LlmProvider::DeepSeekLocal => "deepseek-r1:7b",
            LlmProvider::Claude => "claude-3-5-sonnet-20241022",
            LlmProvider::OpenAI => "gpt-4o",
            LlmProvider::Custom => "",
        }
    }
}

impl Default for LlmConfig {
    fn default() -> Self {
        let provider = LlmProvider::DeepSeek;
        Self {
            base_url: provider.default_base_url().to_string(),
            model: provider.default_model().to_string(),
            provider,
            api_key: std::env::var("DEEPSEEK_API_KEY").unwrap_or_default(),
            ida_path: r"C:\IDA\idat.exe".to_string(),
        }
    }
}

pub struct FileSelectView {
    pub selected_file: Option<String>,
    pub config: LlmConfig,
    show_api_key: bool,
}

impl FileSelectView {
    pub fn new() -> Self {
        let config = load_config().unwrap_or_default();
        Self {
            selected_file: None,
            config,
            show_api_key: false,
        }
    }

    pub fn show(&mut self, ctx: &egui::Context) -> Option<String> {
        let mut confirmed = None;

        egui::CentralPanel::default()
            .frame(
                egui::Frame::none().fill(egui::Color32::from_rgba_unmultiplied(200, 200, 200, 0)),
            )
            .show(ctx, |ui| {
                ui.vertical_centered(|ui| {
                    ui.add_space(60.0);
                    ui.heading(
                        egui::RichText::new("AI 逆向驾驶舱")
                            .size(30.0)
                            .strong()
                            .color(egui::Color32::from_rgb(14, 121, 178)),
                    );
                    ui.add_space(30.0);

                    // 配置区域
                    egui::Frame::none()
                        .fill(ui.visuals().faint_bg_color)
                        .rounding(8.0)
                        .inner_margin(egui::Margin::symmetric(24.0, 16.0))
                        .show(ui, |ui| {
                            ui.set_max_width(480.0);
                            ui.vertical(|ui| {
                                ui.label(
                                    egui::RichText::new("模型配置")
                                        .size(22.0)
                                        .strong()
                                        .color(egui::Color32::from_rgb(14, 121, 178)),
                                );
                                ui.add_space(10.0);

                                // Provider 选择
                                ui.horizontal(|ui| {
                                    ui.label(
                                        egui::RichText::new("服务商：")
                                            .size(16.0)
                                            .strong()
                                            .color(egui::Color32::from_rgb(14, 121, 178)),
                                    );
                                    let providers = [
                                        LlmProvider::DeepSeek,
                                        LlmProvider::DeepSeekLocal,
                                        LlmProvider::Claude,
                                        LlmProvider::OpenAI,
                                        LlmProvider::Custom,
                                    ];
                                    egui::ComboBox::from_id_salt("provider_select")
                                        .selected_text(self.config.provider.label())
                                        .show_ui(ui, |ui| {
                                            for p in &providers {
                                                if ui
                                                    .selectable_value(
                                                        &mut self.config.provider,
                                                        p.clone(),
                                                        p.label(),
                                                    )
                                                    .clicked()
                                                {
                                                    // 切换服务商时自动填入默认值
                                                    self.config.base_url =
                                                        p.default_base_url().to_string();
                                                    self.config.model =
                                                        p.default_model().to_string();
                                                    // Claude 不需要 api_key 环境变量提示
                                                    if self.config.api_key.is_empty() {
                                                        self.config.api_key =
                                                            std::env::var("OPENAI_API_KEY")
                                                                .or_else(|_| {
                                                                    std::env::var(
                                                                        "ANTHROPIC_API_KEY",
                                                                    )
                                                                })
                                                                .or_else(|_| {
                                                                    std::env::var(
                                                                        "DEEPSEEK_API_KEY",
                                                                    )
                                                                })
                                                                .unwrap_or_default();
                                                    }
                                                }
                                            }
                                        });
                                });

                                ui.add_space(8.0);

                                // API Key
                                ui.horizontal(|ui| {
                                    ui.label(
                                        egui::RichText::new("API Key：")
                                            .size(16.0)
                                            .strong()
                                            .color(egui::Color32::from_rgb(14, 121, 178)),
                                    );
                                    let key_input =
                                        egui::TextEdit::singleline(&mut self.config.api_key)
                                            .desired_width(280.0)
                                            .password(!self.show_api_key)
                                            .hint_text("输入 API Key...");
                                    ui.add(key_input);
                                    if ui
                                        .small_button(if self.show_api_key {
                                            "🙈"
                                        } else {
                                            "👁"
                                        })
                                        .clicked()
                                    {
                                        self.show_api_key = !self.show_api_key;
                                    }
                                });

                                ui.add_space(8.0);

                                // Base URL
                                ui.horizontal(|ui| {
                                    ui.label(
                                        egui::RichText::new("API URL：")
                                            .size(16.0)
                                            .strong()
                                            .color(egui::Color32::from_rgb(14, 121, 178)),
                                    );
                                    ui.add(
                                        egui::TextEdit::singleline(&mut self.config.base_url)
                                            .desired_width(280.0)
                                            .hint_text("https://..."),
                                    );
                                });

                                ui.add_space(8.0);

                                // 模型名
                                ui.horizontal(|ui| {
                                    ui.label(
                                        egui::RichText::new("模型名称：")
                                            .size(16.0)
                                            .strong()
                                            .color(egui::Color32::from_rgb(14, 121, 178)),
                                    );
                                    ui.add(
                                        egui::TextEdit::singleline(&mut self.config.model)
                                            .desired_width(280.0)
                                            .hint_text("模型名称..."),
                                    );
                                });

                                ui.add_space(8.0);

                                ui.horizontal(|ui| {
                                    ui.label(
                                        egui::RichText::new("IDA 路径：")
                                            .size(16.0)
                                            .strong()
                                            .color(egui::Color32::from_rgb(14, 121, 178)),
                                    );
                                    ui.add(
                                        egui::TextEdit::singleline(&mut self.config.ida_path)
                                            .desired_width(280.0)
                                            .hint_text(r"C:\IDA\idat.exe"),
                                    );
                                    // 浏览按钮
                                    if ui
                                        .small_button("📂")
                                        .on_hover_text("选择 idat.exe")
                                        .clicked()
                                    {
                                        if let Some(path) = rfd::FileDialog::new()
                                            .add_filter("idat", &["exe"])
                                            .pick_file()
                                        {
                                            self.config.ida_path = path.display().to_string();
                                        }
                                    }
                                });
                            });
                        });

                    ui.add_space(24.0);

                    // 文件选择
                    egui::Frame::none()
                        .fill(ui.visuals().faint_bg_color)
                        .rounding(8.0)
                        .inner_margin(egui::Margin::symmetric(24.0, 16.0))
                        .show(ui, |ui| {
                            ui.set_max_width(480.0);
                            ui.vertical(|ui| {
                                // ui.label(egui::RichText::new("目标文件").strong());
                                ui.label(
                                    egui::RichText::new("目标文件")
                                        .size(16.0)
                                        .strong()
                                        .color(egui::Color32::from_rgb(14, 121, 178)),
                                );

                                ui.add_space(10.0);
                                ui.horizontal(|ui| {
                                    if ui.button("📂  选择文件...").clicked() {
                                        if let Some(path) = rfd::FileDialog::new().pick_file() {
                                            self.selected_file = Some(path.display().to_string());
                                        }
                                    }
                                    if let Some(ref path) = self.selected_file {
                                        ui.label(
                                            egui::RichText::new(path)
                                                .size(11.0)
                                                .color(egui::Color32::GRAY),
                                        );
                                    }
                                });
                            });
                        });

                    ui.add_space(24.0);

                    // 开始按钮
                    let can_start = self.selected_file.is_some()
                        && !self.config.api_key.is_empty()
                        && !self.config.base_url.is_empty()
                        && !self.config.model.is_empty();

                    if ui
                        .add_enabled(
                            can_start,
                            egui::Button::new(egui::RichText::new("Start Analyzing!").size(14.0))
                                .min_size(egui::vec2(180.0, 80.0))
                                .fill(egui::Color32::from_rgb(254, 74, 73)),
                        )
                        .clicked()
                    {
                        confirmed = self.selected_file.clone();
                    }

                    if !can_start && self.selected_file.is_some() {
                        ui.add_space(8.0);
                        ui.label(
                            egui::RichText::new("请填写完整的模型配置")
                                .color(egui::Color32::YELLOW)
                                .size(11.0),
                        );
                    }
                    // save_config(&self.config);
                });
            });

        save_config(&self.config);

        confirmed
    }
}
