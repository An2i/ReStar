# CodeX 工作逻辑图与类对象关系图

本文档基于当前代码结构绘制，重点覆盖前端工作台、Task Pool、FastAPI 路由、后端服务对象、运行态数据和任务循环链路。

## 工作逻辑图

```mermaid
flowchart TD
    User["用户"] --> Browser["React Web 控制台<br/>frontend/src/main.jsx"]

    Browser --> StatusUI["状态管理<br/>平台/能力配置"]
    Browser --> WorkbenchUI["工作台<br/>程序分析入口"]
    Browser --> KnowledgeUI["知识库管理"]
    Browser --> ToolUI["工具管理"]
    Browser --> CapabilityUI["能力管理"]

    StatusUI --> StatusAPI["/api/status-modules<br/>/api/capability-types<br/>/api/pools"]
    CapabilityUI --> StatusAPI
    KnowledgeUI --> KnowledgeAPI["/api/knowledge-bases<br/>/api/knowledge-bases/query"]
    ToolUI --> ToolAPI["/api/tools<br/>/api/tool-system/execute"]
    WorkbenchUI --> ManagerAPI["/api/tasks<br/>/api/task-pool<br/>/api/manager/program-analysis"]

    StatusAPI --> StatusStore["status_store<br/>读写 status_configs.json"]
    StatusAPI --> PoolRegistry["pool_registry<br/>能力池注册表"]
    PoolRegistry --> Pool["Pool<br/>通用能力池"]
    PoolRegistry --> LLMPool["LLMPool<br/>LLM 平台调度/token 探测"]

    KnowledgeAPI --> KnowledgeStore["knowledge_store"]
    KnowledgeStore --> KnowledgeFiles["本地知识库文件夹<br/>.txt / .md"]
    KnowledgeStore --> Embeddings["LocalHashEmbeddings<br/>本地哈希向量"]
    KnowledgeStore --> KnowledgeRuntime["runtime/knowledge_vectors<br/>vectors.json / chroma"]
    KnowledgeStore --> KnowledgeConfig["runtime/knowledge_bases.json"]

    ToolAPI --> ToolStore["tool_store<br/>读写 tools.json"]
    ToolAPI --> ToolSystem["ToolSystem<br/>工具定义/执行/审计"]
    ToolSystem --> ToolRuntime["ToolRuntime<br/>文件读写/命令执行"]
    ToolSystem --> SandboxClient["SandboxClient<br/>沙箱工具安装/远程执行"]
    SandboxClient --> SandboxServer["Sandbox Server<br/>远程沙箱监听服务"]
    ToolSystem --> ToolAudit["runtime/tool_audit.jsonl"]

    ManagerAPI --> RequestManager["RequestManager<br/>接收请求并创建Task"]
    RequestManager --> TaskPool["TaskPool<br/>任务队列/后台worker"]
    TaskPool --> Task["Task<br/>SystemPrompt/UserPrompt/taskExecute/taskLoop"]
    Task --> SessionStorage["SessionStorage<br/>会话事件 JSONL"]
    Task --> MemoryManager["MemoryManager<br/>runtime/memory/MEMORY.md"]
    Task --> LLMPool
    Task --> ExternalLLM["外部 LLM API<br/>OpenAI/Claude/DeepSeek/Gemini"]
    Task --> ToolSystem
    Task --> TaskRuntime["runtime/tasks<br/>任务环境"]
    Task --> Report["runtime/reports/*.json<br/>任务报告"]
    Task --> Uploads["runtime/uploads<br/>上传样本/程序文件"]
```

## Task Pool 任务链路

```mermaid
sequenceDiagram
    actor U as 用户
    participant FE as React 工作台任务页
    participant API as FastAPI manager 路由
    participant RM as RequestManager
    participant TP as TaskPool
    participant T as Task
    participant SS as SessionStorage
    participant Pool as LLMPool
    participant LLM as LLM API
    participant TS as ToolSystem
    participant RT as ToolRuntime
    participant MM as MemoryManager

    U->>FE: 选择免杀生成/漏洞挖掘/样本分析/代码审计
    FE->>API: POST /api/tasks 或 /api/manager/program-analysis
    API->>RM: create_task / create_program_analysis_task
    RM->>TP: submit_task
    TP->>T: 创建Task并填充SystemPrompt/UserPrompt
    T->>SS: create_session + task_queued
    TP->>T: worker监测到任务后调用taskExecute
    T->>T: initialize_task_environment
    T->>Pool: select_platform + occupy
    loop taskLoop while not complete
        T->>T: 上下文压缩与折叠优化
        T->>LLM: 调用LLM决策
        LLM-->>T: complete 或 tool decision
        T->>TS: 根据决策调用工具
    TS->>RT: read_file / write_file / execute_command
    RT-->>TS: 工具执行结果
        TS->>SS: 写入 tool_use / tool_result 事件
        T->>T: 工具结果作为新提示词反馈给LLM
    end
    T->>TS: 写入 runtime/reports/*.json
    T->>SS: 记录 task_completed
    T->>Pool: release
    T->>MM: 写入任务 Memory
    RM-->>API: 返回分析报告
    API-->>FE: JSON 结果
    FE-->>U: 展示结果与导出 JSON
```

## 类对象关系图

```mermaid
classDiagram
    direction LR

    class FastAPIApp {
        <<application>>
        +create_app()
        +include_router()
        +mount_frontend_assets()
    }

    class StatusRoutes {
        <<router>>
        +get_status_modules()
        +create_status_module()
        +get_pools()
        +schedule_llm_platform()
    }

    class KnowledgeRoutes {
        <<router>>
        +create_knowledge_base()
        +query_knowledge_bases()
        +delete_knowledge_bases()
    }

    class ToolRoutes {
        <<router>>
        +get_tools()
        +create_tool()
        +execute_tool()
    }

    class ManagerRoutes {
        <<router>>
        +route_manager_request()
        +submit_program_analysis()
        +get_manager_sessions()
    }

    class RequestManager {
        +route_request(request)
        +create_task(task_type, payload, wait)
        +create_program_analysis_task(file_path, filename, type)
        +create_agent(session_id)
        +release_agent_llm(agent)
        +list_agents()
    }

    class TaskPool {
        +start()
        +stop()
        +worker_loop()
        +submit_task(task_type, payload)
        +get_task(task_id)
        +list_tasks()
        +wait_for_task(task_id, timeout)
        +snapshot()
    }

    class Task {
        +id
        +task_type
        +system_prompt
        +user_prompt
        +task_execute()
        +initialize_task_environment()
        +task_loop()
        +compress_context_if_needed()
        +fold_context_content()
        +call_llm_decision()
        +execute_decision_tool(decision)
    }

    class Agent {
        <<legacy compatible path>>
        +id
        +session_id
        +run_program_analysis(file_info, analysis_type)
        +llm_snapshot()
        +compose_program_analysis_result()
    }

    class LLMDecisionClient {
        +platform
        +provider
        +create_program_analysis_plan()
        +local_program_analysis_plan()
        +call_llm_for_plan()
        +normalize_llm_steps()
    }

    class Pool {
        +capability_type
        +platforms
        +occupied_counts
        +sync_platforms(platforms)
        +occupy(platform_id)
        +release(platform_id)
        +snapshot()
    }

    class LLMPool {
        +token_records
        +supported_providers
        +detect_provider(platform)
        +refresh_token_balances(force)
        +probe_token_balance(platform)
        +select_platform(estimated_tokens, provider)
    }

    class ToolSystem {
        +list_tools()
        +get_tool(tool_key)
        +execute(tool_key, arguments, task_type)
        +get_sandbox_client(task_type)
        +audit_event()
        +redact_arguments()
    }

    class SandboxClient {
        +health()
        +is_online()
        +ensure_tools_installed(tools)
        +execute_tool(tool, arguments, all_tools)
        +prepare_execution_payload(tool, arguments)
    }

    class ToolDefinitionRegistry {
        +list_definitions()
        +get_definition(tool_key)
        +describe_tool(tool)
    }

    class ToolDefinition {
        +id
        +name
        +command_line
        +input_schema
        +permission
        +runtime_traits
        +matches(tool_key)
        +to_dict()
    }

    class ToolRuntime {
        +execute(definition, arguments)
        +read_file(arguments)
        +write_file(arguments)
        +execute_command(arguments)
        +resolve_workspace_path(value)
    }

    class ToolRenderer {
        +render_tool_use(definition, arguments)
        +render_tool_result(definition, result)
        +render_error(definition, error)
    }

    class SessionStorage {
        +create_session(module, metadata)
        +append_event(session_id, event_type, payload)
        +read_events(session_id, limit)
        +list_sessions()
    }

    class MemoryManager {
        +add_record(title, content, tags, source)
        +list_records()
        +recall(query, limit)
        +context_for(query)
    }

    class PromptManager {
        +base_policy
        +build_program_analysis_prompt(file_info, type, tools, events)
    }

    class LocalHashEmbeddings {
        +dimensions
        +embed_documents(texts)
        +embed_query(text)
    }

    class StatusStore {
        <<module>>
        +load_status_state()
        +save_status_state()
    }

    class KnowledgeStore {
        <<module>>
        +build_knowledge_base_index()
        +query_json_vector_store()
        +remove_knowledge_vector_dir()
    }

    class ToolStore {
        <<module>>
        +load_tool_configs()
        +save_tool_configs()
        +ensure_default_tools()
    }

    FastAPIApp --> StatusRoutes
    FastAPIApp --> KnowledgeRoutes
    FastAPIApp --> ToolRoutes
    FastAPIApp --> ManagerRoutes

    StatusRoutes ..> StatusStore
    StatusRoutes ..> LLMPool
    StatusRoutes ..> Pool
    KnowledgeRoutes ..> KnowledgeStore
    KnowledgeStore ..> LocalHashEmbeddings
    ToolRoutes ..> ToolStore
    ToolRoutes ..> ToolSystem
    ManagerRoutes ..> RequestManager

    LLMPool --|> Pool

    RequestManager *-- ToolSystem
    RequestManager *-- SessionStorage
    RequestManager *-- TaskPool
    RequestManager *-- PromptManager
    RequestManager *-- MemoryManager
    RequestManager ..> LLMPool
    RequestManager ..> Agent : creates
    RequestManager ..> Task : submits

    TaskPool *-- Task
    TaskPool --> ToolSystem
    TaskPool --> SessionStorage
    TaskPool --> MemoryManager
    TaskPool --> LLMPool

    Task --> ToolSystem
    Task --> SessionStorage
    Task --> MemoryManager
    Task --> LLMPool

    Agent --> ToolSystem
    Agent --> SessionStorage
    Agent --> LLMPool
    Agent --> LLMDecisionClient

    LLMDecisionClient --> ToolSystem
    LLMDecisionClient --> PromptManager
    LLMDecisionClient --> LLMPool

    PromptManager --> MemoryManager

    ToolSystem *-- ToolDefinitionRegistry
    ToolSystem *-- ToolRuntime
    ToolSystem *-- ToolRenderer
    ToolSystem --> SandboxClient
    ToolDefinitionRegistry ..> ToolDefinition
    ToolRuntime ..> ToolDefinition
    ToolRenderer ..> ToolDefinition
```

## 图例说明

- `runtime/` 是当前平台的本地持久化中心，保存配置、会话、上传文件、报告、工具审计、Task运行目录和 Memory。
- `state.py` 在应用启动时组装全局对象，包括 `TaskPool`、`RequestManager`、`ToolSystem`、`SessionStorage`、`MemoryManager` 和 LLM 池。
- 能力类型为 `沙箱` 且在线时，`样本分析` 和 `漏洞挖掘` 任务中的工具调用会经由 `SandboxClient` 转发到远程 `sandbox_server.py`。
- 前端目前主要是 React 函数组件，不是类组件；“类对象关系图”重点展示后端服务类、路由模块和存储模块之间的关系。
