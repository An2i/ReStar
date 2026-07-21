import React from "react";
import ReactDOM from "react-dom/client";
import {
  Activity,
  AlertTriangle,
  Archive,
  Ban,
  BookOpen,
  BrainCircuit,
  Bug,
  CalendarDays,
  ChevronLeft,
  CheckSquare,
  Cookie,
  Database,
  Download,
  FileCode2,
  FileText,
  FolderOpen,
  Gauge,
  Hammer,
  Hash,
  History,
  KeyRound,
  Layers3,
  LayoutDashboard,
  Link,
  Pencil,
  Plus,
  PlugZap,
  RefreshCw,
  Save,
  ScanSearch,
  ServerCog,
  Settings,
  ShieldAlert,
  ShieldCheck,
  Square,
  Trash2,
  UploadCloud,
  Wrench,
  X,
} from "lucide-react";
import "./styles.css";

const defaultCapabilityType = "LLM 平台";

const navigation = [
  { id: "status", label: "状态管理", icon: Activity },
  { id: "workspace", label: "工作台", icon: LayoutDashboard },
  { id: "history", label: "历史记录", icon: History },
  { id: "knowledge", label: "知识库", icon: BookOpen },
  { id: "skills", label: "Skills管理", icon: Hammer },
  { id: "tools", label: "工具管理", icon: Wrench },
  { id: "capabilities", label: "能力管理", icon: BrainCircuit },
];

const workbenchModules = [
  {
    id: "evasion-generation",
    taskType: "evasion-generation",
    name: "免杀生成",
    description: "策略规划与样本处理任务",
    icon: ShieldCheck,
    requiresFile: false,
  },
  {
    id: "vulnerability-mining",
    taskType: "vulnerability-mining",
    name: "漏洞挖掘",
    description: "目标程序与输入面分析",
    icon: ScanSearch,
    requiresFile: true,
  },
  {
    id: "sample-analysis",
    taskType: "sample-analysis",
    name: "样本分析",
    description: "样本元数据与静态特征分析",
    icon: Bug,
    requiresFile: true,
  },
  {
    id: "code-audit",
    taskType: "code-audit",
    name: "代码审计",
    description: "源码结构与风险点审计",
    icon: FileCode2,
    requiresFile: false,
  },
];

const placeholderModules = {
  skills: ["技能列表", "技能详情", "安装入口", "版本管理"],
  tools: ["工具注册", "权限配置", "调用日志", "健康检查"],
};

const fileInfoFields = [
  { label: "文件名", value: "待上传文件", icon: FileText },
  { label: "文件创建日期", value: "待识别", icon: CalendarDays },
  { label: "文件修改日期", value: "待识别", icon: CalendarDays },
  { label: "文件MD5", value: "待计算", icon: Hash, mono: true },
  { label: "文件SHA256", value: "待计算", icon: Hash, mono: true },
];

function App() {
  const [selected, setSelected] = React.useState("status");
  const [activeWorkbenchEntry, setActiveWorkbenchEntry] = React.useState(null);

  const selectedItem = navigation.find((item) => item.id === selected);
  const activeTaskModule = workbenchModules.find(
    (item) => item.id === activeWorkbenchEntry?.moduleId,
  );
  const headerTitle =
    selected === "workspace" && activeTaskModule
        ? activeTaskModule.name
        : selectedItem?.label;

  const handleSelect = (id) => {
    setSelected(id);
    if (id !== "workspace") {
      setActiveWorkbenchEntry(null);
    }
  };

  return (
    <main className="app-shell">
      <aside className="sidebar" aria-label="功能栏">
        <div className="brand-block">
          <div className="brand-mark">CX</div>
          <div>
            <p className="brand-name">ReStar AI 逆向</p>
              <p className="brand-subtitle">Web 控制台</p>
          </div>
        </div>

        <nav className="nav-list">
          {navigation.map((item) => {
            const Icon = item.icon;
            const active = item.id === selected;

            return (
              <button
                className={`nav-item ${active ? "active" : ""}`}
                key={item.id}
                type="button"
                onClick={() => handleSelect(item.id)}
                aria-current={active ? "page" : undefined}
                title={item.label}
              >
                <Icon size={19} strokeWidth={2.2} aria-hidden="true" />
                <span>{item.label}</span>
              </button>
            );
          })}
        </nav>
      </aside>

      <section className="content-pane">
        <header className="content-header">
          <div>
            <h1>{headerTitle}</h1>
          </div>
        </header>

        <ContentView
          activeWorkbenchEntry={activeWorkbenchEntry}
          selected={selected}
          setActiveWorkbenchEntry={setActiveWorkbenchEntry}
          setSelected={setSelected}
        />
      </section>
    </main>
  );
}

function ContentView({
  activeWorkbenchEntry,
  selected,
  setActiveWorkbenchEntry,
  setSelected,
}) {
  if (selected === "status") {
    return <StatusModuleManager />;
  }

  if (selected === "workspace") {
    const taskModule = workbenchModules.find(
      (item) => item.id === activeWorkbenchEntry?.moduleId,
    );
    if (taskModule) {
      return (
        <TaskExecutionView
          module={taskModule}
          initialTask={
            activeWorkbenchEntry?.taskRecord
              ? mergeTaskResultPayload(activeWorkbenchEntry.taskRecord, null)
              : null
          }
          onBack={() => setActiveWorkbenchEntry(null)}
        />
      );
    }

    return (
      <WorkbenchView
        onOpenTask={(moduleId) => setActiveWorkbenchEntry({ moduleId, taskRecord: null })}
        onOpenTaskRecord={(taskRecord) => {
          const module = getWorkbenchModuleByTaskType(taskRecord?.task_type);
          if (!module) {
            return;
          }
          setActiveWorkbenchEntry({ moduleId: module.id, taskRecord });
        }}
      />
    );
  }

  if (selected === "knowledge") {
    return <KnowledgeBaseView />;
  }

  if (selected === "skills") {
    return <SkillsManagementView />;
  }

  if (selected === "history") {
    return (
      <TaskHistoryView
        onOpenTaskRecord={(taskRecord) => {
          const module = getWorkbenchModuleByTaskType(taskRecord?.task_type);
          if (!module) {
            return;
          }
          setSelected("workspace");
          setActiveWorkbenchEntry({ moduleId: module.id, taskRecord });
        }}
      />
    );
  }

  if (selected === "tools") {
    return <ToolManagementView />;
  }

  if (selected === "capabilities") {
    return <CapabilityManagementView />;
  }

  return <PlaceholderView selected={selected} />;
}

function getCapabilityIcon(capabilityType) {
  return capabilityType === defaultCapabilityType ? PlugZap : ServerCog;
}

async function readToolApiJson(response, fallbackMessage) {
  const contentType = response.headers.get("content-type") ?? "";
  if (!contentType.includes("application/json")) {
    const text = await response.text().catch(() => "");
    const looksLikeHtml = text.trim().toLowerCase().startsWith("<!doctype") || text.includes("<html");
    throw new Error(
      looksLikeHtml
        ? "工具管理 API 未加载，请重启 localhost:8083 后端服务"
        : fallbackMessage,
    );
  }

  return response.json();
}

function schemaToParamRows(schema) {
  const properties =
    schema && typeof schema === "object" && schema.properties && typeof schema.properties === "object"
      ? schema.properties
      : {};
  return Object.entries(properties).map(([name, config]) => {
    const field = config && typeof config === "object" ? config : {};
    return {
      name,
      type: ["string", "integer", "boolean"].includes(field.type) ? field.type : "string",
      defaultValue:
        field.default === undefined || field.default === null ? "" : String(field.default),
      description: String(field.description || ""),
    };
  });
}

function validateSchemaParamRows(rows) {
  const names = new Set();
  for (const row of Array.isArray(rows) ? rows : []) {
    const name = String(row.name || "").trim();
    const type = String(row.type || "").trim();
    const description = String(row.description || "").trim();
    if (!name || !type || !description) {
      return "Input Schema 参数名、类型和描述为必填项";
    }
    if (!/^[A-Za-z_][A-Za-z0-9_]*$/.test(name)) {
      return "Input Schema 参数名只能包含字母、数字和下划线，且不能以数字开头";
    }
    if (names.has(name)) {
      return `Input Schema 参数重复：${name}`;
    }
    names.add(name);
    if (!["string", "integer", "boolean"].includes(type)) {
      return "Input Schema 参数类型只能是 string、integer 或 boolean";
    }
    if (type === "integer" && String(row.defaultValue || "").trim()) {
      const parsed = Number(row.defaultValue);
      if (!Number.isInteger(parsed)) {
        return `Input Schema 参数 ${name} 的默认值必须是整数`;
      }
    }
    if (
      type === "boolean" &&
      String(row.defaultValue || "").trim() &&
      !["true", "false"].includes(String(row.defaultValue).trim().toLowerCase())
    ) {
      return `Input Schema 参数 ${name} 的默认值必须是 true 或 false`;
    }
  }
  return "";
}

function paramRowsToInputSchema(rows) {
  const properties = {};
  const required = [];
  for (const row of Array.isArray(rows) ? rows : []) {
    const name = String(row.name || "").trim();
    if (!name) {
      continue;
    }
    const type = ["string", "integer", "boolean"].includes(row.type)
      ? row.type
      : "string";
    const property = {
      type,
      description: String(row.description || "").trim(),
    };
    const defaultText = String(row.defaultValue ?? "").trim();
    if (defaultText) {
      if (type === "integer") {
        property.default = Number(defaultText);
      } else if (type === "boolean") {
        property.default = defaultText.toLowerCase() === "true";
      } else {
        property.default = defaultText;
      }
    } else if (name !== "log_path") {
      required.push(name);
    }
    properties[name] = property;
  }
  if (!Object.keys(properties).length) {
    return {};
  }
  return {
    type: "object",
    required,
    properties,
  };
}

function StatusModuleManager() {
  const emptyForm = {
    capability_type: defaultCapabilityType,
    name: "",
    url: "",
    model: "",
    api_key: "",
    token: "",
    cookie: "",
  };
  const [modules, setModules] = React.useState([]);
  const [capabilityTypes, setCapabilityTypes] = React.useState([]);
  const [form, setForm] = React.useState(emptyForm);
  const [dialogOpen, setDialogOpen] = React.useState(false);
  const [editingModule, setEditingModule] = React.useState(null);
  const [deleteMode, setDeleteMode] = React.useState(false);
  const [message, setMessage] = React.useState("");
  const [loading, setLoading] = React.useState(true);
  const [saving, setSaving] = React.useState(false);
  const [deletingId, setDeletingId] = React.useState("");
  const [probingId, setProbingId] = React.useState("");

  const loadModules = React.useCallback(async () => {
    setLoading(true);

    try {
      const [moduleResponse, capabilityResponse] = await Promise.all([
        fetch("/api/status-modules"),
        fetch("/api/capability-types"),
      ]);
      if (!moduleResponse.ok || !capabilityResponse.ok) {
        throw new Error("状态模块读取失败");
      }

      const moduleData = await moduleResponse.json();
      const capabilityData = await capabilityResponse.json();
      setModules(moduleData);
      setCapabilityTypes(capabilityData);
      const nextDefault =
        capabilityData.find((item) => item.name === defaultCapabilityType)?.name ??
        capabilityData[0]?.name ??
        defaultCapabilityType;
      setForm((current) => ({
        ...current,
        capability_type: capabilityData.some((item) => item.name === current.capability_type)
          ? current.capability_type
          : nextDefault,
      }));
      if (moduleData.length === 0) {
        setDeleteMode(false);
      }
    } catch (error) {
        setMessage(error.message || "状态模块读取失败");
    } finally {
      setLoading(false);
    }
  }, []);

  React.useEffect(() => {
    loadModules();
  }, [loadModules]);

  const updateField = (field, value) => {
    setForm((current) => ({ ...current, [field]: value }));
  };

  const openCreateDialog = () => {
    const fallbackCapability =
      capabilityTypes.find((item) => item.name === defaultCapabilityType)?.name ??
      capabilityTypes[0]?.name ??
      defaultCapabilityType;
    setEditingModule(null);
    setForm({ ...emptyForm, capability_type: fallbackCapability });
    setDialogOpen(true);
  };

  const openEditDialog = (module) => {
    setEditingModule(module);
    setForm({
      capability_type: module.capability_type ?? defaultCapabilityType,
      name: module.name ?? "",
      url: module.url ?? "",
      model: module.model ?? "",
      api_key: module.api_key ?? "",
      token: module.token ?? "",
      cookie: module.cookie ?? "",
    });
    setDialogOpen(true);
  };

  const closeDialog = () => {
    setDialogOpen(false);
    setEditingModule(null);
    setForm(emptyForm);
  };

  const handleSave = async (event) => {
    event.preventDefault();
    setMessage("");

    if (!form.capability_type || !form.name.trim() || !form.url.trim()) {
      setMessage("能力类型、模块功能名称和 URL 为必填项");
      return;
    }

    setSaving(true);

    try {
      const response = await fetch(
        editingModule ? `/api/status-modules/${editingModule.id}` : "/api/status-modules",
        {
          method: editingModule ? "PUT" : "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(form),
        },
      );

      if (!response.ok) {
        const errorBody = await response.json().catch(() => ({}));
        throw new Error(
          errorBody.detail?.[0]?.msg ||
            errorBody.detail ||
            (editingModule ? "平台信息更新失败" : "模块功能添加失败"),
        );
      }

      const saved = await response.json();
      setModules((current) =>
        editingModule
          ? current.map((module) => (module.id === saved.id ? saved : module))
          : [saved, ...current],
      );
      closeDialog();
      setMessage(
        editingModule
          ? "平台信息已更新，本地配置文件和内存缓存已同步"
          : "模块功能已添加，本地配置文件和内存缓存已更新",
      );
    } catch (error) {
      setMessage(error.message || (editingModule ? "平台信息更新失败" : "模块功能添加失败"));
    } finally {
      setSaving(false);
    }
  };

  const handleDelete = async (moduleId) => {
    setDeletingId(moduleId);
    setMessage("");

    try {
      const response = await fetch(`/api/status-modules/${moduleId}`, {
        method: "DELETE",
        headers: { "Content-Type": "application/json" },
      });

      if (!response.ok) {
        const errorBody = await response.json().catch(() => ({}));
        throw new Error(errorBody.detail || "模块功能删除失败");
      }

      setModules((current) => {
        const next = current.filter((module) => module.id !== moduleId);
        if (next.length === 0) {
          setDeleteMode(false);
        }
        return next;
      });
      setMessage("模块功能已删除，本地配置文件和内存缓存已更新");
    } catch (error) {
      setMessage(error.message || "模块功能删除失败");
    } finally {
      setDeletingId("");
    }
  };

  const handleProbe = async (moduleId) => {
    setProbingId(moduleId);
    setMessage("");

    try {
      const response = await fetch(`/api/status-modules/${moduleId}/probe`, {
        method: "POST",
      });
      const body = await response.json().catch(() => ({}));
      if (!response.ok) {
        throw new Error(body.detail || "访问测试失败");
      }
      setModules((current) =>
        current.map((module) => (module.id === moduleId ? body : module)),
      );
      setMessage(body.status === "online" ? "访问测试通过" : "访问测试未通过");
    } catch (error) {
      setMessage(error.message || "访问测试失败");
    } finally {
      setProbingId("");
    }
  };

  return (
    <section className="status-manager">
      <div className="status-manager-toolbar">
        <button
          className={`delete-button ${deleteMode ? "active" : ""}`}
          type="button"
          onClick={() => setDeleteMode((current) => !current)}
          disabled={modules.length === 0}
        >
          <Trash2 size={18} strokeWidth={2.2} aria-hidden="true" />
          删除
        </button>
      </div>

      <section className="module-grid" aria-label="状态模块功能列表">
        {modules.map((module) => {
          const Icon = getCapabilityIcon(module.capability_type);
          const hasAuth = Boolean(module.api_key || module.token || module.cookie);
          const moduleStatus =
            String(module.status || "").toLowerCase() === "online" ? "online" : "offline";

          return (
            <article className="status-tile dynamic" key={module.id}>
              {deleteMode ? (
                <button
                  className="status-remove-button"
                  type="button"
                  onClick={() => handleDelete(module.id)}
                  disabled={deletingId === module.id}
                  aria-label={`删除${module.name}`}
                >
                  <X size={18} strokeWidth={2.6} aria-hidden="true" />
                </button>
              ) : null}
              <div className="tile-topline">
                <span className="tile-icon" aria-hidden="true">
                  <Icon size={22} strokeWidth={2.1} />
                </span>
                <span className="status-type-badge">{module.capability_type}</span>
              </div>
              <h2>{module.name}</h2>
              <p className="status-url" title={module.url}>
                {module.url}
              </p>
              <div className="status-copy">
                <span className={`status-text ${moduleStatus}`}>
                  {moduleStatus === "online" ? "在线" : "离线"}
                </span>
                  <span className="status-note">{hasAuth ? "认证信息已填写" : "无认证信息"}</span>
              </div>
              <div className="status-card-actions">
                <button
                  type="button"
                  onClick={() => handleProbe(module.id)}
                  disabled={probingId === module.id}
                >
                  <RefreshCw size={15} strokeWidth={2.2} aria-hidden="true" />
                  访问测试
                </button>
                <button type="button" onClick={() => openEditDialog(module)}>
                  <Pencil size={15} strokeWidth={2.2} aria-hidden="true" />
                  编辑
                </button>
              </div>
            </article>
          );
        })}

        <button className="status-add-card" type="button" onClick={openCreateDialog}>
          <span className="knowledge-add-icon" aria-hidden="true">
            <Plus size={28} strokeWidth={2.2} />
          </span>
          <span>添加平台</span>
        </button>
      </section>

        <p className={`knowledge-message ${message.includes("已") ? "success" : ""}`}>
          {loading ? "正在加载状态模块" : message}
      </p>

      {dialogOpen ? (
        <div className="dialog-backdrop" role="presentation">
          <form className="knowledge-dialog status-dialog" onSubmit={handleSave}>
            <div className="dialog-heading">
              <div>
                  <p className="card-kicker">{editingModule ? "编辑状态平台" : "添加状态平台"}</p>
                <h2>{editingModule ? "修改平台信息" : "新建平台配置"}</h2>
              </div>
              <button
                className="dialog-close"
                type="button"
                onClick={closeDialog}
                aria-label="关闭"
              >
                <X size={18} strokeWidth={2.2} aria-hidden="true" />
              </button>
            </div>

            <div className="status-type-options" role="radiogroup" aria-label="能力类型">
              {capabilityTypes.map((item) => {
                const Icon = getCapabilityIcon(item.name);
                const active = form.capability_type === item.name;

                return (
                  <button
                    className={`status-type-option ${active ? "active" : ""}`}
                    key={item.name}
                    type="button"
                    onClick={() => updateField("capability_type", item.name)}
                    role="radio"
                    aria-checked={active}
                  >
                    <Icon size={17} strokeWidth={2.1} aria-hidden="true" />
                    {item.name}
                  </button>
                );
              })}
            </div>

            <label className="config-field">
              <span className="config-label">
                <Settings size={16} strokeWidth={2.1} aria-hidden="true" />
                平台名称<strong>*</strong>
              </span>
              <input
                type="text"
                value={form.name}
                onChange={(event) => updateField("name", event.target.value)}
                placeholder="例如：OpenAI 平台"
                disabled={saving}
                required
              />
            </label>

            <label className="config-field">
              <span className="config-label">
                <Link size={16} strokeWidth={2.1} aria-hidden="true" />
                URL<strong>*</strong>
              </span>
              <input
                type="text"
                value={form.url}
                onChange={(event) => updateField("url", event.target.value)}
                placeholder="https://example.com/api"
                disabled={saving}
                required
              />
            </label>

            <label className="config-field">
              <span className="config-label">
                <BrainCircuit size={16} strokeWidth={2.1} aria-hidden="true" />
                模型名称
              </span>
              <input
                type="text"
                value={form.model}
                onChange={(event) => updateField("model", event.target.value)}
                placeholder="例如：deepseek-v4-flash"
                disabled={saving}
              />
            </label>

            <div className="config-fields compact">
              <label className="config-field">
                <span className="config-label">
                  <KeyRound size={16} strokeWidth={2.1} aria-hidden="true" />
                  API Key
                </span>
                <input
                  type="text"
                  value={form.api_key}
                  onChange={(event) => updateField("api_key", event.target.value)}
                  placeholder="可选"
                  disabled={saving}
                />
              </label>

              <label className="config-field">
                <span className="config-label">
                  <ShieldCheck size={16} strokeWidth={2.1} aria-hidden="true" />
                  Token
                </span>
                <input
                  type="text"
                  value={form.token}
                  onChange={(event) => updateField("token", event.target.value)}
                  placeholder="可选"
                  disabled={saving}
                />
              </label>

              <label className="config-field">
                <span className="config-label">
                  <Cookie size={16} strokeWidth={2.1} aria-hidden="true" />
                  Cookie
                </span>
                <input
                  type="text"
                  value={form.cookie}
                  onChange={(event) => updateField("cookie", event.target.value)}
                  placeholder="可选"
                  disabled={saving}
                />
              </label>
            </div>

            <div className="dialog-actions">
              <button className="primary-action" type="submit" disabled={saving}>
                <Save size={18} strokeWidth={2.2} aria-hidden="true" />
                {saving ? "保存中" : editingModule ? "保存修改" : "保存"}
              </button>
            </div>
          </form>
        </div>
      ) : null}
    </section>
  );
}

function CapabilityManagementView() {
  const [capabilityTypes, setCapabilityTypes] = React.useState([]);
  const [dialogOpen, setDialogOpen] = React.useState(false);
  const [deleteMode, setDeleteMode] = React.useState(false);
  const [confirmTarget, setConfirmTarget] = React.useState(null);
  const [name, setName] = React.useState("");
  const [message, setMessage] = React.useState("");
  const [loading, setLoading] = React.useState(true);
  const [saving, setSaving] = React.useState(false);
  const [deletingName, setDeletingName] = React.useState("");

  const loadCapabilityTypes = React.useCallback(async () => {
    setLoading(true);

    try {
      const response = await fetch("/api/capability-types");
      if (!response.ok) {
        throw new Error("能力类型读取失败");
      }
      const data = await response.json();
      setCapabilityTypes(data);
      if (data.length <= 1) {
        setDeleteMode(false);
      }
    } catch (error) {
      setMessage(error.message || "能力类型读取失败");
    } finally {
      setLoading(false);
    }
  }, []);

  React.useEffect(() => {
    loadCapabilityTypes();
  }, [loadCapabilityTypes]);

  const handleCreate = async (event) => {
    event.preventDefault();
    setMessage("");

    if (!name.trim()) {
      setMessage("能力类型名称不能为空");
      return;
    }

    setSaving(true);

    try {
      const response = await fetch("/api/capability-types", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ name }),
      });

      if (!response.ok) {
        const errorBody = await response.json().catch(() => ({}));
        throw new Error(errorBody.detail || "能力类型添加失败");
      }

      setName("");
      setDialogOpen(false);
      await loadCapabilityTypes();
      setMessage("能力类型已添加，本地配置文件和内存缓存已更新");
    } catch (error) {
      setMessage(error.message || "能力类型添加失败");
    } finally {
      setSaving(false);
    }
  };

  const deleteCapabilityType = async (target, force = false) => {
    setDeletingName(target.name);
    setMessage("");

    try {
      const response = await fetch(
        `/api/capability-types/${encodeURIComponent(target.name)}?force=${force}`,
        { method: "DELETE" },
      );

      if (response.status === 409) {
        setConfirmTarget(target);
        return;
      }

      if (!response.ok) {
        const errorBody = await response.json().catch(() => ({}));
        throw new Error(errorBody.detail || "能力类型删除失败");
      }

      setConfirmTarget(null);
      await loadCapabilityTypes();
      setMessage(
        force
          ? "能力类型及其平台已强制删除，本地配置文件和内存缓存已更新"
          : "能力类型已删除，本地配置文件和内存缓存已更新",
      );
    } catch (error) {
      setMessage(error.message || "能力类型删除失败");
    } finally {
      setDeletingName("");
    }
  };

  return (
    <section className="capability-view">
      <div className="status-manager-toolbar">
        <button
          className={`delete-button ${deleteMode ? "active" : ""}`}
          type="button"
          onClick={() => setDeleteMode((current) => !current)}
          disabled={capabilityTypes.every((item) => item.is_default)}
        >
          <Trash2 size={18} strokeWidth={2.2} aria-hidden="true" />
          删除
        </button>
      </div>

      <section className="capability-grid" aria-label="能力类型列表">
        {capabilityTypes.map((capability) => {
          const Icon = getCapabilityIcon(capability.name);
          const removable = deleteMode && !capability.is_default;

          return (
            <article className="capability-card" key={capability.name}>
              {removable ? (
                <button
                  className="status-remove-button"
                  type="button"
                  onClick={() => deleteCapabilityType(capability)}
                  disabled={deletingName === capability.name}
                  aria-label={`删除${capability.name}`}
                >
                  <X size={18} strokeWidth={2.6} aria-hidden="true" />
                </button>
              ) : null}
              <div className="capability-icon" aria-hidden="true">
                <Icon size={25} strokeWidth={2.1} />
              </div>
              <h2>{capability.name}</h2>
              <div className="capability-stats">
                <span>{capability.platform_count ?? 0}</span>
                <p>当前平台数量</p>
              </div>
              <div className="capability-meta">
                <span>{capability.pool_class}</span>
                {capability.is_default ? <strong>系统默认</strong> : null}
              </div>
            </article>
          );
        })}

        <button className="capability-add-card" type="button" onClick={() => setDialogOpen(true)}>
          <span className="knowledge-add-icon" aria-hidden="true">
            <Plus size={28} strokeWidth={2.2} />
          </span>
          <span>添加能力类型</span>
        </button>
      </section>

        <p className={`knowledge-message ${message.includes("已") ? "success" : ""}`}>
        {loading ? "正在加载能力类型" : message}
      </p>

      {dialogOpen ? (
        <div className="dialog-backdrop" role="presentation">
          <form className="knowledge-dialog" onSubmit={handleCreate}>
            <div className="dialog-heading">
              <div>
                <p className="card-kicker">添加能力类型</p>
                <h2>新建能力类型</h2>
              </div>
              <button
                className="dialog-close"
                type="button"
                onClick={() => setDialogOpen(false)}
                aria-label="关闭"
              >
                <X size={18} strokeWidth={2.2} aria-hidden="true" />
              </button>
            </div>

            <label className="config-field">
              <span className="config-label">
                <BrainCircuit size={16} strokeWidth={2.1} aria-hidden="true" />
                能力类型名称
              </span>
              <input
                type="text"
                value={name}
                onChange={(event) => setName(event.target.value)}
                placeholder="例如：漏洞分析平台"
                disabled={saving}
                required
              />
            </label>

            <div className="dialog-actions">
              <button className="primary-action" type="submit" disabled={saving}>
                <Save size={18} strokeWidth={2.2} aria-hidden="true" />
                {saving ? "保存中" : "保存"}
              </button>
            </div>
          </form>
        </div>
      ) : null}

      {confirmTarget ? (
        <div className="dialog-backdrop" role="presentation">
          <div className="confirm-dialog" role="dialog" aria-modal="true">
            <div className="confirm-icon" aria-hidden="true">
              <AlertTriangle size={26} strokeWidth={2.2} />
            </div>
            <h2>是否强制删除</h2>
            <p>
              “{confirmTarget.name}” 下仍有 {confirmTarget.platform_count} 个平台。点击“是”会同时删除该能力类型下的所有平台。
            </p>
            <div className="confirm-actions">
              <button className="ghost-button" type="button" onClick={() => setConfirmTarget(null)}>
                否
              </button>
              <button
                className="danger-action"
                type="button"
                onClick={() => deleteCapabilityType(confirmTarget, true)}
                disabled={deletingName === confirmTarget.name}
              >
              是
            </button>
            </div>
          </div>
        </div>
      ) : null}
    </section>
  );
}

function ToolManagementView() {
  const emptyForm = {
    name: "",
    command_line: "",
    sandbox_command_line: "",
    description: "",
    schemaParams: [],
  };
  const [tools, setTools] = React.useState([]);
  const [form, setForm] = React.useState(emptyForm);
  const [dialogOpen, setDialogOpen] = React.useState(false);
  const [editingTool, setEditingTool] = React.useState(null);
  const [deleteMode, setDeleteMode] = React.useState(false);
  const [message, setMessage] = React.useState("");
  const [loading, setLoading] = React.useState(true);
  const [saving, setSaving] = React.useState(false);
  const [deletingId, setDeletingId] = React.useState("");

  const loadTools = React.useCallback(async () => {
    setLoading(true);

    try {
      const response = await fetch("/api/tools");
      if (!response.ok) {
        throw new Error("工具列表读取失败");
      }

      const data = await readToolApiJson(response, "工具列表读取失败");
      setTools(data);
      if (data.length === 0) {
        setDeleteMode(false);
      }
    } catch (error) {
      setMessage(error.message || "工具列表读取失败");
    } finally {
      setLoading(false);
    }
  }, []);

  React.useEffect(() => {
    loadTools();
  }, [loadTools]);

  const updateField = (field, value) => {
    setForm((current) => ({ ...current, [field]: value }));
  };

  const addSchemaParam = () => {
    setForm((current) => ({
      ...current,
      schemaParams: [
        ...(Array.isArray(current.schemaParams) ? current.schemaParams : []),
        { name: "", type: "string", defaultValue: "", description: "" },
      ],
    }));
  };

  const updateSchemaParam = (index, field, value) => {
    setForm((current) => ({
      ...current,
      schemaParams: (Array.isArray(current.schemaParams) ? current.schemaParams : []).map(
        (item, itemIndex) =>
          itemIndex === index ? { ...item, [field]: value } : item,
      ),
    }));
  };

  const removeSchemaParam = (index) => {
    setForm((current) => ({
      ...current,
      schemaParams: (Array.isArray(current.schemaParams) ? current.schemaParams : []).filter(
        (_item, itemIndex) => itemIndex !== index,
      ),
    }));
  };

  const openCreateDialog = () => {
    setEditingTool(null);
    setForm(emptyForm);
    setDialogOpen(true);
  };

  const openEditDialog = (tool) => {
    setEditingTool(tool);
    setForm({
      name: tool.name ?? "",
      command_line: tool.command_line ?? "",
      sandbox_command_line: tool.sandbox_command_line ?? "",
      description: tool.description ?? "",
      schemaParams: schemaToParamRows(tool.input_schema),
    });
    setDialogOpen(true);
  };

  const closeDialog = () => {
    setDialogOpen(false);
    setEditingTool(null);
    setForm(emptyForm);
  };

  const handleSave = async (event) => {
    event.preventDefault();
    setMessage("");

    if (!form.name.trim() || !form.command_line.trim() || !form.description.trim()) {
      setMessage("工具名称、本地命令行和描述均为必填项");
      return;
    }

    const schemaValidationError = validateSchemaParamRows(form.schemaParams);
    if (schemaValidationError) {
      setMessage(schemaValidationError);
      return;
    }

    setSaving(true);
    const payload = {
      name: form.name,
      command_line: form.command_line,
      sandbox_command_line: form.sandbox_command_line,
      description: form.description,
      input_schema: paramRowsToInputSchema(form.schemaParams),
    };

    try {
      const response = await fetch(
        editingTool ? `/api/tools/${editingTool.id}` : "/api/tools",
        {
          method: editingTool ? "PUT" : "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(payload),
        },
      );

      if (!response.ok) {
        const errorBody = await readToolApiJson(response, "").catch(() => ({}));
        throw new Error(
          errorBody.detail?.[0]?.msg ||
            errorBody.detail ||
            (editingTool ? "工具信息更新失败" : "工具添加失败"),
        );
      }

      const saved = await readToolApiJson(
        response,
        editingTool ? "工具信息更新失败" : "工具添加失败",
      );
      setTools((current) =>
        editingTool
          ? current.map((tool) => (tool.id === saved.id ? saved : tool))
          : [saved, ...current],
      );
      closeDialog();
      setMessage(
        editingTool
          ? "工具信息已更新，本地配置文件和内存缓存已同步"
          : "工具已添加，本地配置文件和内存缓存已更新",
      );
    } catch (error) {
      setMessage(error.message || (editingTool ? "工具信息更新失败" : "工具添加失败"));
    } finally {
      setSaving(false);
    }
  };

  const handleDelete = async (toolId) => {
    setDeletingId(toolId);
    setMessage("");

    try {
      const response = await fetch(`/api/tools/${toolId}`, { method: "DELETE" });
      if (!response.ok) {
        const errorBody = await readToolApiJson(response, "").catch(() => ({}));
        throw new Error(errorBody.detail || "工具删除失败");
      }

      setTools((current) => {
        const next = current.filter((tool) => tool.id !== toolId);
        if (next.length === 0) {
          setDeleteMode(false);
        }
        return next;
      });
      setMessage("工具已删除，本地配置文件和内存缓存已更新");
    } catch (error) {
      setMessage(error.message || "工具删除失败");
    } finally {
      setDeletingId("");
    }
  };

  return (
    <section className="tool-view">
      <div className="status-manager-toolbar">
        <button
          className={`delete-button ${deleteMode ? "active" : ""}`}
          type="button"
          onClick={() => setDeleteMode((current) => !current)}
          disabled={tools.every((tool) => tool.is_builtin)}
        >
          <Trash2 size={18} strokeWidth={2.2} aria-hidden="true" />
          删除
        </button>
      </div>

      <section className="tool-grid" aria-label="工具列表">
        {tools.map((tool) => (
          <article className="tool-card" key={tool.id}>
            {deleteMode && !tool.is_builtin ? (
              <button
                className="status-remove-button"
                type="button"
                onClick={() => handleDelete(tool.id)}
                disabled={deletingId === tool.id}
                aria-label={`删除${tool.name}`}
              >
                <X size={18} strokeWidth={2.6} aria-hidden="true" />
              </button>
            ) : null}

            <div className="tool-card-head">
              <span className="tool-icon" aria-hidden="true">
                <Wrench size={24} strokeWidth={2.1} />
              </span>
              <h2>{tool.name}</h2>
            </div>

            <div className="tool-command" title={tool.command_line}>
              <Settings size={16} strokeWidth={2.1} aria-hidden="true" />
              <span>{tool.command_line}</span>
            </div>
            {tool.sandbox_command_line ? (
              <div className="tool-command sandbox" title={tool.sandbox_command_line}>
                <ServerCog size={16} strokeWidth={2.1} aria-hidden="true" />
                <span>{tool.sandbox_command_line}</span>
              </div>
            ) : null}
            <p className="tool-description">{tool.description}</p>

            <div className="status-card-actions">
              {tool.is_builtin ? (
                <span className="tool-builtin-badge">系统内置</span>
              ) : (
                <button type="button" onClick={() => openEditDialog(tool)}>
                  <Pencil size={15} strokeWidth={2.2} aria-hidden="true" />
                  编辑
                </button>
              )}
            </div>
          </article>
        ))}

        <button className="tool-add-card" type="button" onClick={openCreateDialog}>
          <span className="knowledge-add-icon" aria-hidden="true">
            <Plus size={28} strokeWidth={2.2} />
          </span>
          <span>添加</span>
        </button>
      </section>

        <p className={`knowledge-message ${message.includes("已") ? "success" : ""}`}>
        {loading ? "正在加载工具列表" : message}
      </p>

      {dialogOpen ? (
        <div className="dialog-backdrop" role="presentation">
          <form className="knowledge-dialog tool-dialog" onSubmit={handleSave}>
            <div className="dialog-heading">
              <div>
                <p className="card-kicker">{editingTool ? "编辑工具" : "添加工具"}</p>
                <h2>{editingTool ? "修改工具信息" : "新建工具"}</h2>
              </div>
              <button
                className="dialog-close"
                type="button"
                onClick={closeDialog}
                aria-label="关闭"
              >
                <X size={18} strokeWidth={2.2} aria-hidden="true" />
              </button>
            </div>

            <label className="config-field">
              <span className="config-label">
                <Wrench size={16} strokeWidth={2.1} aria-hidden="true" />
                工具名称<strong>*</strong>
              </span>
              <input
                type="text"
                value={form.name}
                onChange={(event) => updateField("name", event.target.value)}
                placeholder="例如：YARA 扫描器"
                disabled={saving}
                required
              />
            </label>

            <label className="config-field">
              <span className="config-label">
                <Settings size={16} strokeWidth={2.1} aria-hidden="true" />
                本地命令行<strong>*</strong>
              </span>
              <textarea
                value={form.command_line}
                onChange={(event) => updateField("command_line", event.target.value)}
                  placeholder={'例如：python scripts/analyze.py "{target_path}"'}
                disabled={saving}
                rows={2}
                required
              />
            </label>

            <label className="config-field">
              <span className="config-label">
                <ServerCog size={16} strokeWidth={2.1} aria-hidden="true" />
                沙箱命令行              </span>
              <textarea
                value={form.sandbox_command_line}
                onChange={(event) => updateField("sandbox_command_line", event.target.value)}
                placeholder="可选：沙箱内 cdb.exe 路径不同于本地时填写"
                disabled={saving}
                rows={2}
              />
            </label>

            <label className="config-field">
              <span className="config-label">
                <FileText size={16} strokeWidth={2.1} aria-hidden="true" />
                描述<strong>*</strong>
              </span>
              <textarea
                value={form.description}
                onChange={(event) => updateField("description", event.target.value)}
                placeholder="说明该工具的用途、适用场景或调用注意事项"
                disabled={saving}
                rows={4}
                required
              />
            </label>

            <div className="tool-schema-editor">
              <div className="tool-schema-head">
                <span className="config-label">
                  <Settings size={16} strokeWidth={2.1} aria-hidden="true" />
                  Input Schema
                </span>
                <button
                  className="tool-schema-add"
                  type="button"
                  onClick={addSchemaParam}
                  disabled={saving}
                  aria-label="Add schema parameter"
                >
                  <Plus size={16} strokeWidth={2.4} aria-hidden="true" />
                </button>
              </div>
              {(form.schemaParams || []).length ? (
                <div className="tool-schema-list">
                  <div className="tool-schema-row tool-schema-row-head">
                    <span>Name</span>
                    <span>Type</span>
                    <span>Default</span>
                    <span>Description</span>
                    <span />
                  </div>
                  {(form.schemaParams || []).map((param, index) => (
                    <div className="tool-schema-row" key={`schema-param-${index}`}>
                      <input
                        type="text"
                        value={param.name}
                        onChange={(event) =>
                          updateSchemaParam(index, "name", event.target.value)
                        }
                        placeholder="name"
                        disabled={saving}
                        required
                      />
                      <select
                        value={param.type}
                        onChange={(event) =>
                          updateSchemaParam(index, "type", event.target.value)
                        }
                        disabled={saving}
                        required
                      >
                        <option value="string">string</option>
                        <option value="integer">integer</option>
                        <option value="boolean">boolean</option>
                      </select>
                      {param.type === "boolean" ? (
                        <select
                          value={param.defaultValue || ""}
                          onChange={(event) =>
                            updateSchemaParam(index, "defaultValue", event.target.value)
                          }
                          disabled={saving}
                        >
                          <option value="">default</option>
                          <option value="true">true</option>
                          <option value="false">false</option>
                        </select>
                      ) : (
                        <input
                          type={param.type === "integer" ? "number" : "text"}
                          value={param.defaultValue}
                          onChange={(event) =>
                            updateSchemaParam(index, "defaultValue", event.target.value)
                          }
                          placeholder="default"
                          disabled={saving}
                        />
                      )}
                      <input
                        type="text"
                        value={param.description}
                        onChange={(event) =>
                          updateSchemaParam(index, "description", event.target.value)
                        }
                        placeholder="description"
                        disabled={saving}
                        required
                      />
                      <button
                        className="tool-schema-remove"
                        type="button"
                        onClick={() => removeSchemaParam(index)}
                        disabled={saving}
                        aria-label="Remove schema parameter"
                      >
                        <X size={15} strokeWidth={2.4} aria-hidden="true" />
                      </button>
                    </div>
                  ))}
                </div>
              ) : (
                <p className="tool-schema-empty">
                  ???????????????????? input_schema?
                </p>
              )}
            </div>

            <div className="dialog-actions">
              <button className="primary-action" type="submit" disabled={saving}>
                <Save size={18} strokeWidth={2.2} aria-hidden="true" />
                  {saving ? "保存中" : editingTool ? "保存修改" : "保存"}
              </button>
            </div>
          </form>
        </div>
      ) : null}
    </section>
  );
}

function splitSkillKeywords(value) {
  return String(value || "")
      .replace(/：/g, ",")
    .split(/[\n,]/)
    .map((item) => item.trim())
    .filter(Boolean);
}

function SkillsManagementView() {
  const emptyForm = {
    name: "",
    description: "",
    keywordsText: "",
    content: "",
    source: "editor",
  };
  const [skills, setSkills] = React.useState([]);
  const [form, setForm] = React.useState(emptyForm);
  const [dialogOpen, setDialogOpen] = React.useState(false);
  const [editingSkill, setEditingSkill] = React.useState(null);
  const [deleteMode, setDeleteMode] = React.useState(false);
  const [message, setMessage] = React.useState("");
  const [loading, setLoading] = React.useState(true);
  const [saving, setSaving] = React.useState(false);
  const [deletingId, setDeletingId] = React.useState("");

  const loadSkills = React.useCallback(async () => {
    setLoading(true);
    try {
      const response = await fetch("/api/skills");
      if (!response.ok) {
        throw new Error("Skills 列表读取失败");
      }
      const data = await response.json();
      setSkills(Array.isArray(data) ? data : []);
      if (!Array.isArray(data) || data.length === 0) {
        setDeleteMode(false);
      }
    } catch (error) {
      setMessage(error.message || "Skills 列表读取失败");
    } finally {
      setLoading(false);
    }
  }, []);

  React.useEffect(() => {
    loadSkills();
  }, [loadSkills]);

  const updateField = (field, value) => {
    setForm((current) => ({ ...current, [field]: value }));
  };

  const openCreateDialog = (source = "editor") => {
    setEditingSkill(null);
    setForm({ ...emptyForm, source });
    setDialogOpen(true);
  };

  const openEditDialog = (skill) => {
    setEditingSkill(skill);
    setForm({
      name: skill.name ?? "",
      description: skill.description ?? "",
      keywordsText: Array.isArray(skill.keywords) ? skill.keywords.join(", ") : "",
      content: skill.content ?? "",
      source: skill.source ?? "editor",
    });
    setDialogOpen(true);
  };

  const closeDialog = () => {
    setDialogOpen(false);
    setEditingSkill(null);
    setForm(emptyForm);
  };

  const handleImportFile = async (event) => {
    const file = event.target.files?.[0];
    if (!file) {
      return;
    }
    const text = await file.text();
    const fallbackName = file.name.replace(/\.(md|markdown)$/i, "");
    setForm((current) => ({
      ...current,
      name: current.name || fallbackName,
      content: text,
      source: "markdown-import",
    }));
  };

  const handleSave = async (event) => {
    event.preventDefault();
    setMessage("");

    const keywords = splitSkillKeywords(form.keywordsText);
    if (!form.name.trim() || keywords.length === 0 || !form.content.trim()) {
      setMessage("Skill 名称、触发关键字和 Markdown 内容均为必填项");
      return;
    }

    const payload = {
      name: form.name.trim(),
      description: form.description.trim(),
      keywords,
      content: form.content,
      source: form.source || "editor",
    };

    setSaving(true);
    try {
      const response = await fetch(
        editingSkill ? `/api/skills/${editingSkill.id}` : "/api/skills",
        {
          method: editingSkill ? "PUT" : "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(payload),
        },
      );

      if (!response.ok) {
        const errorBody = await response.json().catch(() => ({}));
        throw new Error(
          errorBody.detail?.[0]?.msg ||
            errorBody.detail ||
            (editingSkill ? "Skill 更新失败" : "Skill 创建失败"),
        );
      }

      const saved = await response.json();
      setSkills((current) =>
        editingSkill
          ? current.map((skill) => (skill.id === saved.id ? saved : skill))
          : [saved, ...current],
      );
      closeDialog();
        setMessage(editingSkill ? "Skill 已更新" : "Skill 已创建");
    } catch (error) {
      setMessage(error.message || (editingSkill ? "Skill 更新失败" : "Skill 创建失败"));
    } finally {
      setSaving(false);
    }
  };

  const handleDelete = async (skillId) => {
    setDeletingId(skillId);
    setMessage("");
    try {
      const response = await fetch(`/api/skills/${skillId}`, { method: "DELETE" });
      if (!response.ok) {
        const errorBody = await response.json().catch(() => ({}));
        throw new Error(errorBody.detail || "Skill 删除失败");
      }
      setSkills((current) => {
        const next = current.filter((skill) => skill.id !== skillId);
        if (next.length === 0) {
          setDeleteMode(false);
        }
        return next;
      });
        setMessage("Skill 已删除");
    } catch (error) {
      setMessage(error.message || "Skill 删除失败");
    } finally {
      setDeletingId("");
    }
  };

  return (
    <section className="skill-view">
      <div className="status-manager-toolbar">
        <button className="secondary-action" type="button" onClick={() => openCreateDialog("editor")}>
          <Pencil size={18} strokeWidth={2.2} aria-hidden="true" />
          在线创建
        </button>
        <button className="secondary-action" type="button" onClick={() => openCreateDialog("markdown-import")}>
          <UploadCloud size={18} strokeWidth={2.2} aria-hidden="true" />
          导入 Markdown
        </button>
        <button
          className={`delete-button ${deleteMode ? "active" : ""}`}
          type="button"
          onClick={() => setDeleteMode((current) => !current)}
          disabled={skills.length === 0}
        >
          <Trash2 size={18} strokeWidth={2.2} aria-hidden="true" />
          删除
        </button>
      </div>

      <section className="skill-grid" aria-label="Skills 列表">
        {skills.map((skill) => (
          <article className="skill-card" key={skill.id}>
            {deleteMode ? (
              <button
                className="status-remove-button"
                type="button"
                onClick={() => handleDelete(skill.id)}
                disabled={deletingId === skill.id}
                aria-label={`删除 ${skill.name}`}
              >
                <X size={18} strokeWidth={2.6} aria-hidden="true" />
              </button>
            ) : null}

            <div className="tool-card-head">
              <span className="tool-icon" aria-hidden="true">
                <Hammer size={24} strokeWidth={2.1} />
              </span>
              <h2>{skill.name}</h2>
            </div>
              <p className="skill-description">{skill.description || "未填写描述"}</p>
            <div className="skill-keywords">
              {(Array.isArray(skill.keywords) ? skill.keywords : []).map((keyword) => (
                <span className="skill-keyword" key={keyword}>
                  {keyword}
                </span>
              ))}
            </div>
            <div className="skill-meta">
              <span>{skill.source === "markdown-import" ? "Markdown 导入" : "在线编辑"}</span>
              <span>{skill.updated_at ? `更新于 ${skill.updated_at}` : ""}</span>
            </div>
            <div className="status-card-actions">
              <button type="button" onClick={() => openEditDialog(skill)}>
                <Pencil size={15} strokeWidth={2.2} aria-hidden="true" />
                编辑
              </button>
            </div>
          </article>
        ))}

        <button className="skill-add-card" type="button" onClick={() => openCreateDialog("editor")}>
          <span className="knowledge-add-icon" aria-hidden="true">
            <Plus size={28} strokeWidth={2.2} />
          </span>
          <span>新建 Skill</span>
        </button>
      </section>

        <p className={`knowledge-message ${message.includes("已") ? "success" : ""}`}>
        {loading ? "正在加载 Skills" : message}
      </p>

      {dialogOpen ? (
        <div className="dialog-backdrop" role="presentation">
          <form className="knowledge-dialog skill-dialog" onSubmit={handleSave}>
            <div className="dialog-heading">
              <div>
                <p className="card-kicker">{editingSkill ? "编辑 Skill" : "创建 Skill"}</p>
                <h2>{editingSkill ? "修改触发规则与提示词" : "配置触发关键字与 Markdown 提示词"}</h2>
              </div>
              <button
                className="dialog-close"
                type="button"
                onClick={closeDialog}
                aria-label="关闭"
              >
                <X size={18} strokeWidth={2.2} aria-hidden="true" />
              </button>
            </div>

            {!editingSkill ? (
              <div className="skill-mode-switch" role="group" aria-label="创建方式">
                <button
                  className={`status-type-option ${form.source === "editor" ? "active" : ""}`}
                  type="button"
                  onClick={() => updateField("source", "editor")}
                >
                  <Pencil size={17} strokeWidth={2.1} aria-hidden="true" />
                  在线编辑
                </button>
                <button
                  className={`status-type-option ${form.source === "markdown-import" ? "active" : ""}`}
                  type="button"
                  onClick={() => updateField("source", "markdown-import")}
                >
                  <UploadCloud size={17} strokeWidth={2.1} aria-hidden="true" />
                  导入 Markdown
                </button>
              </div>
            ) : null}

            {form.source === "markdown-import" ? (
              <label className="config-field">
                <span className="config-label">
                  <UploadCloud size={16} strokeWidth={2.1} aria-hidden="true" />
                  Markdown 文档
                </span>
                <input
                  type="file"
                  accept=".md,.markdown,text/markdown,text/plain"
                  onChange={handleImportFile}
                  disabled={saving}
                />
              </label>
            ) : null}

            <label className="config-field">
              <span className="config-label">
                <Hammer size={16} strokeWidth={2.1} aria-hidden="true" />
                Skill 名称<strong>*</strong>
              </span>
              <input
                type="text"
                value={form.name}
                onChange={(event) => updateField("name", event.target.value)}
                placeholder="例如：PE 导入表分析"
                disabled={saving}
                required
              />
            </label>

            <label className="config-field">
              <span className="config-label">
                <Hash size={16} strokeWidth={2.1} aria-hidden="true" />
                触发关键字<strong>*</strong>
              </span>
              <input
                type="text"
                value={form.keywordsText}
                onChange={(event) => updateField("keywordsText", event.target.value)}
                placeholder="用逗号或换行分隔，例如：导入表, import table, IAT"
                disabled={saving}
                required
              />
            </label>

            <label className="config-field">
              <span className="config-label">
                <FileText size={16} strokeWidth={2.1} aria-hidden="true" />
                描述
              </span>
              <textarea
                value={form.description}
                onChange={(event) => updateField("description", event.target.value)}
                placeholder="简要说明这个 Skill 适用的分析场景"
                disabled={saving}
                rows={3}
              />
            </label>

            <label className="config-field skill-markdown-field">
              <span className="config-label">
                <FileCode2 size={16} strokeWidth={2.1} aria-hidden="true" />
                Markdown 提示词<strong>*</strong>
              </span>
              <textarea
                value={form.content}
                onChange={(event) => updateField("content", event.target.value)}
                placeholder="# Skill 提示词&#10;写入该 Skill 被触发后要追加到 system prompt 的分析策略。"
                disabled={saving}
                rows={14}
                required
              />
            </label>

            <div className="dialog-actions">
              <button className="primary-action" type="submit" disabled={saving}>
                <Save size={18} strokeWidth={2.2} aria-hidden="true" />
                {saving ? "保存中" : editingSkill ? "保存修改" : "保存 Skill"}
              </button>
            </div>
          </form>
        </div>
      ) : null}
    </section>
  );
}

function WorkbenchView({ onOpenTask, onOpenTaskRecord }) {
  const [tasks, setTasks] = React.useState([]);
  const [loadingTasks, setLoadingTasks] = React.useState(true);
  const [taskMessage, setTaskMessage] = React.useState("");
  const [taskFilter, setTaskFilter] = React.useState("all");
  const [moduleFilter, setModuleFilter] = React.useState("all");
  const [searchValue, setSearchValue] = React.useState("");

  const loadTasks = React.useCallback(async () => {
    setLoadingTasks(true);
    try {
      const response = await fetch("/api/tasks");
      if (!response.ok) {
        throw new Error("近期任务读取失败");
      }
      const body = await response.json();
      setTasks(Array.isArray(body) ? body : []);
      setTaskMessage("");
    } catch (error) {
      setTaskMessage(error.message || "近期任务读取失败");
    } finally {
      setLoadingTasks(false);
    }
  }, []);

  React.useEffect(() => {
    loadTasks();
  }, [loadTasks]);

  const recentTasks = tasks
    .filter((task) => Boolean(getWorkbenchModuleByTaskType(task?.task_type)))
    .filter((task) => matchTaskFilter(task, taskFilter))
    .filter((task) => matchModuleFilter(task, moduleFilter))
    .filter((task) => matchTaskSearch(task, searchValue))
    .sort(compareTaskBoardItems)
    .slice(0, 12);

  const taskStats = summarizeTaskStats(tasks);

  return (
    <section className="workbench-shell">
      <section className="workbench-grid" aria-label="工作台模块">
        {workbenchModules.map((module) => {
          const Icon = module.icon;

          return (
            <button
              className="workbench-card available"
              key={module.id}
              type="button"
              onClick={() => onOpenTask(module.id)}
              title={module.name}
            >
              <span className="workbench-icon" aria-hidden="true">
                <Icon size={25} strokeWidth={2.1} />
              </span>
              <span className="workbench-copy">
                <span className="workbench-name">{module.name}</span>
                <span className="workbench-description">{module.description}</span>
              </span>
              <span className="workbench-state">
                进入模块
              </span>
            </button>
          );
        })}
      </section>

      <section className="task-board" aria-label="近期任务栏">
        <div className="task-board-head">
          <div>
              <p className="card-kicker">任务栏</p>
            <h2>近期任务</h2>
          </div>
          <button className="ghost-button task-board-refresh" type="button" onClick={loadTasks}>
            <RefreshCw size={16} strokeWidth={2.1} aria-hidden="true" />
            刷新
          </button>
        </div>

        <div className="task-board-filters" role="tablist" aria-label="任务状态筛选">
          {[
            { id: "all", label: "全部" },
              { id: "running", label: "进行中" },
              { id: "completed", label: "已完成" },
            { id: "failed", label: "失败" },
          ].map((filter) => (
            <button
              className={`task-filter-chip ${taskFilter === filter.id ? "active" : ""}`}
              key={filter.id}
              type="button"
              onClick={() => setTaskFilter(filter.id)}
              role="tab"
              aria-selected={taskFilter === filter.id}
            >
              {filter.label}
            </button>
          ))}
        </div>

        <div className="task-board-toolbar">
          <label className="task-search-field">
            <ScanSearch size={16} strokeWidth={2.1} aria-hidden="true" />
            <input
              type="text"
              value={searchValue}
              onChange={(event) => setSearchValue(event.target.value)}
              placeholder="搜索 Task ID、目标文件、摘要"
            />
          </label>

          <label className="task-module-filter">
            <span>模块</span>
            <select
              value={moduleFilter}
              onChange={(event) => setModuleFilter(event.target.value)}
            >
              <option value="all">全部模块</option>
              {workbenchModules.map((module) => (
                <option key={module.id} value={module.taskType}>
                  {module.name}
                </option>
              ))}
            </select>
          </label>
        </div>

        <div className="task-board-stats">
          <TaskStatCard label="总任务" value={taskStats.total} tone="neutral" />
          <TaskStatCard label="进行中" value={taskStats.running} tone="running" />
          <TaskStatCard label="排队中" value={taskStats.queued} tone="queued" />
          <TaskStatCard label="已完成" value={taskStats.completed} tone="completed" />
          <TaskStatCard label="失败" value={taskStats.failed} tone="failed" />
        </div>

        {loadingTasks ? (
          <div className="task-board-empty">
            <History size={24} strokeWidth={2.1} aria-hidden="true" />
            <p>正在读取近期任务...</p>
          </div>
        ) : recentTasks.length ? (
          <div className="task-board-list">
            {recentTasks.map((task) => {
              const module = getWorkbenchModuleByTaskType(task.task_type);
              const Icon = module?.icon ?? Archive;
              const statusText = taskStatusText(task.status);
              return (
                <button
                  className="task-board-item"
                  key={task.task_id || task.id}
                  type="button"
                  onClick={() => onOpenTaskRecord(task)}
                >
                  <div className="task-board-item-top">
                    <span className="task-board-item-icon" aria-hidden="true">
                      <Icon size={18} strokeWidth={2.1} />
                    </span>
                    <span className={`task-status-pill ${task.status || "unknown"}`}>
                      {statusText}
                    </span>
                  </div>
                  <div className="task-board-item-copy">
                    <strong>{module?.name || task.task_name || task.task_type}</strong>
                    <span>{summarizeTaskBoardMeta(task)}</span>
                    <div className="task-board-meta">
                      <span>{taskTargetLabel(task)}</span>
                      <span>{taskUpdatedLabel(task)}</span>
                    </div>
                    <span className="task-board-id">
                      Task：{task.task_id || task.id}
                    </span>
                  </div>
                  <div
                    className="task-board-actions"
                    onClick={(event) => event.stopPropagation()}
                  >
                    <button
                      className="task-action-button"
                      type="button"
                      onClick={() => onOpenTaskRecord(task)}
                    >
                      查看任务
                    </button>
                    {taskReportUrl(task) ? (
                      <a
                        className="task-action-button"
                        href={taskReportUrl(task)}
                        target="_blank"
                        rel="noreferrer"
                      >
                        查看报告
                      </a>
                    ) : null}
                    <button
                      className="task-action-button"
                      type="button"
                      onClick={() =>
                        downloadTaskJson(task, module?.taskType || task.task_type || "task")
                      }
                    >
                      下载 JSON
                    </button>
                  </div>
                </button>
              );
            })}
          </div>
        ) : (
          <div className="task-board-empty">
            <Archive size={24} strokeWidth={2.1} aria-hidden="true" />
            <p>{taskMessage || "当前还没有近期任务。"}</p>
          </div>
        )}
      </section>
    </section>
  );
}

function TaskHistoryView({ onOpenTaskRecord }) {
  const [tasks, setTasks] = React.useState([]);
  const [loadingTasks, setLoadingTasks] = React.useState(true);
  const [taskMessage, setTaskMessage] = React.useState("");
  const [taskFilter, setTaskFilter] = React.useState("all");
  const [moduleFilter, setModuleFilter] = React.useState("all");
  const [searchValue, setSearchValue] = React.useState("");
  const [page, setPage] = React.useState(1);
  const [pagination, setPagination] = React.useState({
    total: 0,
    page: 1,
    page_size: 12,
    total_pages: 1,
  });

  const pageSize = 12;

  const loadTasks = React.useCallback(async () => {
    setLoadingTasks(true);
    try {
      const params = new URLSearchParams();
      params.set("page", String(page));
      params.set("page_size", String(pageSize));
      if (taskFilter !== "all") {
        params.set("status", taskFilter);
      }
      if (moduleFilter !== "all") {
        params.set("task_type", moduleFilter);
      }
      if (searchValue.trim()) {
        params.set("search", searchValue.trim());
      }
      const response = await fetch(`/api/tasks?${params.toString()}`);
      if (!response.ok) {
        throw new Error("历史任务读取失败");
      }
      const body = await response.json();
      const items = Array.isArray(body?.items) ? body.items : [];
      setTasks(items);
      setPagination({
        total: Number(body?.total || 0),
        page: Number(body?.page || page),
        page_size: Number(body?.page_size || pageSize),
        total_pages: Number(body?.total_pages || 1),
      });
      setTaskMessage("");
    } catch (error) {
      setTaskMessage(error.message || "历史任务读取失败");
    } finally {
      setLoadingTasks(false);
    }
  }, [moduleFilter, page, searchValue, taskFilter]);

  React.useEffect(() => {
    loadTasks();
  }, [loadTasks]);

  React.useEffect(() => {
    setPage(1);
  }, [taskFilter, moduleFilter, searchValue]);

  const visibleTasks = tasks
    .filter((task) => Boolean(getWorkbenchModuleByTaskType(task?.task_type)))
    .sort(compareTaskBoardItems);
  const taskStats = summarizeTaskStats(tasks);

  return (
    <section className="history-shell">
      <section className="task-board history-board" aria-label="历史任务中心">
        <div className="task-board-head">
          <div>
            <p className="card-kicker">历史记录</p>
            <h2>历史任务中心</h2>
          </div>
          <button className="ghost-button task-board-refresh" type="button" onClick={loadTasks}>
            <RefreshCw size={16} strokeWidth={2.1} aria-hidden="true" />
            刷新
          </button>
        </div>

        <div className="task-board-filters" role="tablist" aria-label="历史任务状态筛选">
          {[
            { id: "all", label: "全部" },
              { id: "running", label: "进行中" },
              { id: "completed", label: "已完成" },
            { id: "failed", label: "失败" },
          ].map((filter) => (
            <button
              className={`task-filter-chip ${taskFilter === filter.id ? "active" : ""}`}
              key={filter.id}
              type="button"
              onClick={() => setTaskFilter(filter.id)}
              role="tab"
              aria-selected={taskFilter === filter.id}
            >
              {filter.label}
            </button>
          ))}
        </div>

        <div className="task-board-toolbar">
          <label className="task-search-field">
            <ScanSearch size={16} strokeWidth={2.1} aria-hidden="true" />
            <input
              type="text"
              value={searchValue}
              onChange={(event) => setSearchValue(event.target.value)}
              placeholder="搜索 Task ID、目标文件、摘要"
            />
          </label>

          <label className="task-module-filter">
            <span>模块</span>
            <select
              value={moduleFilter}
              onChange={(event) => setModuleFilter(event.target.value)}
            >
              <option value="all">全部模块</option>
              {workbenchModules.map((module) => (
                <option key={module.id} value={module.taskType}>
                  {module.name}
                </option>
              ))}
            </select>
          </label>
        </div>

        <div className="task-board-stats">
          <TaskStatCard label="本页任务" value={visibleTasks.length} tone="neutral" />
            <TaskStatCard label="进行中" value={taskStats.running} tone="running" />
            <TaskStatCard label="排队中" value={taskStats.queued} tone="queued" />
            <TaskStatCard label="已完成" value={taskStats.completed} tone="completed" />
          <TaskStatCard label="失败" value={taskStats.failed} tone="failed" />
        </div>

        {loadingTasks ? (
          <div className="task-board-empty">
            <History size={24} strokeWidth={2.1} aria-hidden="true" />
            <p>正在读取历史任务...</p>
          </div>
        ) : visibleTasks.length ? (
          <>
            <div className="task-board-list history-task-list">
              {visibleTasks.map((task) => {
                const module = getWorkbenchModuleByTaskType(task.task_type);
                const Icon = module?.icon ?? Archive;
                const statusText = taskStatusText(task.status);
                return (
                  <button
                    className="task-board-item"
                    key={task.task_id || task.id}
                    type="button"
                    onClick={() => onOpenTaskRecord(task)}
                  >
                    <div className="task-board-item-top">
                      <span className="task-board-item-icon" aria-hidden="true">
                        <Icon size={18} strokeWidth={2.1} />
                      </span>
                      <span className={`task-status-pill ${task.status || "unknown"}`}>
                        {statusText}
                      </span>
                    </div>
                    <div className="task-board-item-copy">
                      <strong>{module?.name || task.task_name || task.task_type}</strong>
                      <span>{summarizeTaskBoardMeta(task)}</span>
                      <div className="task-board-meta">
                        <span>{taskTargetLabel(task)}</span>
                        <span>{taskUpdatedLabel(task)}</span>
                      </div>
                      <span className="task-board-id">
                        Task：{task.task_id || task.id}
                      </span>
                    </div>
                    <div
                      className="task-board-actions"
                      onClick={(event) => event.stopPropagation()}
                    >
                      <button
                        className="task-action-button"
                        type="button"
                        onClick={() => onOpenTaskRecord(task)}
                      >
                        查看任务
                      </button>
                      {taskReportUrl(task) ? (
                        <a
                          className="task-action-button"
                          href={taskReportUrl(task)}
                          target="_blank"
                          rel="noreferrer"
                        >
                          查看报告
                        </a>
                      ) : null}
                      <button
                        className="task-action-button"
                        type="button"
                        onClick={() =>
                          downloadTaskJson(task, module?.taskType || task.task_type || "task")
                        }
                      >
                        下载 JSON
                      </button>
                    </div>
                  </button>
                );
              })}
            </div>

            <div className="pagination-bar">
              <div className="pagination-meta">
                <span>鎬讳换鍔★細{pagination.total}</span>
                <span>
                  绗?{pagination.page} / {pagination.total_pages} 椤?                </span>
              </div>
              <div className="pagination-actions">
                <button
                  className="ghost-button pagination-button"
                  type="button"
                  disabled={pagination.page <= 1}
                  onClick={() => setPage((current) => Math.max(1, current - 1))}
                >
                  上一页                </button>
                <button
                  className="ghost-button pagination-button"
                  type="button"
                  disabled={pagination.page >= pagination.total_pages}
                  onClick={() =>
                    setPage((current) => Math.min(pagination.total_pages, current + 1))
                  }
                >
                  下一页                </button>
              </div>
            </div>
          </>
        ) : (
          <div className="task-board-empty">
            <Archive size={24} strokeWidth={2.1} aria-hidden="true" />
            <p>{taskMessage || "当前页没有符合条件的历史任务。"}</p>
          </div>
        )}
      </section>
    </section>
  );
}

function TaskStatCard({ label, value, tone = "neutral" }) {
  return (
    <div className={`task-stat-card ${tone}`}>
      <span>{label}</span>
      <strong>{value}</strong>
    </div>
  );
}

function KnowledgeBaseView() {
  const [knowledgeBases, setKnowledgeBases] = React.useState([]);
  const [selectedIds, setSelectedIds] = React.useState(new Set());
  const [dialogOpen, setDialogOpen] = React.useState(false);
  const [form, setForm] = React.useState({ name: "", folder_path: "" });
  const [message, setMessage] = React.useState("");
  const [loading, setLoading] = React.useState(true);
  const [saving, setSaving] = React.useState(false);
  const [deleting, setDeleting] = React.useState(false);

  const loadKnowledgeBases = React.useCallback(async () => {
    setLoading(true);
    setMessage("");

    try {
      const response = await fetch("/api/knowledge-bases");
      if (!response.ok) {
        throw new Error("知识库列表读取失败");
      }

      const data = await response.json();
      setKnowledgeBases(data);
      setSelectedIds((current) => {
        const validIds = new Set(data.map((item) => item.id));
        return new Set([...current].filter((id) => validIds.has(id)));
      });
    } catch (error) {
        setMessage(error.message || "知识库列表读取失败");
    } finally {
      setLoading(false);
    }
  }, []);

  React.useEffect(() => {
    loadKnowledgeBases();
  }, [loadKnowledgeBases]);

  const allSelected =
    knowledgeBases.length > 0 && knowledgeBases.every((item) => selectedIds.has(item.id));

  const toggleAll = () => {
    setSelectedIds(
      allSelected ? new Set() : new Set(knowledgeBases.map((item) => item.id)),
    );
  };

  const toggleOne = (id) => {
    setSelectedIds((current) => {
      const next = new Set(current);
      if (next.has(id)) {
        next.delete(id);
      } else {
        next.add(id);
      }
      return next;
    });
  };

  const deleteSelected = async () => {
    if (selectedIds.size === 0) {
      setMessage("请先选择要删除的知识库");
      return;
    }

    setDeleting(true);
    setMessage("");

    try {
      const response = await fetch("/api/knowledge-bases", {
        method: "DELETE",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ ids: [...selectedIds] }),
      });

      if (!response.ok) {
        throw new Error("知识库删除失败");
      }

      setSelectedIds(new Set());
      await loadKnowledgeBases();
      setMessage("已删除选中的知识库及本地向量文件");
    } catch (error) {
      setMessage(error.message || "知识库删除失败");
    } finally {
      setDeleting(false);
    }
  };

  const handleCreate = async (event) => {
    event.preventDefault();

    if (!form.name.trim() || !form.folder_path.trim()) {
      setMessage("知识库名称和文件夹路径均为必填项");
      return;
    }

    setSaving(true);
    setMessage("正在切片和向量化知识库文件");

    try {
      const response = await fetch("/api/knowledge-bases", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(form),
      });

      if (!response.ok) {
        const errorBody = await response.json().catch(() => ({}));
        throw new Error(errorBody.detail || "知识库添加失败");
      }

      setDialogOpen(false);
      setForm({ name: "", folder_path: "" });
      await loadKnowledgeBases();
      setMessage("知识库已添加并完成向量化");
    } catch (error) {
      setMessage(error.message || "知识库添加失败");
    } finally {
      setSaving(false);
    }
  };

  return (
    <section className="knowledge-view">
      <div className="knowledge-toolbar">
        <button
          className={`select-all-button ${allSelected ? "active" : ""}`}
          type="button"
          onClick={toggleAll}
          disabled={knowledgeBases.length === 0}
        >
          {allSelected ? (
            <CheckSquare size={18} strokeWidth={2.2} aria-hidden="true" />
          ) : (
            <Square size={18} strokeWidth={2.2} aria-hidden="true" />
          )}
          全选        </button>
        <button
          className="delete-button"
          type="button"
          onClick={deleteSelected}
          disabled={deleting || selectedIds.size === 0}
        >
          <Trash2 size={18} strokeWidth={2.2} aria-hidden="true" />
          删除
        </button>
      </div>

      <section className="knowledge-grid" aria-label="知识库列表">
        {knowledgeBases.map((knowledgeBase) => {
          const selected = selectedIds.has(knowledgeBase.id);

          return (
            <article
              className={`knowledge-card ${selected ? "selected" : ""}`}
              key={knowledgeBase.id}
            >
              <button
                className="knowledge-check"
                type="button"
                onClick={() => toggleOne(knowledgeBase.id)}
                aria-label={`选择${knowledgeBase.name}`}
              >
                {selected ? (
                  <CheckSquare size={20} strokeWidth={2.2} aria-hidden="true" />
                ) : (
                  <Square size={20} strokeWidth={2.2} aria-hidden="true" />
                )}
              </button>
              <div className="knowledge-icon" aria-hidden="true">
                <BookOpen size={25} strokeWidth={2.1} />
              </div>
              <h2>{knowledgeBase.name}</h2>
              <p title={knowledgeBase.folder_path}>{knowledgeBase.folder_path}</p>
              <div className="knowledge-stats">
                <span>
                  <FileText size={15} strokeWidth={2.1} aria-hidden="true" />
                  {knowledgeBase.file_count ?? 0} 文件
                </span>
                <span>
                  <Layers3 size={15} strokeWidth={2.1} aria-hidden="true" />
                  {knowledgeBase.chunk_count ?? 0} 切片
                </span>
              </div>
            </article>
          );
        })}

        <button className="knowledge-add-card" type="button" onClick={() => setDialogOpen(true)}>
          <span className="knowledge-add-icon" aria-hidden="true">
            <Plus size={28} strokeWidth={2.2} />
          </span>
          <span>添加</span>
        </button>
      </section>

        <p className={`knowledge-message ${message.includes("已") ? "success" : ""}`}>
          {loading ? "正在加载知识库" : message}
      </p>

      {dialogOpen ? (
        <div className="dialog-backdrop" role="presentation">
          <form className="knowledge-dialog" onSubmit={handleCreate}>
            <div className="dialog-heading">
              <div>
                  <p className="card-kicker">添加知识库</p>
                  <h2>新建知识库</h2>
              </div>
              <button
                className="dialog-close"
                type="button"
                onClick={() => setDialogOpen(false)}
                aria-label="关闭"
              >
                <X size={18} strokeWidth={2.2} aria-hidden="true" />
              </button>
            </div>

            <label className="config-field">
              <span className="config-label">
                <BookOpen size={16} strokeWidth={2.1} aria-hidden="true" />
                知识库名称
              </span>
              <input
                type="text"
                value={form.name}
                onChange={(event) =>
                  setForm((current) => ({ ...current, name: event.target.value }))
                }
                placeholder="例如：漏洞分析知识库"
                disabled={saving}
                required
              />
            </label>

            <label className="config-field">
              <span className="config-label">
                <FolderOpen size={16} strokeWidth={2.1} aria-hidden="true" />
                知识库文件夹路径
              </span>
              <input
                type="text"
                value={form.folder_path}
                onChange={(event) =>
                  setForm((current) => ({ ...current, folder_path: event.target.value }))
                }
                placeholder="例如：/Users/anzi/Documents/knowledge 或 C:\\Users\\Anzi\\Documents\\knowledge"
                disabled={saving}
                required
              />
            </label>

            <div className="dialog-actions">
              <button className="primary-action" type="submit" disabled={saving}>
                <Save size={18} strokeWidth={2.2} aria-hidden="true" />
                  {saving ? "保存中" : "保存"}
              </button>
            </div>
          </form>
        </div>
      ) : null}
    </section>
  );
}

function TaskExecutionView({ module, initialTask = null, onBack }) {
  const [selectedFile, setSelectedFile] = React.useState(null);
  const [analysisResult, setAnalysisResult] = React.useState(initialTask);
  const [analysisMessage, setAnalysisMessage] = React.useState("");
  const [submitting, setSubmitting] = React.useState(false);
  const [taskInput, setTaskInput] = React.useState("");
  const [taskEvents, setTaskEvents] = React.useState([]);
  const [timelineExpanded, setTimelineExpanded] = React.useState(false);
  const [openTimelineEntryIds, setOpenTimelineEntryIds] = React.useState([]);
  const requiresFile = Boolean(module.requiresFile);
  const openedFromTaskBoard = Boolean(initialTask);

  React.useEffect(() => {
    setAnalysisResult(initialTask);
    setAnalysisMessage("");
    setTaskEvents([]);
    setTimelineExpanded(false);
    setOpenTimelineEntryIds([]);
  }, [initialTask]);

  React.useEffect(() => {
    if (!analysisResult?.task_id) {
      return undefined;
    }
    let cancelled = false;
    let timer = null;
    const loadTask = async () => {
      try {
        const response = await fetch(`/api/tasks/${analysisResult.task_id}`);
        if (!response.ok) {
          return;
        }
        const body = await response.json();
        if (!cancelled) {
          const merged = mergeTaskResultPayload(body, analysisResult);
          setAnalysisResult((current) => mergeTaskResultPayload(body, current));
          if (merged.status === "completed") {
              setAnalysisMessage("Task Pool 已完成任务执行");
          } else if (merged.status === "failed") {
            setAnalysisMessage(merged.error || "任务执行失败");
          } else if (merged.status === "running") {
            setAnalysisMessage("任务执行中，正在实时同步执行过程");
          } else if (merged.status === "queued") {
            setAnalysisMessage("任务已排队，等待 Task Pool 璋冨害");
          }
        }
      } catch {
        // ignore polling errors and keep current UI state
      }
    };

    loadTask();
    if (["queued", "running"].includes(analysisResult?.status || "")) {
      timer = window.setInterval(loadTask, 2500);
    }

    return () => {
      cancelled = true;
      if (timer) {
        window.clearInterval(timer);
      }
    };
  }, [analysisResult?.task_id, analysisResult?.status]);

  const fileInfo = analysisResult?.file_info;
  const fileRows = fileInfo
    ? [
        { label: "文件名", value: fileInfo.filename, icon: FileText },
        { label: "文件创建日期", value: formatDate(fileInfo.created_at), icon: CalendarDays },
        { label: "文件修改日期", value: formatDate(fileInfo.modified_at), icon: CalendarDays },
        { label: "文件MD5", value: fileInfo.md5, icon: Hash, mono: true },
        { label: "文件SHA256", value: fileInfo.sha256, icon: Hash, mono: true },
      ]
    : fileInfoFields;

  const handleFileChange = (event) => {
    const file = event.target.files?.[0] ?? null;
    setSelectedFile(file);
    setAnalysisResult(null);
    setAnalysisMessage(file ? `已选择文件：${file.name}` : "");
  };

  const handleSubmit = async () => {
    if (requiresFile && !selectedFile) {
      setAnalysisMessage("请先选择要分析的文件");
      return;
    }
    if (!requiresFile && !taskInput.trim()) {
      setAnalysisMessage("请先填写任务目标或路径");
      return;
    }

    setSubmitting(true);
    setAnalysisMessage("正在提交任务到Task Pool");

    try {
      let response;
      if (requiresFile) {
        const formData = new FormData();
        formData.append("file", selectedFile);
        formData.append("analysis_type", module.taskType);
        formData.append("execution_mode", "agent");

        response = await fetch("/api/manager/program-analysis", {
          method: "POST",
          body: formData,
        });
      } else {
        response = await fetch("/api/tasks", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            task_type: module.taskType,
            wait: false,
            payload: {
              user_input: taskInput,
              target_path: taskInput,
              execution_mode: "agent",
            },
          }),
        });
      }
      const body = await response.json().catch(() => ({}));

      if (!response.ok) {
        throw new Error(body.detail || "任务提交失败");
      }

      setAnalysisResult(mergeTaskResultPayload(body, null));
      setAnalysisMessage("Task Pool已接收任务，正在实时同步执行过程");
    } catch (error) {
      setAnalysisMessage(error.message || "任务提交失败");
    } finally {
      setSubmitting(false);
    }
  };

  const exportJsonReport = () => {
    if (!analysisResult) {
      setAnalysisMessage("暂无可导出的报告");
      return;
    }
    const blob = new Blob([JSON.stringify(analysisResult, null, 2)], {
      type: "application/json",
    });
    const url = URL.createObjectURL(blob);
    const link = document.createElement("a");
    link.href = url;
    link.download = `${analysisResult.task_id || analysisResult.agent_id || module.taskType}-report.json`;
    link.click();
    URL.revokeObjectURL(url);
  };

  const structuredReport = analysisResult?.analysis_result?.structured_report ?? null;
  const assistantResponse =
    analysisResult?.analysis_result?.assistant_response ||
    analysisResult?.assistant_response ||
    "";
  const finalReportContent =
    formatStructuredReportPreview(structuredReport) ||
    assistantResponse ||
    analysisResult?.analysis_result?.summary ||
    "";
  const hasStructuredReport = Boolean(
    structuredReport && typeof structuredReport === "object" && structuredReport.report_type,
  );
  const timelineEntries = buildTaskTimelineEntries(taskEvents, analysisResult);
  const visibleTimelineEntries = timelineEntries;
  const runningState = ["queued", "running"].includes(analysisResult?.status || "");
  const normalizedTaskStatus = String(analysisResult?.status || "").toLowerCase();
  const resultSummaryTitle =
    analysisResult?.analysis_result?.summary ||
    (runningState
      ? "任务执行中，正在同步分析过程"
      : normalizedTaskStatus === "failed"
        ? analysisResult?.error || "任务执行失败"
        : normalizedTaskStatus === "completed"
          ? "报告已生成"
          : "尚未生成最终报告");

  React.useEffect(() => {
    if (!analysisResult?.session_id) {
      setTaskEvents([]);
      return undefined;
    }
    let cancelled = false;

    const loadEvents = async () => {
      try {
        const response = await fetch(
          `/api/manager/sessions/${analysisResult.session_id}/events?limit=1000`,
        );
        if (!response.ok) {
          return;
        }
        const body = await response.json();
        if (!cancelled) {
          setTaskEvents(Array.isArray(body) ? body : []);
        }
      } catch {
        // ignore event fetch errors
      }
    };

    loadEvents();
    if (!["queued", "running"].includes(analysisResult?.status || "")) {
      return () => {
        cancelled = true;
      };
    }
    const timer = window.setInterval(loadEvents, 2500);
    return () => {
      cancelled = true;
      window.clearInterval(timer);
    };
  }, [analysisResult?.session_id, analysisResult?.status]);

  const exportHtmlReport = async () => {
    if (!analysisResult) {
      setAnalysisMessage("暂无可导出的报告");
      return;
    }
    const reportTitle = `${module.name}报告`;
    const fileName =
      analysisResult?.file_info?.filename ||
      analysisResult?.task_id ||
      analysisResult?.agent_id ||
      module.taskType;
    const body = finalReportContent || "当前任务尚未生成可展示的最终报告内容。";
    const html = buildResultAreaHtmlReport({
      title: reportTitle,
      moduleName: module.name,
      taskId: analysisResult.task_id || analysisResult.agent_id || "",
      fileName,
      reportPath: analysisResult.report_path || "",
      fallbackBody: body,
    });
    const blob = new Blob([html], { type: "text/html;charset=utf-8" });
    const url = URL.createObjectURL(blob);
    const link = document.createElement("a");
    link.href = url;
    link.download = `${analysisResult.task_id || analysisResult.agent_id || module.taskType}-report.html`;
    link.click();
    URL.revokeObjectURL(url);
  };
  const toggleTimelineEntry = (entryId) => {
    setOpenTimelineEntryIds((current) =>
      current.includes(entryId)
        ? current.filter((id) => id !== entryId)
        : [...current, entryId],
    );
  };

  const timelinePanel = (
    <div className="task-progress-panel">
      <div className="assistant-response-head">
        <strong>实时执行过程</strong>
        <div className="task-progress-head-actions">
          <span className={`task-live-indicator ${runningState ? "live" : "idle"}`}>
              {runningState ? "同步中" : "已结束"}
          </span>
          <span className="task-progress-count">
              {timelineEntries.length ? `${timelineEntries.length} 条记录` : "暂无记录"}
          </span>
        </div>
      </div>
      {timelineEntries.length ? (
        <div className="task-timeline">
          {visibleTimelineEntries.map((entry) => {
            const canExpand = entry.canExpand !== false;
            const entryIsOpen = canExpand && openTimelineEntryIds.includes(entry.id);
            const showSummary = Boolean(entry.summary) && !(entry.compactWhenClosed && !entryIsOpen);
            const entryDetailText = entry.detailText || formatTimelineEntryDetail(entry);
            const entryTitle =
              entry.toolName && entry.title === "工具结果已返回"
                ? `${entry.toolName} 结果已返回`
                : entry.title;
            return (
              <div className={`task-timeline-item ${entry.status || "neutral"} ${canExpand ? "" : "compact"}`} key={entry.id}>
                <div className={`task-timeline-dot ${entry.status || "neutral"}`} aria-hidden="true" />
                <div className="task-timeline-copy accordion">
                  <button
                    className="task-timeline-trigger"
                    type="button"
                    onClick={() => {
                      if (canExpand) {
                        toggleTimelineEntry(entry.id);
                      }
                    }}
                    aria-expanded={entryIsOpen}
                    disabled={!canExpand}
                  >
                    <div className="task-timeline-top">
                      <div className="task-timeline-title-group">
                        {entry.step ? (
                          <span className="task-step-badge">
                            Step {entry.step}
                          </span>
                        ) : null}
                        <strong>{entryTitle}</strong>
                      </div>
                      <div className="task-timeline-meta-group">
                        <span className={`task-timeline-kind ${entry.status || "neutral"}`}>
                          {timelineKindLabel(entry)}
                        </span>
                        <span>{entry.time}</span>
                        {canExpand ? (
                          <span className="task-timeline-chevron">
                            {entryIsOpen ? "收起" : "展开"}
                          </span>
                        ) : null}
                      </div>
                    </div>
                    {showSummary ? <p>{entry.summary}</p> : null}
                  </button>
                  {entryIsOpen ? (
                    <div className="task-timeline-panel">
                      {entryDetailText ? (
                        <pre className="task-timeline-detail">
                          {entryDetailText}
                        </pre>
                      ) : null}
                      <div className="task-timeline-panel-actions">
                        <button
                          className="task-json-download"
                          type="button"
                          onClick={() => downloadTimelineEntryJson(entry)}
                        >
                          下载 JSON
                        </button>
                      </div>
                      <pre className="task-timeline-json">
                        {JSON.stringify(entry.jsonPayload, null, 2)}
                      </pre>
                    </div>
                  ) : null}
                </div>
              </div>
            );
          })}
        </div>
      ) : (
        <div className="task-progress-empty">
          <p>正在等待任务产生可展示的执行过程...</p>
        </div>
      )}
    </div>
  );

  return (
    <section className="program-analysis">
      <div className="module-toolbar">
        <button className="ghost-button" type="button" onClick={onBack}>
          <ChevronLeft size={18} strokeWidth={2.2} aria-hidden="true" />
          返回工作台
        </button>
        <span className="module-badge">{module.name}任务</span>
      </div>

      <section className="analysis-layout">
        <div className="analysis-main">
          <article className="analysis-card upload-card">
            <div className="card-heading">
              <div>
                <p className="card-kicker">任务布置</p>
                <h2>{requiresFile ? "上传任务文件" : "填写任务目标"}</h2>
              </div>
              <span className="card-icon">
                <UploadCloud size={22} strokeWidth={2.1} />
              </span>
            </div>

            {requiresFile ? (
              <label className="upload-zone" htmlFor="analysis-file">
                <input
                  id="analysis-file"
                  type="file"
                  aria-label="上传分析文件"
                  onChange={handleFileChange}
                />
                <UploadCloud size={34} strokeWidth={1.9} aria-hidden="true" />
                  <strong>{selectedFile ? selectedFile.name : "选择或拖放任务文件"}</strong>
                <span>
                  {selectedFile
                    ? `${formatBytes(selectedFile.size)}，点击提交后投入 Task Pool`
                      : "支持 EXE、DLL、APK、ZIP、源码包等文件类型"}
                </span>
              </label>
            ) : (
              <label className="config-field task-input-field">
                <span className="config-label">
                  <FileText size={16} strokeWidth={2.1} aria-hidden="true" />
                  任务目标或路径<strong>*</strong>
                </span>
                <textarea
                  value={taskInput}
                  onChange={(event) => setTaskInput(event.target.value)}
                  placeholder="填写目标路径、任务说明或待审计代码目录"
                  disabled={submitting}
                  rows={6}
                  required
                />
              </label>
            )}

            <div className="upload-actions">
              <button
                className="primary-action"
                type="button"
                onClick={handleSubmit}
                disabled={submitting || (requiresFile ? !selectedFile : !taskInput.trim())}
              >
                <UploadCloud size={18} strokeWidth={2.2} aria-hidden="true" />
                {submitting ? "执行中" : openedFromTaskBoard ? "重新提交任务" : "提交任务"}
              </button>
            </div>
            <p className={`analysis-status-message ${analysisResult ? "success" : ""}`}>
              {analysisMessage}
            </p>
          </article>

          <article className="analysis-card result-card">
            <div className="card-heading">
              <div>
                <p className="card-kicker">分析结果</p>
                <h2>结果展示区</h2>
              </div>
              <span className="card-icon muted">
                <Bug size={22} strokeWidth={2.1} />
              </span>
            </div>
            {analysisResult ? (
              <div className="result-details">
                <div className="result-summary">
                  <strong>{resultSummaryTitle}</strong>
                  <span>Task：{analysisResult.task_id || analysisResult.agent_id}</span>
                </div>
                {hasStructuredReport ? (
                  <StructuredReportView
                    report={structuredReport}
                    module={module}
                    assistantResponse={assistantResponse}
                  />
                ) : null}
                <div className="result-meta-grid">
                  <span>
                    LLM：
                    {analysisResult.llm?.allocated
                      ? analysisResult.llm.platform_name
                      : analysisResult.llm?.message || "未分配"}
                  </span>
                  <span>计划来源：{analysisResult.analysis_result?.plan_source || "未提供"}</span>
                  <span>报告：{analysisResult.report_path || "尚未生成"}</span>
                </div>
              </div>
            ) : (
              <div className="result-placeholder">
                <ScanSearch size={34} strokeWidth={1.8} aria-hidden="true" />
                <p>等待任务提交并完成后展示结果</p>
              </div>
            )}
          </article>
        </div>

        <aside className="analysis-side">
          <article className="analysis-card mode-card">
            <p className="card-kicker">任务类型</p>
            <div className="task-type-summary">
              <strong>{module.name}</strong>
              <span>{module.description}</span>
            </div>
          </article>

          <article className="analysis-card info-card">
            <div className="card-heading compact">
              <div>
                <p className="card-kicker">文件基本信息</p>
                <h2>元数据</h2>
              </div>
            </div>
            <dl className="file-info-list">
              {fileRows.map((field) => {
                const Icon = field.icon;

                return (
                  <div className="file-info-row" key={field.label}>
                    <dt>
                      <Icon size={16} strokeWidth={2.1} aria-hidden="true" />
                      {field.label}
                    </dt>
                    <dd className={field.mono ? "mono-value" : ""}>{field.value}</dd>
                  </div>
                );
              })}
            </dl>
          </article>

          <article className="analysis-card export-card">
            <div className="card-heading compact">
              <div>
                <p className="card-kicker">报告导出</p>
                <h2>导出报告</h2>
              </div>
              <span className="card-icon amber">
                <Download size={20} strokeWidth={2.1} />
              </span>
            </div>
            <div className="export-actions" aria-label="报告导出格式">
              <button type="button" disabled>
                PDF
              </button>
              <button type="button" onClick={exportHtmlReport} disabled={!analysisResult}>
                HTML
              </button>
              <button type="button" onClick={exportJsonReport} disabled={!analysisResult}>
                JSON
              </button>
            </div>
          </article>

          {timelinePanel}
        </aside>
      </section>
    </section>
  );
}

function StructuredReportView({ report, module, assistantResponse = "" }) {
  if (!report || typeof report !== "object") {
    return null;
  }

  if (report.report_type === "vulnerability-mining") {
    const executive = report.executive_summary ?? {};
    const findings = Array.isArray(report.findings) ? report.findings : [];
    const attackSurface = Array.isArray(report.attack_surface) ? report.attack_surface : [];
    const iocs = Array.isArray(report.iocs) ? report.iocs : [];
    const nextSteps = Array.isArray(report.next_steps) ? report.next_steps : [];
    const limitations = Array.isArray(report.limitations) ? report.limitations : [];

    return (
      <section className="structured-report-panel">
        <div className="structured-report-grid top">
          <SummaryMetric label="任务" value={module.name} tone="neutral" />
          <SummaryMetric
            label="总体风险"
            value={executive.overall_risk || "unknown"}
            tone={severityTone(executive.overall_risk)}
          />
          <SummaryMetric label="结论" value={executive.verdict || "未提供"} tone="accent" />
          <SummaryMetric
            label="置信度"
            value={executive.confidence || "unknown"}
            tone="neutral"
          />
        </div>

        <StructuredSection title="执行摘要">
          <p className="structured-lead">{executive.summary || "暂无摘要。"}</p>
          <div className="structured-inline-meta">
            <span>目标：{executive.affected_target || "未提供"}</span>
          </div>
        </StructuredSection>

        <div className="structured-report-grid split">
          <StructuredSection title="攻击面">
            <TagList items={attackSurface} emptyText="未识别到攻击面信息" />
          </StructuredSection>
          <StructuredSection title="后续建议">
            <BulletList items={nextSteps} emptyText="暂无后续建议" />
          </StructuredSection>
        </div>

        <StructuredSection title={`发现项 (${findings.length})`}>
          <div className="finding-card-list">
            {findings.length ? (
              findings.map((item, index) => (
                <article className="finding-card" key={item.id || `${item.title}-${index}`}>
                  <div className="finding-card-head">
                    <div className="finding-title-wrap">
                      <span className={`severity-pill ${severityTone(item.severity)}`}>
                        {item.severity || "unknown"}
                      </span>
                      <strong>{item.title || item.id || `发现项 ${index + 1}`}</strong>
                    </div>
                    <span className="finding-id">{item.id || `V-${index + 1}`}</span>
                  </div>
                  <div className="finding-meta-grid">
                    <InfoPill label="状态" value={item.status || "未提供"} />
                    <InfoPill label="分类" value={item.category || "未提供"} />
                    <InfoPill label="位置" value={item.location || "未提供"} />
                    <InfoPill label="置信度" value={item.confidence || "unknown"} />
                  </div>
                  <div className="finding-body-grid">
                    <StructuredMiniBlock title="影响">
                      {item.impact || "未提供影响描述"}
                    </StructuredMiniBlock>
                    <StructuredMiniBlock title="可利用性">
                      {item.exploitability || "未提供可利用性判断"}
                    </StructuredMiniBlock>
                  </div>
                  <div className="finding-body-grid">
                    <StructuredMiniBlock title="证据">
                      <BulletList items={item.evidence} emptyText="无证据条目" />
                    </StructuredMiniBlock>
                    <StructuredMiniBlock title="复现步骤">
                      <BulletList items={item.reproduction_steps} emptyText="暂无复现步骤" />
                    </StructuredMiniBlock>
                  </div>
                  <StructuredMiniBlock title="修复建议">
                    <BulletList items={item.remediation} emptyText="暂无修复建议" />
                  </StructuredMiniBlock>
                </article>
              ))
            ) : (
              <EmptyStructured text="当前没有结构化发现项。" />
            )}
          </div>
        </StructuredSection>

        <div className="structured-report-grid split">
          <StructuredSection title={`IOC (${iocs.length})`}>
            <IocTable rows={iocs} columns={["type", "value", "context"]} />
          </StructuredSection>
          <StructuredSection title="限制说明">
            <BulletList items={limitations} emptyText="暂无限制说明" />
          </StructuredSection>
        </div>
      </section>
    );
  }

  if (report.report_type === "sample-analysis") {
    const executive = report.executive_summary ?? {};
    const profile = report.sample_profile ?? {};
    const hashes = profile.hashes ?? {};
    const capabilities = Array.isArray(report.capabilities) ? report.capabilities : [];
    const iocs = Array.isArray(report.iocs) ? report.iocs : [];
    const detectionRecommendations = Array.isArray(report.detection_recommendations)
      ? report.detection_recommendations
      : [];
    const limitations = Array.isArray(report.limitations) ? report.limitations : [];
    const nextSteps = Array.isArray(report.next_steps) ? report.next_steps : [];
    const behavior = report.behavior_summary ?? {};
    const integrated = report.integrated_analysis ?? {};
    const hasIntegrated = integrated && Object.keys(integrated).length > 0;
    const threatIntelligence = report.threat_intelligence ?? {};
    const threatSummary = threatIntelligence.summary ?? {};
    const threatResponse = threatIntelligence.response ?? {};
    const hasThreatIntelligence =
      Boolean(threatIntelligence.enabled) || Object.keys(threatSummary).length > 0;
    const threatScore =
      integrated.threat_score ??
      threatSummary.threat_score ??
      threatResponse?.data?.summary?.threat_score ??
      "";
    const detectRate =
      integrated.detect_rate ||
      threatSummary.detect_rate ||
      threatSummary.multi_engines ||
      threatResponse?.data?.multiengines?.detect_rate ||
      "";
    const engineHits = Array.isArray(integrated.engine_hits)
      ? integrated.engine_hits
      : Array.isArray(threatSummary.engine_hits)
        ? threatSummary.engine_hits
        : [];
    const staticFindings = Array.isArray(integrated.static_findings)
      ? integrated.static_findings
      : Array.isArray(threatSummary.static_findings)
        ? threatSummary.static_findings
        : [];
    const networkActivity = Array.isArray(integrated.network_activity)
      ? integrated.network_activity
      : Array.isArray(threatSummary.network_activity)
        ? threatSummary.network_activity
        : [];
    const threatTags = Array.isArray(threatSummary.tags)
      ? threatSummary.tags
      : Array.isArray(threatSummary.tag)
        ? threatSummary.tag
        : [];
    const llmAnalysis = String(report.llm_analysis || assistantResponse || "").trim();
    const llmJudgement =
      report.llm_judgement && typeof report.llm_judgement === "object"
        ? report.llm_judgement
        : {};
    const deduplicatedIocs = Array.isArray(integrated.deduplicated_iocs)
      ? integrated.deduplicated_iocs
      : [];

    return (
      <section className="structured-report-panel">
        <div className="structured-report-grid top">
          <SummaryMetric label="任务" value={module.name} tone="neutral" />
          <SummaryMetric
            label="恶意性"
            value={executive.is_malicious ? "恶意" : "未证实"}
            tone={executive.is_malicious ? "high" : "neutral"}
          />
          <SummaryMetric
            label="严重性"
            value={executive.severity || "unknown"}
            tone={severityTone(executive.severity)}
          />
          <SummaryMetric
            label="置信度"
            value={executive.confidence || "unknown"}
            tone="accent"
          />
        </div>

        <StructuredSection title="执行摘要">
          <p className="structured-lead">{executive.summary || "暂无摘要。"}</p>
          <div className="structured-inline-meta">
            <span>结论：{executive.verdict || "未提供"}</span>
            <span>家族：{executive.family || "未识别"}</span>
          </div>
        </StructuredSection>

        {llmAnalysis || hasIntegrated || hasThreatIntelligence ? (
          <SampleOutcomePanel
            executive={executive}
            integrated={integrated}
            threatIntelligence={threatIntelligence}
            threatSummary={threatSummary}
            threatResponse={threatResponse}
            threatScore={threatScore}
            detectRate={detectRate}
            engineHits={engineHits}
            staticFindings={staticFindings}
            networkActivity={networkActivity}
            threatTags={threatTags}
            deduplicatedIocs={deduplicatedIocs}
            capabilities={capabilities}
            llmAnalysis={llmAnalysis}
            llmJudgement={llmJudgement}
          />
        ) : null}

        <StructuredSection title="样本画像">
          <div className="finding-meta-grid profile-grid">
            <InfoPill label="文件名" value={profile.file_name || "未提供"} />
            <InfoPill label="文件类型" value={profile.file_type || "未提供"} />
            <InfoPill label="架构" value={profile.architecture || "未提供"} />
            <InfoPill label="平台" value={profile.platform || "未提供"} />
            <InfoPill label="大小" value={profile.size_bytes || "0"} />
            <InfoPill label="MD5" value={hashes.md5 || "未提供"} mono />
            <InfoPill label="SHA256" value={hashes.sha256 || "未提供"} mono />
          </div>
        </StructuredSection>

        <StructuredSection title={`能力画像 (${capabilities.length})`}>
          <div className="finding-card-list">
            {capabilities.length ? (
              capabilities.map((item, index) => (
                <article className="finding-card capability-card" key={`${item.name}-${index}`}>
                  <div className="finding-card-head">
                    <div className="finding-title-wrap">
                      <span className={`severity-pill ${severityTone(item.confidence)}`}>
                        {item.confidence || "unknown"}
                      </span>
                      <strong>{item.name || `能力 ${index + 1}`}</strong>
                    </div>
                  </div>
                  <div className="finding-body-grid">
                    <StructuredMiniBlock title="证据">
                      <BulletList items={item.evidence} emptyText="无证据条目" />
                    </StructuredMiniBlock>
                    <StructuredMiniBlock title="MITRE">
                      <TagList items={item.mitre_techniques} emptyText="未映射到 MITRE" />
                    </StructuredMiniBlock>
                  </div>
                </article>
              ))
            ) : (
              <EmptyStructured text="当前没有结构化能力项。" />
            )}
          </div>
        </StructuredSection>

        <StructuredSection title="行为摘要">
          <div className="structured-report-grid behavior">
            <StructuredMiniBlock title="持久化">
              <BulletList items={behavior.persistence} emptyText="无" compact />
            </StructuredMiniBlock>
            <StructuredMiniBlock title="网络">
              <BulletList items={behavior.network} emptyText="无" compact />
            </StructuredMiniBlock>
            <StructuredMiniBlock title="文件系统">
              <BulletList items={behavior.filesystem} emptyText="无" compact />
            </StructuredMiniBlock>
            <StructuredMiniBlock title="进程">
              <BulletList items={behavior.process} emptyText="无" compact />
            </StructuredMiniBlock>
            <StructuredMiniBlock title="注册表">
              <BulletList items={behavior.registry} emptyText="无" compact />
            </StructuredMiniBlock>
            <StructuredMiniBlock title="规避">
              <BulletList items={behavior.defense_evasion} emptyText="无" compact />
            </StructuredMiniBlock>
          </div>
        </StructuredSection>

        <div className="structured-report-grid split">
          <StructuredSection title={`IOC (${iocs.length})`}>
            <IocTable rows={iocs} columns={["type", "value", "context", "severity"]} />
          </StructuredSection>
          {deduplicatedIocs.length ? (
            <StructuredSection title={`去重 IOC (${deduplicatedIocs.length})`}>
              <IocTable rows={deduplicatedIocs} columns={["type", "value", "context", "severity"]} />
            </StructuredSection>
          ) : null}
          <StructuredSection title="检测建议">
            <BulletList items={detectionRecommendations} emptyText="暂无检测建议" />
          </StructuredSection>
        </div>

        <div className="structured-report-grid split">
          <StructuredSection title="限制说明">
            <BulletList items={limitations} emptyText="暂无限制说明" />
          </StructuredSection>
          <StructuredSection title="后续动作">
            <BulletList items={nextSteps} emptyText="暂无后续动作" />
          </StructuredSection>
        </div>
      </section>
    );
  }

  return null;
}

function SampleOutcomePanel({
  executive = {},
  integrated = {},
  threatIntelligence = {},
  threatSummary = {},
  threatResponse = {},
  threatScore = "",
  detectRate = "",
  engineHits = [],
  staticFindings = [],
  networkActivity = [],
  threatTags = [],
  deduplicatedIocs = [],
  capabilities = [],
  llmAnalysis = "",
  llmJudgement = {},
}) {
  const parsedThreatbook = parseThreatbookResponse(threatResponse, threatSummary);
  const hasFixedJudgement = llmJudgement && Object.keys(llmJudgement).length > 0;
  const engineHitText = engineHits
    .filter((item) => item && typeof item === "object")
    .map((item) => `${item.engine || "unknown"}：${item.verdict || "命中"}`);
  const familyText =
    llmJudgement.family ||
    integrated.family ||
    parsedThreatbook.malwareFamily ||
    parsedThreatbook.malwareType ||
    executive.family ||
    "未识别";
  const confidenceText = llmJudgement.confidence || executive.confidence || "unknown";
  const conclusionCards = [
    {
      label: "综合结论",
      value:
        llmJudgement.final_verdict ||
        integrated.verdict ||
        executive.verdict ||
        parsedThreatbook.verdict ||
        "未提供",
      tone: severityTone(llmJudgement.severity || integrated.severity || executive.severity || parsedThreatbook.threatLevel),
    },
    {
      label: "威胁等级",
      value: llmJudgement.severity || integrated.severity || executive.severity || parsedThreatbook.threatLevel || "unknown",
      tone: severityTone(llmJudgement.severity || integrated.severity || executive.severity || parsedThreatbook.threatLevel),
    },
    {
      label: "威胁分 / 检出率",
      value: `${threatScore || parsedThreatbook.threatScore || "未提供"} / ${detectRate || parsedThreatbook.detectRate || "未提供"}`,
      tone: "accent",
    },
    {
      label: "家族 / 置信度",
      value: `${familyText} / ${confidenceText}`,
      tone: "neutral",
    },
  ];

  return (
    <section className="sample-outcome-panel">
      <div className="sample-outcome-head">
        <div>
          <span>完成态输出</span>
          <strong>样本分析综合研判</strong>
          <p>
            {integrated.fusion_note ||
              "已将 LLM 行为分析、结构化样本画像和威胁情报平台返回结果合并为单一结论视图。"}
          </p>
        </div>
        <span className={`severity-pill ${severityTone(executive.severity || parsedThreatbook.threatLevel)}`}>
          {executive.is_malicious ? "malicious" : executive.severity || parsedThreatbook.threatLevel || "unknown"}
        </span>
      </div>

      <div className="sample-conclusion-grid">
        {conclusionCards.map((item) => (
          <div className={`sample-conclusion-card ${item.tone}`} key={item.label}>
            <span>{item.label}</span>
            <strong>{String(item.value || "未提供")}</strong>
          </div>
        ))}
      </div>

      <div className="sample-outcome-grid">
        <article className="sample-analysis-column">
          <div className="sample-column-title">
            <span>LLM 固定研判</span>
            <strong>{hasFixedJudgement ? "固定字段" : `${capabilities.length} 个能力项`}</strong>
          </div>
          {hasFixedJudgement ? (
            <FixedLlmJudgementView judgement={llmJudgement} fallbackText={llmAnalysis} />
          ) : (
            <>
              <p className="structured-lead">{executive.summary || integrated.llm_summary || "暂无执行摘要。"}</p>
              {llmAnalysis ? <AnalysisNarrative text={llmAnalysis} /> : <EmptyStructured text="暂无 LLM 详细分析。" />}
            </>
          )}
        </article>

        <article className="sample-evidence-column">
          <div className="sample-column-title">
            <span>证据汇总</span>
            <strong>{threatIntelligence.platform_name || "ThreatBook"}</strong>
          </div>
          <div className="evidence-stack">
            <StructuredMiniBlock title="外部引擎命中">
              <BulletList items={engineHitText} emptyText="暂无多引擎命中" compact />
            </StructuredMiniBlock>
            <StructuredMiniBlock title="静态与网络信号">
              <BulletList
                items={[...staticFindings.slice(0, 5), ...networkActivity.slice(0, 5)]}
                emptyText="暂无静态或网络信号"
                compact
              />
            </StructuredMiniBlock>
            <StructuredMiniBlock title="情报标签">
              <TagList items={threatTags} emptyText="暂无标签" />
            </StructuredMiniBlock>
            <StructuredMiniBlock title="计数">
              <div className="evidence-count-grid">
                <span>引擎命中：{engineHits.length}</span>
                <span>能力项：{integrated.capability_count ?? capabilities.length}</span>
                <span>去重 IOC：{integrated.ioc_count ?? deduplicatedIocs.length}</span>
              </div>
            </StructuredMiniBlock>
          </div>
        </article>
      </div>

      <ThreatbookFixedJsonView
        parsed={parsedThreatbook}
        threatResponse={threatResponse}
        platformName={threatIntelligence.platform_name}
      />
    </section>
  );
}

function ThreatbookFixedJsonView({ parsed, threatResponse = {}, platformName = "" }) {
  const hasResponse = Object.keys(threatResponse || {}).length > 0;
  if (!hasResponse) {
    return (
      <section className="threatbook-json-panel">
        <div className="sample-column-title">
          <span>威胁情报解析</span>
          <strong>{platformName || "未配置"}</strong>
        </div>
        <EmptyStructured text="当前任务没有威胁情报平台原始结果。" />
      </section>
    );
  }

  return (
    <section className="threatbook-json-panel">
      <div className="sample-column-title">
        <span>ThreatBook 固定 JSON 解析</span>
        <strong>{platformName || "ThreatBook"}</strong>
      </div>

      <div className="threatbook-summary-grid">
        <InfoPill label="响应码" value={parsed.responseCode || "未提供"} />
        <InfoPill label="消息" value={parsed.message || "未提供"} />
        <InfoPill label="样本 SHA256" value={parsed.sha256 || "未提供"} mono />
        <InfoPill label="提交时间" value={parsed.submitTime || "未提供"} />
        <InfoPill label="最后检出" value={parsed.lastDetectionTime || "未提供"} />
        <InfoPill label="沙箱类型" value={parsed.sandboxType || "未提供"} />
      </div>

      <div className="threatbook-section-grid">
        <StructuredMiniBlock title="样本摘要">
          <div className="compact-kv-list">
            <span>文件名：{parsed.fileName || "未提供"}</span>
            <span>文件类型：{parsed.fileType || "未提供"}</span>
            <span>文件大小：{parsed.fileSize || "未提供"}</span>
            <span>恶意类型：{parsed.malwareType || "未提供"}</span>
            <span>恶意家族：{parsed.malwareFamily || "未提供"}</span>
          </div>
        </StructuredMiniBlock>
        <StructuredMiniBlock title={`多引擎检出 (${parsed.engineHits.length})`}>
          <div className="engine-hit-list">
            {parsed.engineHits.length ? (
              parsed.engineHits.slice(0, 12).map((item, index) => (
                <span key={`${item.engine}-${index}`}>
                  <strong>{item.engine}</strong>
                  {item.verdict}
                </span>
              ))
            ) : (
              <EmptyStructured text="暂无引擎命中。" />
            )}
          </div>
        </StructuredMiniBlock>
        <StructuredMiniBlock title="签名与标签">
          <TagList items={[...parsed.signatureNames, ...parsed.tags]} emptyText="暂无签名或标签" />
        </StructuredMiniBlock>
        <StructuredMiniBlock title="静态解析">
          <BulletList items={parsed.staticFindings} emptyText="暂无静态可疑信号" compact />
        </StructuredMiniBlock>
        <StructuredMiniBlock title="网络活动">
          <BulletList items={parsed.networkActivity} emptyText="暂无网络活动" compact />
        </StructuredMiniBlock>
      </div>

      <details className="threat-raw-console">
        <summary>
          <span>原始威胁情报 JSON</span>
          <small>保留完整字段用于核验</small>
        </summary>
        <PreBlock text={JSON.stringify(threatResponse, null, 2)} />
      </details>
    </section>
  );
}

function FixedLlmJudgementView({ judgement = {}, fallbackText = "" }) {
  const intel =
    judgement.threat_intel_interpretation &&
    typeof judgement.threat_intel_interpretation === "object"
      ? judgement.threat_intel_interpretation
      : {};
  const keyEvidence = Array.isArray(judgement.key_evidence) ? judgement.key_evidence : [];
  const behaviors = Array.isArray(judgement.behavior_judgement)
    ? judgement.behavior_judgement
    : [];
  const iocs = Array.isArray(judgement.iocs) ? judgement.iocs : [];
  const recommendations = Array.isArray(judgement.detection_recommendations)
    ? judgement.detection_recommendations
    : [];
  const actions = Array.isArray(judgement.response_actions) ? judgement.response_actions : [];
  const conflicts = Array.isArray(judgement.conflicts) ? judgement.conflicts : [];
  const limitations = Array.isArray(judgement.limitations) ? judgement.limitations : [];

  return (
    <div className="fixed-llm-judgement">
      <div className="llm-judgement-hero">
        <span className={`severity-pill ${severityTone(judgement.severity)}`}>
          {judgement.malicious_assessment || judgement.severity || "unknown"}
        </span>
        <div>
          <strong>{judgement.final_verdict || "暂无最终结论"}</strong>
          <p>{judgement.summary || fallbackText || "暂无摘要。"}</p>
        </div>
      </div>

      <div className="llm-field-grid">
        <InfoPill label="严重性" value={judgement.severity || "unknown"} />
        <InfoPill label="置信度" value={judgement.confidence || "unknown"} />
        <InfoPill label="家族" value={judgement.family || "未识别"} />
        <InfoPill label="恶意性" value={judgement.malicious_assessment || "需复核"} />
      </div>

      <div className="llm-judgement-grid">
        <StructuredMiniBlock title={`关键证据 (${keyEvidence.length})`}>
          <EvidenceCardList items={keyEvidence} />
        </StructuredMiniBlock>
        <StructuredMiniBlock title="威胁情报解读">
          <div className="compact-kv-list">
            <span>威胁等级：{intel.threat_level || "未提供"}</span>
            <span>威胁分：{intel.threat_score || "未提供"}</span>
            <span>检出率：{intel.detect_rate || "未提供"}</span>
            <span>类型：{intel.malware_type || "未提供"}</span>
            <span>家族：{intel.malware_family || "未提供"}</span>
            <span>解读：{intel.meaning || "未提供"}</span>
          </div>
        </StructuredMiniBlock>
        <StructuredMiniBlock title={`行为与能力 (${behaviors.length})`}>
          <BehaviorJudgementList items={behaviors} />
        </StructuredMiniBlock>
        <StructuredMiniBlock title={`IOC (${iocs.length})`}>
          <IocTable rows={iocs} columns={["type", "value", "context", "severity"]} />
        </StructuredMiniBlock>
        <StructuredMiniBlock title="检测建议">
          <BulletList items={recommendations} emptyText="暂无检测建议" compact />
        </StructuredMiniBlock>
        <StructuredMiniBlock title="处置建议">
          <BulletList items={actions} emptyText="暂无处置建议" compact />
        </StructuredMiniBlock>
        <StructuredMiniBlock title="冲突与限制">
          <BulletList items={[...conflicts, ...limitations]} emptyText="暂无冲突或限制" compact />
        </StructuredMiniBlock>
      </div>
    </div>
  );
}

function EvidenceCardList({ items }) {
  const list = Array.isArray(items) ? items : [];
  if (!list.length) {
    return <EmptyStructured text="暂无关键证据。" />;
  }
  return (
    <div className="evidence-card-list">
      {list.map((item, index) => (
        <article className="evidence-card" key={`${item.title || item.detail || "evidence"}-${index}`}>
          <div>
            <span>{item.source || "evidence"}</span>
            <strong>{item.title || `证据 ${index + 1}`}</strong>
          </div>
          <p>{item.detail || "未提供详情"}</p>
          <small>{item.weight || "unknown"}</small>
        </article>
      ))}
    </div>
  );
}

function BehaviorJudgementList({ items }) {
  const list = Array.isArray(items) ? items : [];
  if (!list.length) {
    return <EmptyStructured text="暂无行为研判。" />;
  }
  return (
    <div className="behavior-judgement-list">
      {list.map((item, index) => (
        <article className="behavior-judgement-card" key={`${item.category || "behavior"}-${index}`}>
          <strong>{item.category || "其他"}</strong>
          <p>{item.assessment || "未提供研判"}</p>
          <BulletList
            items={Array.isArray(item.evidence) ? item.evidence : [item.evidence].filter(Boolean)}
            emptyText="暂无证据"
            compact
          />
        </article>
      ))}
    </div>
  );
}

function parseThreatbookResponse(threatResponse = {}, threatSummary = {}) {
  const data = threatResponse?.data && typeof threatResponse.data === "object" ? threatResponse.data : {};
  const summary = data.summary && typeof data.summary === "object" ? data.summary : {};
  const multiengines =
    data.multiengines && typeof data.multiengines === "object" ? data.multiengines : {};
  const staticDetails =
    data.static?.details && typeof data.static.details === "object" ? data.static.details : {};
  const engineResult =
    multiengines.result && typeof multiengines.result === "object" ? multiengines.result : {};
  const safeValues = new Set(["", "safe", "clean", "undetected", "none", "ok"]);
  const engineHits = Object.entries(engineResult)
    .map(([engine, verdict]) => ({ engine, verdict: String(verdict || "").trim() }))
    .filter((item) => !safeValues.has(item.verdict.toLowerCase()));
  const signatureNames = Array.isArray(data.signature)
    ? data.signature
        .map((item) => (item && typeof item === "object" ? item.name || item.sig_name : ""))
        .filter(Boolean)
    : [];
  const tags = normalizeTagArray(summary.tags || summary.tag || threatSummary.tags || threatSummary.tag);
  return {
    responseCode: threatResponse.response_code || threatSummary.response_code || "",
    message: threatResponse.verbose_msg || threatResponse.msg || threatSummary.verbose_msg || "",
    verdict: summary.threat_level || threatSummary.threat_level || "",
    threatLevel: summary.threat_level || threatSummary.threat_level || "",
    threatScore: summary.threat_score || threatSummary.threat_score || "",
    detectRate: multiengines.detect_rate || summary.multi_engines || threatSummary.detect_rate || "",
    sha256: summary.sample_sha256 || data.sample_sha256 || "",
    fileName: summary.file_name || data.file_name || "",
    fileType: summary.file_type || data.file_type || "",
    fileSize: summary.file_size || data.file_size || "",
    malwareType: summary.malware_type || threatSummary.malware_type || "",
    malwareFamily: summary.malware_family || threatSummary.malware_family || "",
    submitTime: summary.submit_time || data.submit_time || "",
    lastDetectionTime: summary.last_detection_time || data.last_detection_time || "",
    sandboxType: summary.sandbox_type || data.sandbox_type || "",
    engineHits,
    signatureNames,
    tags,
    staticFindings: extractThreatbookStaticFindings(staticDetails, threatSummary.static_findings),
    networkActivity: extractThreatbookNetworkActivity(data.network, threatSummary.network_activity),
  };
}

function normalizeTagArray(rawTags) {
  const tags = [];
  const append = (value) => {
    if (!value) {
      return;
    }
    if (Array.isArray(value)) {
      value.forEach(append);
      return;
    }
    if (typeof value === "object") {
      Object.values(value).forEach(append);
      return;
    }
    const text = String(value).trim();
    if (text && !tags.includes(text)) {
      tags.push(text);
    }
  };
  append(rawTags);
  return tags;
}

function extractThreatbookStaticFindings(details, fallback) {
  const findings = Array.isArray(fallback) ? fallback.filter(Boolean).map(String) : [];
  const importsText = JSON.stringify(details?.pe_imports || details?.imports || []);
  ["IsDebuggerPresent", "VirtualAlloc", "VirtualProtect", "WriteProcessMemory", "CreateRemoteThread"].forEach(
    (apiName) => {
      if (importsText.includes(apiName) && !findings.includes(apiName)) {
        findings.push(apiName);
      }
    },
  );
  const sections = Array.isArray(details?.pe_sections) ? details.pe_sections : [];
  sections.forEach((section) => {
    const name = String(section?.name || "unknown");
    const characteristics = String(section?.characteristics || "").toUpperCase();
    if ((characteristics.includes("W") && characteristics.includes("X")) || characteristics.includes("RWE")) {
      findings.push(`可写可执行 PE 节：${name}`);
    }
  });
  return [...new Set(findings)].slice(0, 12);
}

function extractThreatbookNetworkActivity(network, fallback) {
  const values = Array.isArray(fallback) ? fallback.filter(Boolean).map(String) : [];
  if (network && typeof network === "object") {
    ["domains", "hosts", "dns", "http", "tcp", "udp"].forEach((key) => {
      const item = network[key];
      if (Array.isArray(item)) {
        item.slice(0, 6).forEach((value) => values.push(`${key}: ${normalizeDebugValue(value)}`));
      } else if (item && typeof item === "object") {
        values.push(`${key}: ${normalizeDebugValue(item)}`);
      }
    });
  }
  return [...new Set(values)].slice(0, 12);
}

function normalizeDebugValue(value) {
  if (value === null || value === undefined) {
    return "";
  }
  if (typeof value === "object") {
    try {
      return JSON.stringify(value);
    } catch (_error) {
      return String(value);
    }
  }
  return String(value);
}

function ThreatFusionPanel({
  integrated = {},
  threatIntelligence = {},
  threatSummary = {},
  threatScore = "",
  detectRate = "",
  engineHits = [],
  staticFindings = [],
  networkActivity = [],
  threatTags = [],
  deduplicatedIocs = [],
  capabilities = [],
}) {
  const engineHitText = engineHits
    .filter((item) => item && typeof item === "object")
    .map((item) => `${item.engine || "unknown"}：${item.verdict || "命中"}`);
  const threatSignals = Array.isArray(integrated.threat_signals)
    ? integrated.threat_signals
    : [];

  return (
    <section className="threat-fusion-panel">
      <div className="threat-fusion-head">
        <div>
          <span className="threat-fusion-eyebrow">威胁情报融合研判</span>
          <strong>{integrated.verdict || threatSummary.threat_level || "等待外部情报结论"}</strong>
          <p>
            {integrated.fusion_note ||
              "已将 LLM 分析结果与威胁情报平台返回的信誉、检出和静态信号合并展示。"}
          </p>
        </div>
        <span className={`severity-pill ${severityTone(integrated.severity || threatSummary.threat_level)}`}>
          {integrated.severity || threatSummary.threat_level || "unknown"}
        </span>
      </div>

      <div className="threat-score-grid">
        <div className="threat-score-card">
          <span>威胁分</span>
          <strong>{String(threatScore || "未提供")}</strong>
        </div>
        <div className="threat-score-card">
          <span>多引擎检出</span>
          <strong>{String(detectRate || "未提供")}</strong>
        </div>
        <div className="threat-score-card">
          <span>外部引擎命中</span>
          <strong>{engineHits.length}</strong>
        </div>
        <div className="threat-score-card">
          <span>去重 IOC</span>
          <strong>{integrated.ioc_count ?? deduplicatedIocs.length}</strong>
        </div>
        <div className="threat-score-card">
          <span>能力项</span>
          <strong>{integrated.capability_count ?? capabilities.length}</strong>
        </div>
        <div className="threat-score-card">
          <span>平台状态</span>
          <strong>{threatIntelligence.status || (threatIntelligence.enabled ? "enabled" : "未配置")}</strong>
        </div>
      </div>

      <div className="threat-signal-grid">
        <StructuredMiniBlock title="引擎命中">
          <BulletList items={engineHitText} emptyText="暂无多引擎命中" compact />
        </StructuredMiniBlock>
        <StructuredMiniBlock title="静态可疑信号">
          <BulletList items={staticFindings} emptyText="暂无静态可疑信号" compact />
        </StructuredMiniBlock>
        <StructuredMiniBlock title="网络活动">
          <BulletList items={networkActivity} emptyText="暂无网络活动记录" compact />
        </StructuredMiniBlock>
        <StructuredMiniBlock title="标签">
          <TagList items={threatTags} emptyText="暂无标签" />
        </StructuredMiniBlock>
      </div>

      {threatSignals.length ? (
        <div className="threat-signal-strip">
          {threatSignals.slice(0, 8).map((item, index) => (
            <span key={`${item}-${index}`}>{item}</span>
          ))}
        </div>
      ) : null}
    </section>
  );
}

function DeepAnalysisEvidencePanel({
  llmAnalysis = "",
  threatResponse = {},
  threatSummary = {},
  integrated = {},
  engineHits = [],
  staticFindings = [],
  networkActivity = [],
  threatTags = [],
  threatScore = "",
  detectRate = "",
  platformName = "",
}) {
  const rawJson = Object.keys(threatResponse).length
    ? JSON.stringify(threatResponse, null, 2)
    : "";
  const engineHitText = engineHits
    .filter((item) => item && typeof item === "object")
    .slice(0, 8)
    .map((item) => `${item.engine || "unknown"}：${item.verdict || "命中"}`);
  const quickFacts = [
    { label: "融合结论", value: integrated.verdict || threatSummary.threat_level || "未提供" },
    { label: "威胁分", value: threatScore || "未提供" },
    { label: "多引擎检出", value: detectRate || "未提供" },
    { label: "恶意家族", value: threatSummary.malware_family || integrated.family || "未识别" },
  ];

  return (
    <section className="deep-analysis-panel">
      <div className="deep-analysis-head">
        <div>
          <span>深度分析与情报证据</span>
          <strong>LLM 研判与威胁情报原始结果</strong>
        </div>
        <div className="deep-analysis-status">
          <span>{llmAnalysis ? "LLM 已生成" : "无 LLM 详情"}</span>
          <span>{rawJson ? "原始情报可核验" : "无原始情报"}</span>
        </div>
      </div>

      <div className="deep-analysis-body">
        <article className="llm-analysis-card">
          <div className="analysis-card-title">
            <span>LLM 详细分析</span>
            <strong>{integrated.severity || threatSummary.threat_level || "analyst view"}</strong>
          </div>
          {llmAnalysis ? <AnalysisNarrative text={llmAnalysis} /> : <EmptyStructured text="暂无 LLM 详细分析。" />}
        </article>

        <aside className="threat-evidence-card">
          <div className="analysis-card-title">
            <span>威胁情报证据</span>
            <strong>{platformName || "Threat Intel"}</strong>
          </div>

          <div className="threat-fact-grid">
            {quickFacts.map((item) => (
              <div className="threat-fact" key={item.label}>
                <span>{item.label}</span>
                <strong>{String(item.value || "未提供")}</strong>
              </div>
            ))}
          </div>

          <StructuredMiniBlock title="引擎命中">
            <BulletList items={engineHitText} emptyText="暂无多引擎命中" compact />
          </StructuredMiniBlock>
          <StructuredMiniBlock title="静态与网络信号">
            <BulletList
              items={[...staticFindings.slice(0, 4), ...networkActivity.slice(0, 4)]}
              emptyText="暂无静态或网络信号"
              compact
            />
          </StructuredMiniBlock>
          <StructuredMiniBlock title="情报标签">
            <TagList items={threatTags} emptyText="暂无标签" />
          </StructuredMiniBlock>

          {rawJson ? (
            <details className="threat-raw-console">
              <summary>
                <span>原始威胁情报 JSON</span>
                <small>展开核验平台返回字段</small>
              </summary>
              <PreBlock text={rawJson} />
            </details>
          ) : null}
        </aside>
      </div>
    </section>
  );
}

function AnalysisNarrative({ text }) {
  const blocks = String(text || "")
    .split(/\n{2,}/)
    .map((item) => item.trim())
    .filter(Boolean);
  if (!blocks.length) {
    return <EmptyStructured text="暂无分析内容。" />;
  }
  return (
    <div className="analysis-narrative">
      {blocks.map((item, index) => (
        <p key={`${item.slice(0, 24)}-${index}`}>{item}</p>
      ))}
    </div>
  );
}

function StructuredSection({ title, children }) {
  return (
    <section className="structured-section">
      <div className="structured-section-head">
        <strong>{title}</strong>
      </div>
      <div className="structured-section-body">{children}</div>
    </section>
  );
}

function StructuredMiniBlock({ title, children }) {
  return (
    <div className="structured-mini-block">
      <span className="structured-mini-title">{title}</span>
      <div className="structured-mini-body">{children}</div>
    </div>
  );
}

function SummaryMetric({ label, value, tone = "neutral" }) {
  return (
    <div className={`summary-metric ${tone}`}>
      <span>{label}</span>
      <strong>{String(value || "未提供")}</strong>
    </div>
  );
}

function InfoPill({ label, value, mono = false }) {
  return (
    <div className={`info-pill ${mono ? "mono" : ""}`}>
      <span>{label}</span>
      <strong>{String(value || "未提供")}</strong>
    </div>
  );
}

function TagList({ items, emptyText = "暂无数据" }) {
  const list = Array.isArray(items) ? items.filter(Boolean) : [];
  if (!list.length) {
    return <EmptyStructured text={emptyText} />;
  }
  return (
    <div className="tag-list">
      {list.map((item, index) => (
        <span className="tag-chip" key={`${item}-${index}`}>
          {item}
        </span>
      ))}
    </div>
  );
}

function BulletList({ items, emptyText = "暂无数据", compact = false }) {
  const list = Array.isArray(items) ? items.filter(Boolean) : [];
  if (!list.length) {
    return <EmptyStructured text={emptyText} />;
  }
  return (
    <ul className={`structured-list ${compact ? "compact" : ""}`}>
      {list.map((item, index) => (
        <li key={`${item}-${index}`}>{item}</li>
      ))}
    </ul>
  );
}

function IocTable({ rows, columns }) {
  const list = Array.isArray(rows) ? rows : [];
  if (!list.length) {
    return <EmptyStructured text="暂无 IOC 数据" />;
  }
  const labels = {
    type: "类型",
    value: "值",
    context: "上下文",
    severity: "严重性",
  };
  return (
    <div className="ioc-table-wrap">
      <table className="ioc-table">
        <thead>
          <tr>
            {columns.map((column) => (
              <th key={column}>{labels[column] || column}</th>
            ))}
          </tr>
        </thead>
        <tbody>
          {list.map((row, index) => (
            <tr key={`${row.value || row.type || "ioc"}-${index}`}>
              {columns.map((column) => (
                <td key={column}>{row?.[column] || "未提供"}</td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function PreBlock({ text }) {
  return <pre className="structured-pre">{String(text || "")}</pre>;
}

function EmptyStructured({ text }) {
  return <p className="empty-structured">{text}</p>;
}

function severityTone(value) {
  const text = String(value || "").toLowerCase();
  if (["critical", "high", "严重", "高"].includes(text)) {
    return "high";
  }
  if (["medium", "中"].includes(text)) {
    return "medium";
  }
  if (["low", "低"].includes(text)) {
    return "low";
  }
  return "neutral";
}

function getWorkbenchModuleByTaskType(taskType) {
  return workbenchModules.find((item) => item.taskType === taskType) ?? null;
}

function taskStatusText(status) {
  const normalized = String(status || "").toLowerCase();
  if (normalized === "completed") {
    return "已完成";
  }
  if (normalized === "running") {
    return "进行中";
  }
  if (normalized === "queued") {
    return "排队中";
  }
  if (normalized === "failed") {
    return "失败";
  }
  return normalized || "未知";
}

function summarizeTaskBoardMeta(task) {
  const resultSummary =
    task?.result?.analysis_result?.summary ||
    task?.analysis_result?.summary ||
    task?.result?.assistant_response ||
    task?.assistant_response ||
    "";
  if (resultSummary) {
    return String(resultSummary).slice(0, 72);
  }
  if (task?.updated_at) {
    return `最近更新：${formatDate(task.updated_at)}`;
  }
  return "点击进入查看任务详情";
}

function mergeTaskResultPayload(payload, fallback) {
  const source = payload && typeof payload === "object" ? payload : {};
  const base =
    fallback && typeof fallback === "object"
      ? { ...fallback }
      : {};
  const taskBlock =
    source.task && typeof source.task === "object"
      ? source.task
      : {};
  const resultBlock =
    taskBlock.result && typeof taskBlock.result === "object"
      ? taskBlock.result
      : source.result && typeof source.result === "object"
        ? source.result
        : {};
  const hasFreshTask = Boolean(source.task || source.task_id || source.id || source.status);

  return {
    ...base,
    ...taskBlock,
    ...resultBlock,
    ...source,
    task_id:
      source.task_id ||
      taskBlock.task_id ||
      taskBlock.id ||
      resultBlock.task_id ||
      base.task_id ||
      "",
    agent_id:
      source.agent_id ||
      taskBlock.agent_id ||
      resultBlock.agent_id ||
      base.agent_id ||
      "",
    file_info:
      source.file_info ||
      resultBlock.file_info ||
      taskBlock.result?.file_info ||
      base.file_info ||
      null,
    llm:
      source.llm ||
      resultBlock.llm ||
      base.llm ||
      null,
    tool_results:
      source.tool_results ||
      resultBlock.tool_results ||
      base.tool_results ||
      [],
    runtime_trace:
      source.runtime_trace ||
      resultBlock.runtime_trace ||
      base.runtime_trace ||
      [],
    analysis_result:
      source.analysis_result ||
      resultBlock.analysis_result ||
      base.analysis_result ||
      {},
    report_path:
      source.report_path ||
      resultBlock.report_path ||
      taskBlock.report_path ||
      (hasFreshTask ? "" : base.report_path) ||
      "",
    assistant_response:
      source.assistant_response ||
      resultBlock.assistant_response ||
      base.assistant_response ||
      "",
    status:
      source.status ||
      taskBlock.status ||
      resultBlock.status ||
      base.status ||
      "",
  };
}

function matchTaskFilter(task, filter) {
  if (filter === "all") {
    return true;
  }
  return String(task?.status || "").toLowerCase() === filter;
}

function taskReportUrl(task) {
  const normalizedStatus = String(task?.status || "").toLowerCase();
  const reportPath = String(task?.report_path || task?.result?.report_path || "").trim();
  const taskId = task?.task_id || task?.id || task?.agent_id || "";
  if (normalizedStatus !== "completed" || !reportPath) {
    return "";
  }
  const normalizedPath = reportPath.replaceAll("\\", "/");
  const fileName = normalizedPath.split("/").filter(Boolean).pop();
  if (fileName) {
    return `/reports/${encodeURIComponent(fileName)}`;
  }
  if (!taskId) {
    return "";
  }
  return `/reports/${encodeURIComponent(`${taskId}.html`)}`;
}

function downloadTaskJson(task, fallbackType = "task") {
  const taskId = task?.task_id || task?.id || fallbackType;
  const blob = new Blob([JSON.stringify(task, null, 2)], {
    type: "application/json",
  });
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = `${taskId}-snapshot.json`;
  link.click();
  URL.revokeObjectURL(url);
}

function compareTaskBoardItems(left, right) {
  const statusRank = {
    running: 0,
    queued: 1,
    failed: 2,
    completed: 3,
  };
  const leftRank = statusRank[String(left?.status || "").toLowerCase()] ?? 9;
  const rightRank = statusRank[String(right?.status || "").toLowerCase()] ?? 9;
  if (leftRank !== rightRank) {
    return leftRank - rightRank;
  }
  const leftTs = taskSortTimestamp(left);
  const rightTs = taskSortTimestamp(right);
  return rightTs - leftTs;
}

function taskSortTimestamp(task) {
  const value =
    task?.updated_at ||
    task?.completed_at ||
    task?.started_at ||
    task?.created_at ||
    "";
  const ts = Date.parse(String(value));
  return Number.isFinite(ts) ? ts : 0;
}

function matchModuleFilter(task, filter) {
  if (filter === "all") {
    return true;
  }
  return String(task?.task_type || "") === filter;
}

function matchTaskSearch(task, query) {
  const normalized = String(query || "").trim().toLowerCase();
  if (!normalized) {
    return true;
  }
  const haystack = [
    task?.task_id,
    task?.id,
    task?.task_type,
    task?.task_name,
    task?.file_info?.filename,
    task?.result?.file_info?.filename,
    task?.analysis_result?.summary,
    task?.result?.analysis_result?.summary,
    task?.assistant_response,
    task?.result?.assistant_response,
  ]
    .filter(Boolean)
    .join(" ")
    .toLowerCase();
  return haystack.includes(normalized);
}

function summarizeTaskStats(tasks) {
  const stats = {
    total: 0,
    running: 0,
    queued: 0,
    completed: 0,
    failed: 0,
  };
  for (const task of Array.isArray(tasks) ? tasks : []) {
    if (!getWorkbenchModuleByTaskType(task?.task_type)) {
      continue;
    }
    stats.total += 1;
    const status = String(task?.status || "").toLowerCase();
    if (status in stats) {
      stats[status] += 1;
    }
  }
  return stats;
}

function taskTargetLabel(task) {
  const fileName =
    task?.file_info?.filename ||
    task?.result?.file_info?.filename ||
    task?.result?.file_info?.path ||
    "";
  return fileName ? `目标：${fileName}` : "目标：未提供";
}

function taskUpdatedLabel(task) {
  const value =
    task?.updated_at ||
    task?.completed_at ||
    task?.started_at ||
    task?.created_at ||
    "";
  return value ? `更新时间：${formatDate(value)}` : "更新时间：未知";
}

function buildTaskTimelineEntries(events, analysisResult) {
  const list = Array.isArray(events) ? events : [];
  const entries = [];
  let stepNumber = 0;

  for (const event of list) {
    if (!event || typeof event !== "object") {
      continue;
    }
    const type = String(event.type || "");
    const payload = event.payload && typeof event.payload === "object" ? event.payload : {};
    const createdAt = formatDate(event.created_at);

    if (type === "task_loop_decision") {
      stepNumber += 1;
      entries.push({
        id: event.id || `${type}-${entries.length}`,
        kind: "analysis",
        step: stepNumber,
        status: "analysis",
        title: `分析步骤 ${stepNumber}`,
        summary: "",
        time: createdAt,
        canExpand: false,
        compactWhenClosed: true,
      });
      continue;
    }

    if (type === "task_loop_agent_started") {
      entries.push({
        id: event.id || `${type}-${entries.length}`,
        kind: "analysis",
        status: "analysis",
        title: "Claude Code 已启动",
        summary: String(payload.command || "任务已委托给 Claude Code CLI。").slice(0, 220),
        time: createdAt,
        jsonPayload: {
          event_type: type,
          created_at: event.created_at,
          payload,
        },
        downloadName: "claude-code-started.json",
      });
      continue;
    }

    if (type === "task_loop_agent_completed" || type === "task_loop_agent_failed") {
      const failed = type.endsWith("_failed");
      entries.push({
        id: event.id || `${type}-${entries.length}`,
        kind: "tool",
        status: failed ? "failed" : "success",
        title: failed ? "Claude Code 执行失败" : "Claude Code 执行完成",
        summary: String(
          payload.stdout_preview ||
            payload.stderr_preview ||
            payload.error ||
            "Claude Code 已返回执行结果。",
        ).slice(0, 220),
        time: createdAt,
        jsonPayload: {
          event_type: type,
          created_at: event.created_at,
          payload,
        },
        downloadName: failed ? "claude-code-failed.json" : "claude-code-completed.json",
      });
      continue;
    }

    if (type === "threat_intelligence_report") {
      const status = String(payload.status || "");
      const summary = payload.summary && typeof payload.summary === "object" ? payload.summary : {};
      entries.push({
        id: event.id || `${type}-${entries.length}`,
        kind: "tool",
        status: status === "failed" ? "failed" : "success",
        title: "威胁情报查询完成",
        summary: String(
          summary.detect_rate ||
            summary.multi_engines ||
            summary.threat_level ||
            payload.error ||
            "威胁情报平台已返回结果。",
        ).slice(0, 220),
        time: createdAt,
        jsonPayload: {
          event_type: type,
          created_at: event.created_at,
          payload,
        },
        downloadName: "threat-intelligence-report.json",
      });
      continue;
    }

    if (
      type === "final_synthesis_started" ||
      type === "final_synthesis_completed" ||
      type === "final_synthesis_failed"
    ) {
      const failed = type === "final_synthesis_failed";
      const completed = type === "final_synthesis_completed";
      entries.push({
        id: event.id || `${type}-${entries.length}`,
        kind: completed ? "result" : failed ? "tool" : "analysis",
        status: failed ? "failed" : completed ? "success" : "analysis",
        title: completed
          ? "最终分析整理完成"
          : failed
            ? "最终分析整理失败"
            : "最终分析整理中",
        summary: String(
          payload.preview ||
            payload.error ||
            "正在将 LLM 分析与威胁情报结果交给 LLM 进行最终归纳。",
        ).slice(0, 220),
        time: createdAt,
        jsonPayload: {
          event_type: type,
          created_at: event.created_at,
          payload,
        },
        downloadName: `${type}.json`,
      });
      continue;
    }

    if (type === "tool_result") {
      const toolPayload =
        payload.payload && typeof payload.payload === "object" ? payload.payload : payload;
      const rendered =
        toolPayload.rendered && typeof toolPayload.rendered === "object"
          ? toolPayload.rendered
          : {};
      const toolName =
        toolPayload.tool_name ||
        payload.tool_name ||
        toolPayload.tool ||
        "Tool";
      const status = String(toolPayload.status || payload.status || "");
      if (status === "success") {
        entries.push({
          id: event.id || `${type}-${entries.length}`,
          kind: "tool",
          status: "success",
          title: `${toolName} 执行成功`,
          summary:
            String(
              rendered.summary ||
                rendered.transcript ||
                "已成功获取新的工具结果。",
            ).slice(0, 220),
          time: createdAt,
          jsonPayload: {
            event_type: type,
            created_at: event.created_at,
            payload,
          },
          downloadName: `${String(toolName).replace(/\s+/g, "-").toLowerCase()}-success.json`,
        });
      } else if (status) {
        entries.push({
          id: event.id || `${type}-${entries.length}`,
          kind: "tool",
          status: "failed",
          title: `${toolName} 执行失败`,
          summary:
            String(
              rendered.summary ||
                toolPayload.error ||
                "工具执行失败。",
            ).slice(0, 220),
          time: createdAt,
          jsonPayload: {
            event_type: type,
            created_at: event.created_at,
            payload,
          },
          downloadName: `${String(toolName).replace(/\s+/g, "-").toLowerCase()}-failed.json`,
        });
      }
      continue;
    }

    if (type === "task_loop_no_tool_call") {
      entries.push({
        id: event.id || `${type}-${entries.length}`,
        kind: "analysis",
        status: "analysis",
        title: "等待有效工具调用",
        summary: String(payload.content || "模型说明了下一步意图，但未返回工具调用，平台已要求继续。").slice(0, 220),
        time: createdAt,
        jsonPayload: {
          event_type: type,
          created_at: event.created_at,
          payload,
        },
        downloadName: "task-loop-no-tool-call.json",
      });
      continue;
    }

    if (type === "task_completed") {
      entries.push({
        id: event.id || `${type}-${entries.length}`,
        kind: "result",
        status: "completed",
        title: "任务完成",
        summary: String(payload.summary || "任务已完成并生成结果。"),
        time: createdAt,
        jsonPayload: {
          event_type: type,
          created_at: event.created_at,
          payload,
        },
        downloadName: "task-completed.json",
      });
      continue;
    }

    if (type === "task_failed") {
      entries.push({
        id: event.id || `${type}-${entries.length}`,
        kind: "result",
        status: "failed",
        title: "任务失败",
        summary: String(payload.error || "任务执行失败。"),
        time: createdAt,
        jsonPayload: {
          event_type: type,
          created_at: event.created_at,
          payload,
        },
        downloadName: "task-failed.json",
      });
    }
  }

  if (entries.length) {
    return entries.reverse();
  }

  const taskStatus = String(analysisResult?.status || "").toLowerCase();
  if (!["completed", "failed"].includes(taskStatus)) {
    const runtimeEntries = buildRuntimeTraceEntries(analysisResult, []);
    if (runtimeEntries.length) {
      return runtimeEntries;
    }
  }

  const toolResults = Array.isArray(analysisResult?.tool_results)
    ? analysisResult.tool_results
    : [];
  return toolResults
    .reverse()
    .map((item, index) => ({
      id: `${item.tool}-${index}`,
      kind: "tool",
      status: item?.status === "success" ? "success" : "failed",
      title: `${item.tool || "Tool"} 执行${item?.status === "success" ? "成功" : "失败"}`,
      summary: formatTooluseLine(item),
      time: formatDate(item.created_at),
      jsonPayload: item,
      downloadName: `${String(item.tool || "tool").replace(/\s+/g, "-").toLowerCase()}-result.json`,
    }));
}

function buildRuntimeTraceEntries(analysisResult, existingEntries = []) {
  const trace = Array.isArray(analysisResult?.runtime_trace)
    ? analysisResult.runtime_trace
    : [];
  const existingIds = new Set(existingEntries.map((entry) => String(entry.id || "")));
  const entries = [];
  const toolNameByCallId = new Map();
  trace.forEach((item) => {
    if (!item || typeof item !== "object" || String(item.type || "") !== "tool_call") {
      return;
    }
    const callId = String(item.tool_call_id || item.id || "");
    const toolName = String(item.tool_name || "").trim();
    if (callId && toolName) {
      toolNameByCallId.set(callId, toolName);
    }
  });
  for (const [traceIndex, item] of trace.entries()) {
    if (!item || typeof item !== "object") {
      continue;
    }
    const type = String(item.type || "");
    const rawId = String(item.id || item.tool_call_id || entries.length);
    const itemId = `runtime-${type}-${traceIndex}-${rawId}`;
    if (existingIds.has(itemId)) {
      continue;
    }
    if (type === "tool_call") {
      entries.push({
        id: itemId,
        kind: "analysis",
        status: "analysis",
        title: `${item.tool_name || "Tool"} 调用已生成`,
        summary: formatRuntimeTraceArguments(item.arguments),
        detailText: formatRuntimeTraceArguments(item.arguments),
        time: formatDate(item.created_at),
        jsonPayload: item,
        downloadName: `${String(item.tool_name || "tool").replace(/\s+/g, "-").toLowerCase()}-runtime-call.json`,
      });
    } else if (type === "tool_result") {
      const callId = String(item.tool_call_id || item.id || "");
      const runtimeToolName = toolNameByCallId.get(callId);
      entries.push({
        id: itemId,
        kind: "tool",
        status: item.status === "fail" || item.status === "failed" ? "failed" : "success",
        toolName: runtimeToolName || "",
        title: "工具结果已返回",
        summary: String(item.content || "工具结果已写入上下文。").slice(0, 220),
        time: formatDate(item.created_at),
        detailText: String(item.content || ""),
        jsonPayload: item,
        downloadName: "runtime-tool-result.json",
      });
    } else if (type === "message") {
      const role = String(item.role || "");
      entries.push({
        id: itemId,
        kind: "analysis",
        status: "analysis",
        title: role === "assistant" ? "模型分析中" : "平台反馈",
        summary: String(item.content || "").slice(0, 220),
        time: formatDate(item.created_at),
        jsonPayload: item,
        downloadName: "runtime-message.json",
      });
    }
  }
  return entries.reverse();
}

function mergeTimelineEntries(primaryEntries, secondaryEntries) {
  const seen = new Set();
  const merged = [];
  for (const entry of [...primaryEntries, ...secondaryEntries]) {
    const key = String(entry.id || "");
    if (key && seen.has(key)) {
      continue;
    }
    if (key) {
      seen.add(key);
    }
    merged.push(entry);
  }
  return merged;
}

function formatRuntimeTraceArguments(argumentsValue) {
  if (!argumentsValue) {
    return "工具调用已写入运行时上下文。";
  }
  if (typeof argumentsValue === "string") {
    return argumentsValue.slice(0, 220);
  }
  try {
    return JSON.stringify(argumentsValue, null, 2).slice(0, 220);
  } catch {
    return String(argumentsValue).slice(0, 220);
  }
}

function downloadTimelineEntryJson(entry) {
  const blob = new Blob([JSON.stringify(entry?.jsonPayload ?? {}, null, 2)], {
    type: "application/json",
  });
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = entry?.downloadName || "timeline-entry.json";
  link.click();
  URL.revokeObjectURL(url);
}

function formatTimelineEntryDetail(entry) {
  const payload = entry?.jsonPayload;
  if (!payload || typeof payload !== "object") {
    return "";
  }
  const eventPayload =
    payload.payload && typeof payload.payload === "object"
      ? payload.payload
      : payload;
  const toolPayload =
    eventPayload.payload && typeof eventPayload.payload === "object"
      ? eventPayload.payload
      : eventPayload;
  const rendered =
    toolPayload.rendered && typeof toolPayload.rendered === "object"
      ? toolPayload.rendered
      : {};
  const result =
    toolPayload.result && typeof toolPayload.result === "object"
      ? toolPayload.result
      : {};
  const parts = [
    rendered.transcript,
    rendered.summary,
    toolPayload.error,
    result.stdout,
    result.stderr,
    payload.content,
    entry?.summary,
  ]
    .map((value) => String(value || "").trim())
    .filter(Boolean);
  return parts.length ? parts[0].slice(0, 6000) : "";
}

function timelineKindLabel(entry) {
  const status = String(entry?.status || "");
  if (status === "analysis") {
    return "分析中";
  }
  if (status === "success") {
    return "成功";
  }
  if (status === "failed") {
    return "失败";
  }
  if (status === "completed") {
    return "完成";
  }
  return "事件";
}

function formatStructuredReportPreview(report) {
  if (!report || typeof report !== "object") {
    return "";
  }

  if (report.report_type === "vulnerability-mining") {
    const executive = report.executive_summary ?? {};
    const findings = Array.isArray(report.findings) ? report.findings : [];
    const nextSteps = Array.isArray(report.next_steps) ? report.next_steps : [];
    return [
      `结论：${executive.verdict || "未提供"}`,
      `总体风险：${executive.overall_risk || "unknown"}`,
      `置信度：${executive.confidence || "unknown"}`,
      executive.summary ? `摘要：${executive.summary}` : "",
      findings.length ? "" : "",
      findings.length ? "发现项：" : "",
      ...findings.slice(0, 5).map((item, index) =>
        `${index + 1}. [${item.severity || "unknown"}] ${item.title || item.id || "未命名问题"}`
      ),
      nextSteps.length ? "" : "",
      nextSteps.length ? "后续建议：" : "",
      ...nextSteps.slice(0, 3).map((item, index) => `${index + 1}. ${item}`),
    ]
      .filter(Boolean)
      .join("\n");
  }

  if (report.report_type === "sample-analysis") {
    const executive = report.executive_summary ?? {};
    const capabilities = Array.isArray(report.capabilities) ? report.capabilities : [];
    const iocs = Array.isArray(report.iocs) ? report.iocs : [];
    return [
      `结论：${executive.verdict || "未提供"}`,
      `恶意性：${executive.is_malicious ? "是" : "否/未证实"}`,
      `严重性：${executive.severity || "unknown"}`,
      `置信度：${executive.confidence || "unknown"}`,
      executive.family ? `家族：${executive.family}` : "",
      executive.summary ? `摘要：${executive.summary}` : "",
      capabilities.length ? "" : "",
      capabilities.length ? "能力画像：" : "",
      ...capabilities.slice(0, 5).map((item, index) =>
        `${index + 1}. ${item.name || "未命名能力"} (${item.confidence || "unknown"})`
      ),
      iocs.length ? "" : "",
      iocs.length ? `IOC 数量：${iocs.length}` : "",
    ]
      .filter(Boolean)
      .join("\n");
  }

  try {
    return JSON.stringify(report, null, 2);
  } catch {
    return "";
  }
}

function formatDate(value) {
  if (!value) {
    return "待识别";
  }
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) {
    return value;
  }
  return date.toLocaleString("zh-CN", { hour12: false });
}

function formatBytes(value) {
  if (!Number.isFinite(value)) {
    return "0 B";
  }
  if (value < 1024) {
    return `${value} B`;
  }
  if (value < 1024 * 1024) {
    return `${(value / 1024).toFixed(1)} KB`;
  }
  return `${(value / 1024 / 1024).toFixed(1)} MB`;
}

function buildResultAreaHtmlReport({
  title,
  moduleName,
  taskId,
  fileName,
  reportPath,
  fallbackBody,
}) {
  const reportNode =
    document.querySelector(".result-card .structured-report-panel") ||
    document.querySelector(".structured-report-panel");
  const bodyHtml = reportNode
    ? reportNode.cloneNode(true).outerHTML
    : `<section class="structured-report-panel"><div class="structured-section"><pre class="structured-pre">${escapeHtml(
        fallbackBody || "当前任务尚未生成可展示的最终报告内容。",
      )}</pre></div></section>`;
  const metaHtml = `
    <div class="export-meta">
      <div><span>任务类型：</span>${escapeHtml(moduleName)}</div>
      <div><span>任务 ID：</span>${escapeHtml(taskId)}</div>
      <div><span>目标文件：</span>${escapeHtml(fileName)}</div>
      <div><span>报告路径：</span>${escapeHtml(reportPath)}</div>
      <div><span>导出时间：</span>${escapeHtml(new Date().toLocaleString())}</div>
    </div>`;
  return `<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>${escapeHtml(title)}</title>
  <style>
    ${collectSameOriginStyles()}
    body{margin:0;background:#eef3f7;color:#17202f;font-family:Inter,"Segoe UI","Microsoft YaHei",sans-serif}
    .export-wrap{max-width:1180px;margin:0 auto;padding:28px 20px 48px}
    .export-title{margin:0 0 16px;font-size:28px;line-height:1.2;color:#111827}
    .export-meta{display:grid;grid-template-columns:repeat(auto-fit,minmax(220px,1fr));gap:10px 16px;margin:0 0 18px;padding:14px 16px;border:1px solid #dbe5ee;border-radius:8px;background:#fff;color:#475569;font-size:13px}
    .export-meta span{font-weight:700;color:#111827}
  </style>
</head>
<body>
  <main class="export-wrap">
    <h1 class="export-title">${escapeHtml(title)}</h1>
    ${metaHtml}
    ${bodyHtml}
  </main>
</body>
</html>`;
}

function collectSameOriginStyles() {
  const chunks = [];
  for (const sheet of Array.from(document.styleSheets || [])) {
    try {
      const rules = Array.from(sheet.cssRules || []);
      chunks.push(rules.map((rule) => rule.cssText).join("\n"));
    } catch {
      // Ignore stylesheets blocked by the browser's cross-origin rules.
    }
  }
  return chunks.join("\n");
}

function escapeHtml(value) {
  return String(value ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#39;");
}

function formatTooluseLine(item) {
  const purpose = item?.purpose ? String(item.purpose) : "";
  const execution = item?.execution && typeof item.execution === "object" ? item.execution : {};
  const argumentsPayload =
    execution.arguments && typeof execution.arguments === "object" ? execution.arguments : {};
  const command =
    argumentsPayload.command ||
    argumentsPayload.command_line ||
    "";
  const path =
    argumentsPayload.path ||
    argumentsPayload.file_path ||
    "";
  const detail = command || path;
  if (purpose && detail) {
    return `${purpose}\n${detail}`;
  }
  return purpose || detail || "无附加说明";
}

function PlaceholderView({ selected }) {
  const item = navigation.find((navItem) => navItem.id === selected);
  const modules = placeholderModules[selected] ?? [];

  return (
    <section className="placeholder-area" aria-label={`${item?.label}占位模块`}>
      {modules.map((name) => (
        <article className="placeholder-tile" key={name}>
          <div className="placeholder-icon">
            <Archive size={20} strokeWidth={2.1} />
          </div>
          <h2>{name}</h2>
          <p>功能位置已预留</p>
        </article>
      ))}
    </section>
  );
}

ReactDOM.createRoot(document.getElementById("root")).render(
  <React.StrictMode>
    <App />
  </React.StrictMode>,
);
