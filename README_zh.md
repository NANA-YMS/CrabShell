### 中文 | [English](./README.md)

# CrabShell v1.0 🦀

**适用于 OpenClaw 的多智能体共识审计插件**

给OpenClaw套上一层“蟹壳”！CrabShell 会组建一支大语言模型团队，对每一次 `.exec` 调用意图进行交叉校验，借助集体 AI 算力抵御提示词注入与恶意脚本，守护你的运行环境。

CrabShell 在 OpenClaw 智能体执行任何 Shell 命令前，会强制执行多模型安全投票机制。

---

## 架构说明


| 层       | 机制                       | 作用                                                 |
| ------- | ------------------------ | -------------------------------------------------- |
| Layer 1 | `safe_exec` 工具注册         | 替代内置 `exec`，每次调用先经过 Python 审计服务多数表决                |
| Layer 2 | `before_prompt_build` 钩子 | 每轮对话前将安全策略注入 System Prompt，确保 Agent 使用 `safe_exec` |
| Layer 3 | Gateway 配置双重封禁           | 从工具列表隐藏 `exec` + 安全层拦截，彻底禁用内置 `exec`               |


---

# 安装与配置说明

## 一、目录结构

```
CrabShell/
├── README.md
├── requirements.txt
├── openclaw.plugin.json     # 插件清单（id: crabshell）
├── package.json
├── index.ts                 # 插件入口（register(api) 格式）
├── test_brain.py            # 本地测试脚本（可从任意子目录运行）
└── engine/
    ├── .env.example         # API 密钥（需去除.example）
    ├── cost.log             # 模型输出日志文件
    ├── auditor.py
    ├── main.py              # FastAPI 服务（端口 8081）
    ├── models.py
    └── prompts.py
```

---

## 二、前置依赖

- Python 3.10+
- OpenClaw 已安装（`openclaw` 命令可用）
- SiliconFlow 或 OpenRouter 的 API Key

---

## 三、安装步骤

### 1. CrabShell\ 安装 Python 依赖

开启 Windows 长路径支持：

```powershell
New-ItemProperty -Path "HKLM:\System\CurrentControlSet\Control\FileSystem" `
-Name "LongPathsEnabled" -Value 1 -PropertyType DWORD -Force
```

创建虚拟环境并安装依赖：

```powershell
python -m venv venv
.\venv\Scripts\activate
pip install -r requirements.txt
```

### 2. 配置 API 密钥

将 `engine\.env.example` 复制为 `engine\.env`，填写密钥：

```
SILICONFLOW_API_KEY=sk-...
OPENROUTER_API_KEY=sk-or-v1-...
```

### 3. 安装插件到 OpenClaw

```powershell
openclaw plugins install .\CrabShell
```

验证安装：

```powershell
openclaw plugins list
```

应看到 `crabshell` 显示在列表中。

### 4. 启用插件

```powershell
openclaw plugins enable crabshell
```

### 5. 配置 Gateway（关键步骤）

编辑 `~/.openclaw/openclaw.json`，修改并添加以下配置：

禁用原.exec工具：

```json
  "tools": {
    "deny": ["exec"],
    "exec": {
      "security": "deny"
    }
  },
```

确保 plugins 部分只保留这一段，删掉多余的 installs 记录：

```
  "plugins": {
    "allow": ["crabshell"],
    "entries": {
      "crabshell": { "enabled": true }
    }
  }
```

- `"deny": ["exec"]`：从 Agent 可见工具列表隐藏内置 `exec`
- `"security": "deny"`：Gateway 层硬拦截

### 6. 重启 Gateway

```powershell
openclaw gateway restart
```

---

## 四、启动审计服务

在 CrabShell 目录（已激活 venv）下：

```powershell
python -m engine.main
```

验证服务：

```powershell
Invoke-RestMethod -Uri http://127.0.0.1:8081/health
```

返回 `{"status":"ok"}` 即为正常。审计服务必须在 OpenClaw 使用插件前启动。

---

## 五、验证插件是否正常工作

Gateway 重启后，查看日志：

```powershell
openclaw logs --follow
```

应看到：

```
[CrabShell v2.0] Plugin registered successfully.
  ✓ safe_exec tool active
  ✓ before_prompt_build hook active
  ✓ Audit endpoint: http://127.0.0.1:8081/api/audit
```

在 OpenClaw 中发送一条包含命令的消息，Agent 会调用 `safe_exec` 而非 `exec`，并在执行前触发多模型审计。

---

## 六、本地快速测试（不依赖 OpenClaw）

`test_brain.py` 支持从任意目录调用，无需切换工作目录：

```powershell
# 从项目根目录运行
python test_brain.py

# 从子目录（如 engine/）运行
python ..\test_brain.py

# 激活 venv 后直接运行
.\venv\Scripts\python.exe test_brain.py
```

---

## 七、工作流程

```
Agent 要执行命令
     │
     ▼
before_prompt_build 注入安全策略（Layer 2）
     │
     ▼
Agent 调用 safe_exec（内置 exec 已被 Layer 3 双重封禁）
     │
     ▼
safe_exec.execute() 调用 http://127.0.0.1:8081/api/audit（Layer 1）
     │
     ├── 审计服务并行调用多个 LLM（SiliconFlow / OpenRouter）
     │         │
     │    多数表决
     │         │
     │    ┌────┴────┐
     │  DENY      ALLOW
     │    │          │
     │  熔断       execAsync 执行命令
     │  返回错误   返回输出
     ▼
cost.log 记录所有审计结果
```

---

## ❓ 常见问题


| 现象                         | 原因             | 解决                                                                            |
| -------------------------- | -------------- | ----------------------------------------------------------------------------- |
| 日志无 `CrabShell registered` | 插件未正确加载        | 检查 `openclaw plugins list`，确认 loaded                                          |
| Agent 仍使用内置 `exec`         | Gateway 配置未更新  | 确认 `tools.deny: ["exec"]` 已写入 `~/.openclaw/openclaw.json` 并重启 Gateway         |
| `safe_exec` 返回审计超时         | Python 审计服务未启动 | 运行 `python -m engine.main` 并验证 `/health`                                      |
| 插件安装失败                     | 路径错误           | 使用 `openclaw plugins install .\CrabShell` 正确安装                                |
| 出现 1008 错误                 | 后台有旧的配置残留在内存里  | 运行 `taskkill /f /im node.exe` 终止所有龙虾相关的 Node 进程并重新运行 `openclaw gateway start` |


## ⚠️ 注意事项

- 审计日志记录在 `engine\cost.log`。
- 如需调整审计模型，编辑 `engine\models.py` 中的 `AUDIT_MODELS`。
- 如果审计服务部署在其他机器，修改 `index.ts` 中的 `AUDIT_ENDPOINT`，然后重新安装插件。

---

## 💬 最后

我的编程能力仍在不断打磨提升中！🛠️
如果你发现了任何漏洞或是对项目改进有好的想法，欢迎随时联系我或提交 Issue。
希望这款插件在你的设备上，能像在我的设备上一样流畅运行！