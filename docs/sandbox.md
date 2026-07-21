# CodeX 沙箱执行说明

沙箱是“能力管理”中的一种能力类型。添加能力类型 `沙箱`，再添加一个该类型的平台，URL 填写沙箱 server 地址，例如：

```text
http://127.0.0.1:8765
```

如果 server 启动时配置了 token，则在平台的 `API Key` 或 `Token` 中填写同一个值。

## 远程沙箱启动

将 [sandbox_server.py](../scripts/sandbox_server.py) 放到远程沙箱环境中运行：

```powershell
python scripts/sandbox_server.py --host 0.0.0.0 --port 8765 --root C:\codex_sandbox --token your-token
```

server 提供以下接口：

- `GET /health`：健康检查
- `POST /tools/check`：检查工具是否安装
- `POST /tools/install`：安装或登记工具
- `POST /tools/execute`：执行工具并返回完整结果

## 平台侧行为

- 只有 `样本分析` 和 `漏洞挖掘` 任务会自动使用沙箱。
- `ToolSystem.execute()` 在实际执行工具前，会查找能力类型为 `沙箱` 且状态为 `online` 的平台。
- 如果沙箱 `health` 可达，系统会先检查并安装工具系统中的工具，然后把工具请求和相关文件转发到沙箱 server。
- 如果没有配置在线沙箱，工具会继续使用本地执行逻辑。
