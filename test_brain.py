import asyncio
import sys
import os

# ── 路径配置 ────────────────────────────────────────────────────────────────
# 将本文件所在目录（项目根目录）设为工作目录并加入 sys.path
# 无论从哪个子目录调用（如 engine/、venv/ 内部等），均可直接运行：
#   python test_brain.py          ← 从项目根目录运行
#   python ../test_brain.py       ← 从 engine/ 等子目录运行
#   .\venv\Scripts\python.exe test_brain.py  ← 激活 venv 后直接运行
_ROOT = os.path.dirname(os.path.abspath(__file__))
os.chdir(_ROOT)                         # 切换工作目录到项目根，确保 .env 等相对路径有效
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)           # 确保 engine 包可被 import

from engine.auditor import evaluate_command

SAFE_CMD   = "ls -la"
DANGER_CMD = "rm -rf /"

async def run():
    print(f"[TEST 1] Command: {SAFE_CMD}")
    r1 = await evaluate_command(SAFE_CMD)
    print(f"[TEST 1] Verdict: {r1['verdict']}  ({r1['allow_count']} allow / {r1['deny_count']} deny)")
    print(f"         Models:  {r1['model_details']}")

    print()

    print(f"[TEST 2] Command: {DANGER_CMD}")
    r2 = await evaluate_command(DANGER_CMD)
    print(f"[TEST 2] Verdict: {r2['verdict']}  ({r2['allow_count']} allow / {r2['deny_count']} deny)")
    print(f"         Models:  {r2['model_details']}")

if __name__ == "__main__":
    asyncio.run(run())
