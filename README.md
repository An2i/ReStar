# AI 逆向驾驶舱——ReStar

ReStar是一个基于 Rust + egui 构建的 AI 辅助逆向工程工具，旨在通过大模型分析来减轻逆向研究人员的工作量，通过大模型自动生成并执行 IDAPython 脚本，帮助逆向工程师高效分析二进制文件。支持监督和自动两种模式自由切换来完成工作，监督模式下研究人员可以依据自身经验来纠正模型分析出现的错误以及帮助模型找到分析的捷径，更有效地完成工作。

## 功能特性

- 🤖 **AI 驱动分析** — 接入 DeepSeek、Claude、OpenAI 等主流大模型，自动生成 IDAPython 脚本
- 🔧 **交互式 Tool 调用** — 每个脚本任务以气泡形式展示，用户可逐一审核、编辑、通过或拒绝
- ✏️ **代码编辑** — 点击任意脚本气泡可直接编辑代码内容，修改后立即执行
- 🚀 **自动逆向模式** — 一键开启全自动模式，所有脚本任务自动通过执行，无需手动确认
- 📋 **分析报告** — 分析完成后自动生成本地报告文件
- 🎨 **自定义界面** — 支持背景图片、头像配置，代码块高亮显示
- 💾 **配置持久化** — API Key、模型、IDA 路径等配置自动保存，下次启动自动加载

## 截图

> ![screen1](https://github.com/An2i/ReStar/blob/main/image/screen1.png)
>
> ![screen1](https://github.com/An2i/ReStar/blob/main/image/screen2.png)
>
> ![screen1](https://github.com/An2i/ReStar/blob/main/image/screen3.png)
>
> ![screen1](https://github.com/An2i/ReStar/blob/main/image/screen4.png)
>
> ![screen1](https://github.com/An2i/ReStar/blob/main/image/screen5.png)
>
> ![screen1](https://github.com/An2i/ReStar/blob/main/image/screen6.png)
>
> ![screen1](https://github.com/An2i/ReStar/blob/main/image/screen7.png)
>
> ![screen1](https://github.com/An2i/ReStar/blob/main/image/screen8.png)
>
> ![screen1](https://github.com/An2i/ReStar/blob/main/image/screen9.png)

## 环境要求

- Rust 1.88.0+
- IDA Pro 9.1（需要 `idat.exe`）
- Windows（当前 IDA 路径配置针对 Windows）

## 快速开始

### 1. 克隆项目

```bash
git clone https://github.com/An2i/ReStar.git
cd ReStar
2. 编译
cargo build --release
3. 运行
cargo run --release
4. 配置
启动后在初始界面完成以下配置：

配置项	说明
服务商	选择 DeepSeek / Claude / OpenAI / 本地模型 / 自定义
API Key	对应服务商的 API Key
Base URL	API 接口地址，选择服务商后自动填入
模型名称	如 deepseek-chat、gpt-4o 等
IDA 路径	idat.exe 的完整路径
配置完成后选择目标二进制文件，点击「开始分析」即可。

使用流程
选择目标文件
     ↓
AI 自动生成 IDAPython 脚本
     ↓
用户审核脚本（✓ 通过 / ✗ 拒绝 / 编辑后执行）
     ↓
脚本在 IDA 中执行，结果反馈给 AI
     ↓
AI 根据结果生成下一个脚本
     ↓
循环直到分析完成，生成报告
也可开启「🤖 自动逆向」模式跳过手动确认，全程自动执行。

支持的模型
服务商	默认模型	Base URL
DeepSeek 官方	deepseek-chat	https://api.deepseek.com
DeepSeek 本地	deepseek-r1:7b	http://localhost:11434/v1
Claude	claude-3-5-sonnet-20241022	https://api.anthropic.com/v1
OpenAI	gpt-4o	https://api.openai.com/v1
自定义	自填	自填
项目结构
src/
├── main.rs              # 入口
├── app.rs               # 应用主体，事件处理
├── llm.rs               # LLM API 调用
├── tools.rs             # IDAPython 脚本执行
├── types.rs             # 数据类型定义
└── views/
    ├── file_select.rs   # 初始配置界面
    └── chat.rs          # 对话界面
assets/
    ├── background.png   # 背景图
    ├── avatar_ai.png    # AI 头像
    └── avatar_user.png  # 用户头像
配置文件
配置自动保存在可执行文件同目录下的 ai_assistant_config.json：

{
  "provider": "DeepSeek",
  "api_key": "sk-xxx",
  "base_url": "https://api.deepseek.com",
  "model": "deepseek-chat",
  "ida_path": "D:\\IDA\\idat.exe"
}
```
