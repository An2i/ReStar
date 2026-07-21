# ReStar Platform

ReStar 是一个面向安全分析工作流的本地 Web 平台。项目由 FastAPI 后端和 React/Vite 前端组成，用任务池、LLM 平台池、工具系统、知识库、Skills、远程沙箱和报告生成能力，把样本分析、漏洞挖掘、代码审计等任务组织成可追踪的半自动分析流程。

> 本项目适用于授权安全研究、样本分析、漏洞验证和内部工具编排场景。请勿用于未授权目标。

## 核心能力

- **任务工作台**：支持免杀生成、漏洞挖掘、样本分析、代码审计等任务类型。
- **Task Pool**：后端异步执行任务，前端可查看排队、运行、完成和失败状态。
- **LLM 平台池**：可配置多个 LLM 平台 URL、模型和 API Key，并在任务执行时调度使用。
- **工具系统**：支持内置工具和自定义外部工具，可配置命令模板、输入 schema、本地或沙箱执行方式。
- **远程沙箱**：样本分析和漏洞挖掘任务可优先把高风险工具调用转发到远程沙箱服务。
- **知识库检索**：导入本地目录，构建向量索引，任务执行时可检索相关知识。
- **Skills**：通过 Markdown 技能和关键词匹配，为任务注入专用分析提示。
- **威胁情报接入**：可配置威胁情报平台，基于文件哈希查询并融合到样本分析报告。
- **结构化报告**：任务结果会保存结构化报告、LLM 分析、工具轨迹和 HTML 报告。

## 技术栈

- 后端：Python 3、FastAPI、Uvicorn
- 前端：React 18、Vite、lucide-react
- LLM/检索：OpenAI SDK、LangChain、Chroma 相关组件
- 运行数据：默认保存在 `runtime/` 下的 JSON、JSONL、HTML 和向量索引文件

## 项目结构

```text
CodeX/
├── backend/                 # FastAPI 后端
│   ├── main.py              # 应用入口
│   ├── config.py            # 路径与能力类型配置
│   ├── routes/              # API 路由
│   ├── services/            # 任务、工具、LLM、报告、沙箱、技能等核心服务
│   └── stores/              # 本地配置与状态持久化
├── frontend/                # React/Vite 前端
│   ├── src/main.jsx         # 前端主应用
│   ├── src/styles.css       # 页面样式
│   └── package.json
├── scripts/
│   └── sandbox_server.py    # 可部署到远程环境的沙箱服务
├── docs/                    # 架构与功能文档
├── runtime/                 # 运行时数据、会话、报告、工具配置等
└── requirements.txt         # Python 依赖
```

## 快速启动

以下命令同时适用于 Windows、macOS 与 Linux。虚拟环境激活命令按系统选择即可。

### 1. 安装后端依赖

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
```

macOS / Linux：
```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
```

### 2. 安装前端依赖

```powershell
cd frontend
npm install
cd ..
```

### 3. 开发模式启动

后端：

```powershell
.\.venv\Scripts\Activate.ps1
uvicorn backend.main:app --reload --host 127.0.0.1 --port 8000
```

macOS / Linux：
```bash
source .venv/bin/activate
uvicorn backend.main:app --reload --host 127.0.0.1 --port 8000
```

前端：

```bash
cd frontend
npm run dev
```

默认前端地址：

```text
http://127.0.0.1:5173
```

### 4. 生产构建与后端托管

```bash
cd frontend
npm run build
cd ..
uvicorn backend.main:app --host 127.0.0.1 --port 8000
```

构建后的前端文件位于 `frontend/dist/`，后端会挂载并提供访问。

### 5. 平台兼容说明

- Web 后端、前端、任务池、知识库、报告生成和 Bash/通用命令工具支持 Windows、macOS 与 Linux。
- PowerShell 工具在 Windows 上可直接使用；在 macOS/Linux 上需要先安装 PowerShell Core，并确保 `pwsh` 或 `powershell` 在 `PATH` 中。
- Windows Debugging Tools / `cdb` 属于 Windows-only 工具；如需在 macOS/Linux 主机分析 Windows 样本，建议通过远程 Windows 沙箱接入。
- 路径配置建议使用当前系统的原生路径。项目内部会尽量使用 `pathlib` 处理路径，报告 URL 中会自动把反斜杠标准化。

## 基础配置

平台配置主要通过前端页面完成，持久化文件位于 `runtime/`。

常见文件：

```text
runtime/status_configs.json      # LLM、沙箱、威胁情报等能力平台配置
runtime/tools.json               # 工具配置
runtime/skills.json              # Skills 配置
runtime/knowledge_bases.json     # 知识库配置
runtime/sessions/                # 会话、任务事件和任务快照
runtime/reports/                 # HTML 报告
runtime/uploads/                 # 任务上传文件
runtime/memory/MEMORY.md         # 长期记忆记录
runtime/tool_audit.jsonl         # 工具调用审计
```

首次运行时，部分配置文件会在需要时自动创建。

## 配置 LLM 平台

1. 打开前端页面。
2. 进入“能力管理”。
3. 添加或编辑 `LLM 平台` 类型的平台。
4. 填写 API URL、Model、API Key。
5. 保存后，任务调度会从在线平台中分配 LLM。

## 配置工具

工具管理支持内置工具和自定义工具。

自定义工具主要字段：

- `name`：工具名称
- `command_line`：本地命令模板
- `sandbox_command_line`：沙箱环境中的命令模板，可选
- `description`：给任务循环使用的工具说明
- `input_schema`：工具参数 schema

工具调用会记录到会话事件和 `runtime/tool_audit.jsonl`，便于回看分析过程。

## 配置远程沙箱

沙箱适合执行样本分析、漏洞挖掘等高风险工具调用。

在沙箱主机上运行：

```powershell
python scripts/sandbox_server.py --host 0.0.0.0 --port 8765 --root C:\codex_sandbox --token your-token
```

macOS / Linux：
```bash
python scripts/sandbox_server.py --host 0.0.0.0 --port 8765 --root /tmp/codex_sandbox --token your-token
```

然后在前端“能力管理”中：

1. 添加能力类型 `沙箱`。
2. 添加该类型的平台。
3. URL 填写沙箱地址，例如 `http://127.0.0.1:8765`。
4. 如启动时设置了 token，将同一个值填入 API Key 或 Token。

沙箱服务提供：

- `GET /health`
- `POST /tools/check`
- `POST /tools/install`
- `POST /tools/execute`

如果没有在线沙箱，工具系统会回退到本地执行逻辑。

## 常用 API

任务与会话：

- `POST /api/tasks`
- `GET /api/tasks`
- `GET /api/tasks/{task_id}`
- `GET /api/task-pool`
- `POST /api/manager/program-analysis`
- `GET /api/manager/sessions/{session_id}/events`

能力管理：

- `GET /api/capability-types`
- `POST /api/capability-types`
- `GET /api/status-modules`
- `POST /api/status-modules`
- `PUT /api/status-modules/{module_id}`
- `POST /api/status-modules/{module_id}/probe`
- `DELETE /api/status-modules/{module_id}`

工具：

- `GET /api/tools`
- `POST /api/tools`
- `PUT /api/tools/{tool_id}`
- `DELETE /api/tools/{tool_id}`
- `GET /api/tool-system/tools`
- `POST /api/tool-system/execute`

知识库：

- `GET /api/knowledge-bases`
- `POST /api/knowledge-bases`
- `DELETE /api/knowledge-bases`
- `POST /api/knowledge-bases/query`

Skills：

- `GET /api/skills`
- `POST /api/skills`
- `POST /api/skills/import`
- `PUT /api/skills/{skill_id}`
- `DELETE /api/skills/{skill_id}`

## 开发检查

后端语法检查：

```powershell
.\.venv\Scripts\python -m compileall backend scripts
```

macOS / Linux：
```bash
python -m compileall backend scripts
```

前端构建：

```bash
cd frontend
npm run build
```

前端预览：

```bash
cd frontend
npm run preview
```

## 安全注意事项

- 分析未知样本时，优先配置远程沙箱执行工具。
- 不要在生产或办公主机上直接运行不可信样本。
- 自定义工具命令会被任务系统调用，添加前请确认命令模板和参数来源。
- LLM API Key、威胁情报 API Key 等敏感信息保存在本地 `runtime/` 配置中，请妥善保护。
- 本平台面向授权场景，请勿对未授权系统进行测试或攻击。

## 故障排查

### 前端页面空白或资源 404

先构建前端：

```powershell
cd frontend
npm run build
```

再启动后端：

```powershell
uvicorn backend.main:app --host 127.0.0.1 --port 8000
```

### LLM 任务无法启动

检查“能力管理”中是否配置了在线的 `LLM 平台`，并确认 URL、模型名和 API Key 正确。

### 工具调用失败

检查：

- 工具命令模板是否正确。
- 参数 schema 是否与任务调用参数一致。
- 本地或沙箱环境是否安装对应工具。
- `runtime/tool_audit.jsonl` 和会话事件中的错误信息。

### 沙箱不可用

检查：

- 沙箱服务是否启动。
- URL 是否能访问 `/health`。
- Token 是否一致。
- 防火墙是否允许访问沙箱端口。

## 相关文档

- [沙箱执行说明](docs/sandbox.md)
- [架构图](docs/architecture-diagrams.md)
- [项目简报](docs/project-brief.md)
