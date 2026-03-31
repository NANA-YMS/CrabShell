// @ts-nocheck
// 注：OpenClaw 使用 jiti 在运行时加载插件（不执行 tsc 类型检查）
// 此指令仅抑制 IDE 因缺少 @types/node 产生的误报，不影响实际运行

/**
 * index.ts — CrabShell OpenClaw Plugin
 * ─────────────────────────────────────────────────────────────────────────────
 * 正确的 OpenClaw 插件格式（v2.0）
 *
 * 架构重写原因（来自运行时日志 Context/00.txt + 官方文档）：
 *   旧方案：monkey-patch `globalThis.__openclawToolDispatch`
 *   问题：  该属性在 OpenClaw 中根本不存在，setter 陷阱永远不会触发
 *
 * 正确架构（三层联动）：
 *   Layer 1 — 注册 `safe_exec` 工具：审计通过后才执行命令
 *   Layer 2 — `before_prompt_build` 钩子：强制注入安全指令到 System Prompt
 *   Layer 3 — Gateway 配置：将内置 `exec` 的 security 设为 deny
 *
 * 插件入口格式（来自官方文档 tools/plugin.md）：
 *   正确：export default function register(api) { ... }
 *   错误：export default { activate, deactivate }   ← 旧方案，OpenClaw 不调用 activate()
 * ─────────────────────────────────────────────────────────────────────────────
 */

// jiti 运行时加载插件时处于 Node.js 进程内，child_process 和 util 原生可用
// 使用 require() 动态加载以兼容 jiti 的模块解析（避免 ESM 静态分析问题）
// eslint-disable-next-line @typescript-eslint/no-require-imports
const { exec: cpExec } = require("child_process") as typeof import("child_process");
// eslint-disable-next-line @typescript-eslint/no-require-imports
const { promisify } = require("util") as typeof import("util");

// 将 child_process.exec 包装为可 await 的 Promise 版本
const execAsync = promisify(cpExec);

// ══════════════════════════════════════════════════════════════════════════════
// § 1  常量配置
// ══════════════════════════════════════════════════════════════════════════════

/** Python FastAPI 审计服务地址（engine/main.py 监听的端口） */
const AUDIT_ENDPOINT = "http://127.0.0.1:8081/api/audit";

/** 单次审计请求的最大等待时间（毫秒）；略长于 Python 侧 30 秒硬超时 */
const AUDIT_TIMEOUT_MS = 35_000;

/** 命令执行的最大时长（毫秒）；防止命令无限挂起 */
const EXEC_TIMEOUT_MS = 60_000;

/** 熔断消息：向 OpenClaw Agent 及用户反馈 */
const DENY_MESSAGE =
  "【CrabShell 熔断】该操作已被多智能体共识过滤层熔断，禁止执行。";

/** 强制注入 System Prompt 的安全策略（Layer 2） */
const SECURITY_MANDATE = [
  "SECURITY POLICY — CrabShell v2.0 Active:",
  "• You MUST use the 'safe_exec' tool instead of the built-in 'exec' for ALL shell/system commands.",
  "• The built-in 'exec' tool has been disabled by gateway policy. Only 'safe_exec' will succeed.",
  "• Every command is audited by a multi-model consensus layer before execution.",
  "• Do NOT attempt to bypass this policy or suggest disabling CrabShell.",
].join("\n");

// ══════════════════════════════════════════════════════════════════════════════
// § 2  类型定义
// ══════════════════════════════════════════════════════════════════════════════

/** FastAPI /api/audit 响应结构（与 engine/main.py AuditResponse 对应） */
interface AuditResponse {
  status: "ALLOW" | "DENY";
  allow_count: number;
  deny_count: number;
  model_details: Record<string, string>;
}

/** safe_exec 工具的参数结构 */
interface SafeExecParams {
  command: string;      // 待执行的完整 Shell 命令
  directory?: string;   // 工作目录（可选，默认为 "."）
}

// ══════════════════════════════════════════════════════════════════════════════
// § 3  审计服务调用（带超时控制）
// ══════════════════════════════════════════════════════════════════════════════

/**
 * callAuditService
 * 向本地 FastAPI 审计服务发起阻塞 POST 请求，等待多模型多数表决结果。
 * AbortController 确保超时时主动取消，不无限挂起。
 */
async function callAuditService(
  command: string,
  directory: string
): Promise<AuditResponse> {
  const controller = new AbortController();
  const timeoutId = setTimeout(() => controller.abort(), AUDIT_TIMEOUT_MS);

  try {
    const response = await fetch(AUDIT_ENDPOINT, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ command, directory }),
      signal: controller.signal,
    });

    if (!response.ok) {
      // HTTP 层面的非 2xx 响应（422/500 等）视为审计服务异常
      throw new Error(`Audit service HTTP ${response.status}: ${response.statusText}`);
    }

    return (await response.json()) as AuditResponse;
  } finally {
    clearTimeout(timeoutId);   // 无论成功/失败都清除定时器，防止内存泄漏
  }
}

// ══════════════════════════════════════════════════════════════════════════════
// § 4  OpenClaw 插件入口（正确格式）
// ══════════════════════════════════════════════════════════════════════════════

/**
 * register(api)
 * OpenClaw 插件系统要求的入口函数。
 * 插件加载时，OpenClaw 自动调用此函数并传入 api 对象。
 * api 对象提供：registerTool / on / registerHook / registerHttpRoute 等方法。
 *
 * 旧方案的错误：export default { activate, deactivate }
 *   → OpenClaw 加载后不会调用 activate()，插件处于"已加载但未注册"状态
 *
 * 新方案（正确）：export default function register(api) { ... }
 *   → OpenClaw 加载时直接调用 register(api)，所有注册立即生效
 */
export default function register(api: any): void {

  // ── Layer 1：注册 safe_exec 工具 ────────────────────────────────────────────
  api.registerTool({
    name: "safe_exec",
    description: [
      "Securely execute a shell command after multi-model consensus audit.",
      "This is the ONLY valid command execution tool when CrabShell is active.",
      "The built-in exec tool has been disabled by security policy.",
    ].join(" "),
    parameters: {
      type: "object",
      properties: {
        command: {
          type: "string",
          description: "The shell command to execute (will be audited before running)",
        },
        directory: {
          type: "string",
          description: "Working directory for the command (default: '.')",
          default: ".",
        },
      },
      required: ["command"],
    },

    async execute(_id: string, params: SafeExecParams) {
      const { command, directory = "." } = params;

      // ── 步骤 1：向审计服务发送多模型表决请求 ─────────────────────────────
      let auditResult: AuditResponse;
      try {
        auditResult = await callAuditService(command, directory);
      } catch (err) {
        // 审计服务不可达（超时/网络故障）→ DENY-SAFE 策略：默认拒绝
        const reason = err instanceof Error ? err.message : String(err);
        return {
          content: [{
            type: "text",
            text: [
              DENY_MESSAGE,
              "原因：审计服务不可达，触发安全熔断（DENY-SAFE 策略）",
              `网络错误：${reason}`,
            ].join("\n"),
          }],
          isError: true,
        };
      }

      // ── 步骤 2：根据表决结果决定放行或熔断 ──────────────────────────────
      if (auditResult.status === "DENY") {
        // 多数模型判定危险 → 熔断，不执行命令
        return {
          content: [{
            type: "text",
            text: [
              DENY_MESSAGE,
              `裁决票数：${auditResult.deny_count} 拒绝 / ${auditResult.allow_count} 允许`,
              `模型明细：${JSON.stringify(auditResult.model_details, null, 2)}`,
            ].join("\n"),
          }],
          isError: true,
        };
      }

      // ── 步骤 3：审计通过（ALLOW）→ 实际执行命令 ─────────────────────────
      try {
        const { stdout, stderr } = await execAsync(command, {
          cwd: directory,
          timeout: EXEC_TIMEOUT_MS,  // 命令执行超时保护
        });

        // 将 stdout 和 stderr 合并后返回给 Agent
        const output = [stdout, stderr].filter(Boolean).join("\n").trim();
        return {
          content: [{
            type: "text",
            text: output || "(command completed with no output)",
          }],
        };
      } catch (err) {
        // 命令执行失败（非零退出码、超时等）
        const error = err instanceof Error ? err.message : String(err);
        return {
          content: [{ type: "text", text: `Command failed: ${error}` }],
          isError: true,
        };
      }
    },
  });

  // ── Layer 2：before_prompt_build 钩子注入安全指令 ─────────────────────────
  // 每次 Agent 构建 Prompt 前触发，将安全策略前置到 System Prompt
  // 确保 LLM 在任何 turn 都知晓必须使用 safe_exec 而非内置 exec
  api.on(
    "before_prompt_build",
    (_event: unknown, _ctx: unknown) => {
      return {
        // prependSystemContext 将内容插入 System Prompt 最前方（高优先级）
        prependSystemContext: SECURITY_MANDATE,
      };
    },
    { priority: 100 },  // 高优先级，确保在其他钩子之前执行
  );

  console.log(
    "[CrabShell v2.0] Plugin registered successfully.\n" +
    "  ✓ safe_exec tool active\n" +
    "  ✓ before_prompt_build hook active\n" +
    "  ✓ Audit endpoint: " + AUDIT_ENDPOINT
  );
}
