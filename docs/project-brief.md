# CodeX 项目简报

## 1. 项目定位

CodeX 不是一个普通的聊天式 AI 页面，而是一个面向安全分析 / 逆向分析场景的任务执行平台。

它的核心思路是：

- 用前端工作台承接不同分析任务
- 用后端 Task Pool 把任务变成可调度的执行单元
- 用 LLM 平台池给任务分配合适模型
- 用 Tool System 让模型按工具协议读取文件、搜索代码、执行命令、生成报告
- 用 runtime 目录保存上传样本、会话轨迹、工具审计、知识库索引和最终报告

从现有实现来看，这个平台已经具备“AI Agent 编排器”的雏形，重点不是单次问答，而是围绕逆向 / 漏洞 / 样本场景做半自动分析闭环。

## 2. 当前支持的任务类型

前端工作台中已经定义了 4 类任务：

- `evasion-generation`
  - 免杀生成 / 对抗策略规划类任务
- `vulnerability-mining`
  - 漏洞挖掘，偏目标程序与输入面分析
- `sample-analysis`
  - 样本分析，偏恶意样本静态 / 行为分析
- `code-audit`
  - 代码审计，偏源码级风险识别

其中：

- `sample-analysis` 和 `vulnerability-mining` 走上传文件分析入口
- `evasion-generation` 和 `code-audit` 走普通任务提交入口

## 3. 总体架构

项目由 3 层组成：

### 前端层

目录：`frontend/`

技术栈：

- React 18
- Vite
- lucide-react

职责：

- 平台能力管理
- 工作台任务发起
- 知识库管理
- 工具管理
- 任务结果展示
- 报告导出

当前前端是一个单文件偏重型实现，`frontend/src/main.jsx` 同时承载多个页面和大量状态逻辑。

### 后端层

目录：`backend/`

技术栈：

- FastAPI
- 自定义任务池
- 自定义工具系统
- 自定义 LLM 调度层

入口：

- `backend/main.py`

职责：

- 提供任务、工具、知识库、能力平台的 API
- 启动 Task Pool 和 LLM 刷新后台线程
- 管理上传文件、会话事件、报告输出

### 运行时数据层

目录：`runtime/`

主要内容：

- `runtime/uploads`：上传的程序样本
- `runtime/reports`：生成的 HTML 报告
- `runtime/sessions`：会话 / 任务事件 JSONL
- `runtime/tool_audit.jsonl`：工具调用审计
- `runtime/tools.json`：工具配置
- `runtime/status_configs.json`：平台能力配置
- `runtime/knowledge_bases.json`：知识库配置
- `runtime/memory/MEMORY.md`：项目级长期记忆

这说明你已经把“平台配置”和“任务结果”从代码中分离，设计方向是对的。

## 4. 核心执行链路

### 4.1 应用启动

`backend/main.py` 创建 FastAPI 应用，并挂载：

- `health`
- `manager`
- `tools`
- `status`
- `knowledge`
- 前端静态资源

### 4.2 全局状态装配

`backend/state.py` 是项目的核心装配点，初始化了：

- 状态模块配置 `status_modules`
- 能力类型 `capability_types`
- 工具配置 `tool_configs`
- `LLMRegistryManager`
- `ToolSystem`
- `TaskPool`
- `RequestManager`
- `SessionStorage`
- `MemoryManager`
- `PromptManager`

可以把它理解成整个平台的“服务容器”。

### 4.3 任务提交与执行

任务主链路在：

- `backend/routes/manager.py`
- `backend/services/agent.py`
- `backend/services/tasks.py`

执行流程大致是：

1. 前端提交任务或上传样本
2. `RequestManager` 统一接住请求
3. 创建 `Task`
4. `TaskPool` 将任务放入队列
5. worker 线程异步执行 `task.task_execute()`
6. `Task` 申请 LLM 资源
7. 进入 task loop
8. LLM 产出决策或工具调用
9. `ToolSystem` 执行工具
10. 工具结果回灌到上下文
11. 输出最终报告并写入会话 / 审计 / runtime

这个设计已经明显具备 agent orchestration 的模式。

## 5. LLM 调度设计

关键文件：

- `backend/services/llm_models.py`

当前实现里，LLM 不只是一个固定接口，而是“平台池”：

- `LLMPool` 负责管理可用平台
- 支持 provider 识别：
  - OpenAI
  - Claude
  - DeepSeek
  - Gemini
- `ModelManager` 负责为单个任务分配模型资源
- 支持 token 余额刷新与平台占用 / 释放

这说明你的设计目标不是绑定某一个模型，而是要做多模型调度层。

这部分很关键，也是平台可扩展性的基础。

## 6. 工具系统设计

关键文件：

- `backend/services/tool_system.py`
- `backend/services/tool_runtime.py`
- `backend/stores/tool_store.py`

当前工具系统分成三层：

- Definition：工具定义、权限、输入 schema
- Runtime：真正执行读写 / 搜索 / 命令
- Renderer / Audit：把工具调用变成结构化记录

默认内置工具已经比较完整：

- `Read`
- `Write`
- `Edit`
- `Glob`
- `Grep`
- `Bash`
- `PowerShell`
- `WebFetch`
- `WebSearch`

其中 `ToolRuntime` 还做了工作区边界限制：

- 路径必须落在当前项目工作区内
- 读写和命令执行经过统一入口

这说明你已经在尝试给 agent 建立安全边界，而不是直接放任执行。

## 7. 沙箱执行设计

关键文件：

- `backend/services/tool_system.py`
- `backend/services/sandbox_client.py`
- `scripts/sandbox_server.py`
- `docs/sandbox.md`

目前沙箱能力的思路是：

- 将“沙箱”抽象成一种能力类型
- 如果某些任务类型需要隔离执行，就优先走 sandbox client
- 远程 sandbox server 提供工具检查、安装、执行接口

按现有逻辑，沙箱主要面向：

- 样本分析
- 漏洞挖掘

这很符合逆向平台的真实需求，因为这两类任务天然更适合隔离环境。

## 8. 知识库设计

关键文件：

- `backend/routes/knowledge.py`
- `backend/stores/knowledge_store.py`
- `backend/embeddings.py`

知识库的核心流程是：

1. 指定一个本地目录
2. 收集 `.txt` / `.md` 文件
3. 切分 chunk
4. 生成本地 embedding
5. 写入 `runtime/knowledge_vectors`
6. 查询时走本地向量检索

当前支持两种落地方式：

- 本地 JSON 向量存储
- Chroma（如果环境可用）

这说明你已经在为“领域知识增强分析”打基础，未来可以把漏洞知识、恶意样本家族特征、逆向经验沉淀进去。

## 9. 会话与记忆设计

关键文件：

- `backend/services/session_memory.py`

这里分成两类：

- `SessionStorage`
  - 保存每次任务事件流
  - 格式是 JSONL
- `MemoryManager`
  - 保存项目级长期记忆
  - 当前落地在 `runtime/memory/MEMORY.md`

这意味着平台已经不是“无状态”的。

你的目标明显是让 agent：

- 记住任务过程
- 复用历史经验
- 在 prompt 构造时引入上下文和项目知识

## 10. 我对项目思路的理解

如果用一句话概括，这个项目是在做：

“一个面向逆向、安全分析与样本处理场景的本地化 AI Agent 平台，用可配置 LLM、工具系统、任务池、知识库和沙箱，把分析任务流程化、平台化。”

它的目标用户更像是：

- 逆向分析人员
- 漏洞研究人员
- 恶意样本分析人员
- 安全研发或内部红队

而不是普通 C 端聊天用户。

## 11. 当前项目的优势

从现有代码看，已经有几项非常不错的方向：

- 架构思路是对的
  - 前后端、任务、工具、状态、运行时数据已经分层
- 有平台意识
  - 不是只写一个 agent，而是在写平台底座
- 有多模型调度意识
  - 后期接入更多模型成本不高
- 有工具审计意识
  - `tool_audit.jsonl` 很重要
- 有沙箱意识
  - 对逆向类任务很关键
- 有知识库与长期记忆意识
  - 为后续智能化增强留了扩展点

## 12. 当前明显的短板

这部分是我看完后最真实的判断。

### 12.1 前端文件过大

`frontend/src/main.jsx` 体积很大，页面、状态、请求、弹窗、任务视图都混在一起。

问题：

- 难维护
- 难复用
- 后续加模块会变慢

### 12.2 后端存在“新任务池”和“旧 Agent 兼容层”并存

`RequestManager` 里既支持 `TaskPool`，又保留 legacy agent 路径。

问题：

- 代码心智负担大
- 容易出现两套执行逻辑分叉
- 后期 bug 排查成本高

### 12.3 任务 prompt 很重，但任务结果结构化还不够

当前报告主要还是大段文本输出，虽然已经有 `tool_results`、`summary`、`llm` 信息，但缺少更稳定的结构化字段，比如：

- 风险评级枚举
- IOC 列表
- 漏洞列表
- 证据列表
- MITRE 映射

这会限制后续检索、聚合和可视化。

### 12.4 工具安全边界还需要继续加强

虽然已经有工作区路径限制和沙箱设计，但如果未来要让平台更稳定，仍建议继续细化：

- 按任务类型限制工具白名单
- 按工具限制参数范围
- 区分只读工具和高风险工具
- 加更明确的超时 / 输出截断 / 资源配额

### 12.5 编码与文本展示有潜在问题

我在终端读取部分中文文件时，出现了明显乱码表现，可能是：

- 文件编码不统一
- 终端编码与源文件编码不一致

这不一定影响程序运行，但会影响维护、调试和协作体验，值得尽快统一。

### 12.6 缺少项目级入口文档

目前仓库里没有一个清晰的 README 来说明：

- 项目是什么
- 怎么启动
- 目录结构
- API 入口
- 任务链路
- 如何接入 LLM 平台 / 沙箱 / 知识库

这会显著提高新协作者理解成本。

## 13. 我建议的优先优化顺序

如果我们接下来一起完善项目，我建议按这个顺序推进：

### 第一阶段：稳住基础设施

- 补 README 和部署说明
- 统一编码与文本规范
- 盘点 runtime 配置文件格式
- 明确哪些逻辑已经废弃，收敛 legacy path

### 第二阶段：收敛核心后端链路

- 明确 TaskPool 是唯一主执行路径
- 拆分 Task 的 prompt、决策、报告、工具执行逻辑
- 给任务结果补充结构化输出 schema

### 第三阶段：整理前端

- 按页面拆分组件
- 抽离 API 层
- 抽离公共状态和通用弹窗
- 优化任务结果展示和历史检索

### 第四阶段：增强逆向能力

- 增加更专业的样本分析工具适配
- 增加证据提取与报告模板
- 强化沙箱联动
- 引入知识库检索增强分析

## 14. 结论

这个项目已经不是“想法阶段”，而是一个已经搭出主骨架的 AI 安全分析平台。

它现在最有价值的地方在于：

- 主体架构方向正确
- 核心闭环已经存在
- 后续扩展空间很大

它现在最需要的，不是推倒重来，而是：

- 收敛架构
- 提高可维护性
- 强化结构化输出
- 让逆向 / 漏洞分析能力更加专业化

只要把这几个关键点打磨好，这个项目是可以继续长成一个很像样的平台的。
