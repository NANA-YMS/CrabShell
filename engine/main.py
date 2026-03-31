"""
engine/main.py
─────────────────────────────────────────────────────────────────────────────
OpenClaw-Consensus FastAPI 微服务入口

职责：
  - 在本地 8081 端口提供 HTTP 服务
  - POST /api/audit 接收指令审计请求，委托 auditor.py 进行多数表决
  - 将表决结果以 JSON 格式返回给调用方

启动方式：
  uvicorn engine.main:app --host 0.0.0.0 --port 8081
  或直接运行本文件：python -m engine.main
─────────────────────────────────────────────────────────────────────────────
"""

import uvicorn                          # ASGI 服务器，用于启动 FastAPI 应用
from fastapi import FastAPI, HTTPException   # FastAPI 框架 + HTTP 异常处理
from pydantic import BaseModel, Field        # 请求体数据验证与类型声明

from engine.auditor import evaluate_command  # 核心多数表决审计函数

# ══════════════════════════════════════════════════════════════════════════════
# § 1  FastAPI 应用实例
# ══════════════════════════════════════════════════════════════════════════════

# 创建 FastAPI 应用，title 和 description 会显示在自动生成的 /docs 文档页面
app = FastAPI(
    title="OpenClaw-Consensus Audit Service",
    description="Zero-trust multi-model consensus auditor for AI agent commands.",
    version="1.0.0",
)

# ══════════════════════════════════════════════════════════════════════════════
# § 2  请求 / 响应数据模型（Pydantic）
# ══════════════════════════════════════════════════════════════════════════════

class AuditRequest(BaseModel):
    """
    POST /api/audit 的请求体结构。
    Pydantic 自动验证字段类型，缺少必填字段时返回 422 Unprocessable Entity。
    """
    command: str = Field(
        ...,                              # 必填字段（无默认值）
        min_length=1,                     # 禁止空指令，避免无意义的 API 调用
        description="待审计的系统指令，例如 'ls -la' 或 'rm -rf /'",
        examples=["ls -la"],
    )
    directory: str = Field(
        default=".",                      # 工作目录缺省为当前目录
        description="指令的工作目录路径，供审计上下文参考",
        examples=["/home/user/project"],
    )


class AuditResponse(BaseModel):
    """
    POST /api/audit 的响应体结构。
    status 字段是调用方关注的核心结论；其余字段提供审计过程的透明度。
    """
    status: str = Field(
        description="审计最终裁决：ALLOW（允许执行）或 DENY（拒绝执行）"
    )
    allow_count: int = Field(
        description="投票允许的模型数量"
    )
    deny_count: int = Field(
        description="投票拒绝的模型数量"
    )
    model_details: dict[str, str] = Field(
        description="各审计模型的独立判定明细，格式为 {模型名: 'ALLOW'/'DENY'}"
    )

# ══════════════════════════════════════════════════════════════════════════════
# § 3  审计接口
# ══════════════════════════════════════════════════════════════════════════════

@app.get(
    "/api/audit",
    summary="审计接口说明（仅 GET 提示）",
    include_in_schema=True,
)
async def audit_get_hint() -> dict:
    """
    浏览器直接打开 /api/audit 时会收到此说明。
    审计请求请使用 POST 方法，请求体：{"command": "指令", "directory": "工作目录"}。
    """
    return {
        "message": "本接口仅接受 POST 请求，请勿在浏览器地址栏直接访问。",
        "usage": "POST /api/audit，请求体 JSON：{\"command\": \"ls -la\", \"directory\": \".\"}",
        "health_check": "GET /health 可检查服务是否正常",
        "docs": "GET /docs 可查看完整 API 文档",
    }


@app.post(
    "/api/audit",
    response_model=AuditResponse,
    summary="提交指令审计请求",
    description=(
        "接收一条系统指令及其工作目录，并行调用多个 AI 审计模型进行多数表决，"
        "返回最终裁决结果（ALLOW / DENY）。"
    ),
)
async def audit_command(request: AuditRequest) -> AuditResponse:
    """
    核心审计端点。

    处理流程：
      1. Pydantic 自动验证请求体格式（字段缺失 / 类型错误 → 422）
      2. 将 command 和 directory 拼接为完整审计上下文，传入 evaluate_command
      3. evaluate_command 并行调用 engine/models.py 中配置的所有模型
      4. 按多数表决制得出 verdict，包装为 AuditResponse 返回

    错误处理：
      - evaluate_command 内部已捕获所有 API 异常，此处额外捕获未预期的系统级异常
      - 任何未捕获异常均以 500 Internal Server Error 返回，不暴露内部错误细节
    """
    try:
        # 将工作目录信息追加到指令上下文中，帮助审计模型判断路径合规性
        # 格式：[工作目录: <dir>]\n<原始指令>
        full_context: str = f"[工作目录: {request.directory}]\n{request.command}"

        # 委托核心审计引擎执行多数表决（异步，await 等待所有模型响应完成）
        result: dict = await evaluate_command(full_context)

        # 将 auditor.py 的返回字典映射为标准响应模型
        return AuditResponse(
            status=result["verdict"],              # "ALLOW" 或 "DENY"
            allow_count=result["allow_count"],     # 允许票数
            deny_count=result["deny_count"],       # 拒绝票数
            model_details=result["model_details"], # 各模型判定明细
        )

    except Exception as e:
        # 兜底：捕获 evaluate_command 之外的未预期异常
        # 不向客户端暴露内部错误堆栈，仅返回通用 500 错误
        raise HTTPException(
            status_code=500,
            detail=f"Audit service encountered an internal error: {type(e).__name__}",
        ) from e

# ══════════════════════════════════════════════════════════════════════════════
# § 4  健康检查接口（可选，便于运维监控）
# ══════════════════════════════════════════════════════════════════════════════

@app.get("/health", summary="服务健康检查")
async def health_check() -> dict:
    """
    返回服务存活状态，供负载均衡器或监控系统探活。
    不调用任何外部 API，始终快速响应。
    """
    return {"status": "ok", "service": "OpenClaw-Consensus Audit Service"}

# ══════════════════════════════════════════════════════════════════════════════
# § 5  直接运行入口
# ══════════════════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    # 使用 uvicorn 在 0.0.0.0:8081 启动服务
    # host="0.0.0.0" 允许局域网内其他设备访问；如需仅本机访问可改为 "127.0.0.1"
    uvicorn.run(
        "engine.main:app",   # 以字符串形式指定 app 路径，支持热重载
        host="0.0.0.0",      # 监听所有网络接口
        port=8081,           # 固定端口 8081
        reload=False,        # 生产模式关闭热重载；开发时可改为 True
    )
