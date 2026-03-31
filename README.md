### English | [简体中文](./README_zh.md)

# CrabShell v1.0 🦀

**A Multi-Agent Consensus Auditing Plugin for OpenClaw**

Give your OpenClaw Agent a tougher shell! CrabShell recruits a team of LLMs to double-check the intent of every `.exec` call, defending your environment against prompt injections and malicious scripts with collective AI brainpower.

CrabShell implements a mandatory multi-model security vote before any Shell command is executed by the OpenClaw Agent.

---

## 🏗 Architecture Overview

| Layer | Mechanism | Purpose |
|:---:|---|---|
| **Layer 1** | `safe_exec` Tool Registration | Replaces the built-in `exec`. Every call must pass a majority vote from the Python audit service. |
| **Layer 2** | `before_prompt_build` Hook | Injects security policies into the System Prompt before every conversation, ensuring the Agent prefers `safe_exec`. |
| **Layer 3** | Gateway Double-Block | Hides `exec` from the tool list and enforces a hard-deny at the Gateway level to prevent bypass. |

---

## 📁 Directory Structure

```text
CrabShell/
├── README.md
├── requirements.txt
├── openclaw.plugin.json     # Plugin manifest (ID: crabshell)
├── package.json
├── index.ts                 # Plugin entry point (register(api) format)
├── test_brain.py            # Standalone local testing script
└── engine/
    ├── .env.example         # API Key template (Rename to .env)
    ├── cost.log             # Audit logs and model output history
    ├── auditor.py
    ├── main.py              # FastAPI Service (Port 8081)
    ├── models.py
    └── prompts.py
```

---

## 📋 Prerequisites

- **Python 3.10+**
- **OpenClaw** installed and available in your PATH (`openclaw` command).
- API Keys from **SiliconFlow** or **OpenRouter**.

---

## 🚀 Installation & Setup

### 1. Install Python Dependencies
First, enable Windows Long Path support (if on Windows):
```powershell
New-ItemProperty -Path "HKLM:\System\CurrentControlSet\Control\FileSystem" `
-Name "LongPathsEnabled" -Value 1 -PropertyType DWORD -Force
```

Create a virtual environment and install the required packages:
```powershell
# Run from the project root
python -m venv venv
.\venv\Scripts\activate
pip install -r requirements.txt
```

### 2. Configure API Keys
Copy `engine\.env.example` to `engine\.env` and add your keys:
```env
SILICONFLOW_API_KEY=sk-...
OPENROUTER_API_KEY=sk-or-v1-...
```

### 3. Install the Plugin to OpenClaw
```powershell
openclaw plugins install .\CrabShell
```
Verify the installation:
```powershell
openclaw plugins list
```
You should see `crabshell` in the list.

### 4. Enable the Plugin
```powershell
openclaw plugins enable crabshell
```

### 5. Configure Gateway (Critical Step)
Edit your OpenClaw configuration file (usually `~/.openclaw/openclaw.json`). Add the following to disable the default `exec` tool and ensure the plugin is active:

```json
{
  "tools": {
    "deny": ["exec"],
    "exec": {
      "security": "deny"
    }
  },
  "plugins": {
    "allow": ["crabshell"],
    "entries": {
      "crabshell": { "enabled": true }
    }
  }
}
```
* `"deny": ["exec"]`: Hides the built-in tool from the Agent.
* `"security": "deny"`: Hard-interception at the Gateway layer.

### 6. Restart OpenClaw Gateway
```powershell
openclaw gateway restart
```

---

## 🛡 Running the Audit Service

Inside the CrabShell directory (with `venv` activated):
```powershell
python -m engine.main
```
**Verify service status:**
```powershell
Invoke-RestMethod -Uri http://127.0.0.1:8081/health
```
A return value of `{"status":"ok"}` means the audit engine is ready. **The audit service must be running for the plugin to work.**

---

## ✅ Verification

Check the OpenClaw logs after restarting:
```powershell
openclaw logs --follow
```
You should see:
```text
[CrabShell v1.0] Plugin registered successfully.
  ✓ safe_exec tool active
  ✓ before_prompt_build hook active
  ✓ Audit endpoint: http://127.0.0.1:8081/api/audit
```
When you send a command to the Agent, it will now trigger `safe_exec`, which requires consensus from the audit service before proceeding.

---

## 🧪 Local Quick Test (No OpenClaw Required)
You can test the auditing logic independently using `test_brain.py`:
```powershell
# Run from the project root
python test_brain.py

# Or use the venv path directly
.\venv\Scripts\python.exe test_brain.py
```

---

## 🔄 Workflow



1.  **Agent Request:** Agent attempts to execute a command.
2.  **Strategy Injection:** `before_prompt_build` injects safety guidelines.
3.  **Redirection:** Built-in `exec` is blocked; Agent is forced to use `safe_exec`.
4.  **Audit Trigger:** `safe_exec` sends the command to the Python Audit Service (`:8081`).
5.  **Multi-LLM Voting:** The engine calls multiple models (SiliconFlow/OpenRouter) in parallel.
6.  **Consensus:**
    * **ALLOW:** If the majority approves, the command executes via `execAsync`.
    * **DENY:** If the majority flags it, execution is blocked and an error is returned to the Agent.
7.  **Logging:** Every decision and cost metric is recorded in `cost.log`.

---

## ❓ FAQ & Troubleshooting

| Symptom | Cause | Solution |
|:---|:---|:---|
| Logs don't show `CrabShell registered` | Plugin not loaded | Check `openclaw plugins list` to ensure it is "loaded". |
| Agent still uses built-in `exec` | Gateway config mismatch | Ensure `tools.deny: ["exec"]` is in `openclaw.json` and restart Gateway. |
| `safe_exec` returns timeout | Audit service offline | Run `python -m engine.main` and check `/health`. |
| Installation error | Path issues | Use the absolute path or `.\CrabShell` during install. |
| Error 1008 | Zombie processes | Run `taskkill /f /im node.exe` and restart OpenClaw. |

## ⚠️ Notes
- **Audit Logs:** Check `engine\cost.log` for a detailed audit trail.
- **Model Selection:** To change the auditing models, edit `AUDIT_MODELS` in `engine\models.py`.
- **Remote Deployment:** If the audit service is hosted on a different machine, update the `AUDIT_ENDPOINT` in `index.ts` and reinstall the plugin.

---

## 💬 A Note from the Author
My programming background is still a work in progress! 🛠️
If you spot any bugs, find room for optimization, or have better ideas on how to improve this project, please feel free to reach out or open an issue. My ultimate goal is for this plugin to run as smoothly on your machine as it does on mine!