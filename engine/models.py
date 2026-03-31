"""
engine/models.py
─────────────────────────────────────────────────────────────────────────────
【唯一模型配置入口】修改此文件即可更换审计模型，无需触碰 auditor.py 其他逻辑。

支持的 provider 值：
  "siliconflow" — 使用 engine/.env 中的 SILICONFLOW_API_KEY
                  经由 https://api.siliconflow.cn/v1 的 OpenAI 兼容接口调用
  "openrouter"  — 使用 engine/.env 中的 OPENROUTER_API_KEY
                  经由 litellm 内置的 openrouter/ 前缀路由自动调用

每个条目字段说明：
  model    : 目标模型在对应 provider 平台上的完整模型名称（区分大小写）
  provider : "siliconflow" 或 "openrouter"（auditor.py 据此自动切换调用方式）

修改示例——将第三个模型换成 OpenRouter 上的 Claude：
  {"model": "anthropic/claude-3.5-sonnet", "provider": "openrouter"},
─────────────────────────────────────────────────────────────────────────────
"""

from typing import TypedDict


class ModelEntry(TypedDict):
    """单个审计模型的配置结构，TypedDict 提供静态类型检查。"""
    model:    str   # 模型在 provider 平台上的完整名称
    provider: str   # 调用渠道："siliconflow" | "openrouter"


# ══════════════════════════════════════════════════════════════════════════════
# 审计模型列表（多数表决制，建议保持奇数个以避免平票）
# ══════════════════════════════════════════════════════════════════════════════
AUDIT_MODELS: list[ModelEntry] = [
    # --- SiliconFlow 托管模型 ---
    {"model": "deepseek-ai/DeepSeek-V3",        "provider": "siliconflow"},
    {"model": "Qwen/Qwen3-8B",                  "provider": "siliconflow"},
    {"model": "THUDM/GLM-Z1-32B-0414",          "provider": "siliconflow"},

    # --- OpenRouter 托管模型（示例，取消注释即可启用）---
    # {"model": "deepseek/deepseek-chat-v3-0324", "provider": "openrouter"},
    # {"model": "google/gemini-2.0-flash-001",    "provider": "openrouter"},
    # {"model": "anthropic/claude-3.5-haiku",     "provider": "openrouter"},
]
