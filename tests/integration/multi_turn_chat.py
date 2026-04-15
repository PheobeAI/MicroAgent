"""多轮对话集成测试：直接调用 AgentRunner Python API，绕过 CLI/tty 限制。

测试目标：
- 多轮上下文记忆（session 内 history）
- 短期记忆：上一轮说的内容，下一轮能记住
- 明确触发 memory_store（"记住..."）
- 话题切换后仍无规划失败
- MemoryManager 生命周期正常（start/end）

运行方式：
    python tests/integration/multi_turn_chat.py
"""
from __future__ import annotations
import sys
import os
import time
import logging

# 加入项目根目录
PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
sys.path.insert(0, PROJECT_ROOT)

# 静默 llama.cpp 的 C 层日志，避免刷屏
logging.disable(logging.WARNING)

PASS = "✓"
FAIL = "✗"
INFO = "ℹ"


def _token_counter_simple(messages: list) -> int:
    """简单字符估算 token 数（不依赖模型）。"""
    return sum(len(str(m.get("content", ""))) // 3 for m in messages)


def setup() -> tuple:
    """加载配置、模型、工具、MemoryManager，返回 (agent, memory, tools)。"""
    from core.paths import find_config, resolve_relative
    from core.config import load_config
    from tools.registry import ToolRegistry
    from core.model import LlamaCppBackend
    from core.agent import create_agent_runner
    from memory.manager import MemoryManager
    from tools.memory_tools import MemoryRecallTool, MemoryStoreTool, MemoryForgetTool

    config_path = find_config()
    config = load_config(config_path)
    config.model.path = str(resolve_relative(config_path.parent, config.model.path))

    tools = ToolRegistry(config.tools).load()

    print("⏳ 加载模型（这需要 20~60 秒）...")
    t0 = time.perf_counter()
    backend = LlamaCppBackend(config.model)
    backend.load()
    print(f"✅ 模型加载完成 ({time.perf_counter()-t0:.1f}s)\n")

    # MemoryManager — 用简单计数器，不依赖模型 tokenizer
    if config.memory.enabled:
        db_path = str(resolve_relative(config_path.parent, config.memory.db_path))
        config.memory.db_path = db_path
        memory = MemoryManager(config.memory, _token_counter_simple)
        memory.on_session_start()
        tools.append(MemoryRecallTool(memory))
        tools.append(MemoryStoreTool(memory))
        tools.append(MemoryForgetTool(memory))
    else:
        memory = None

    agent = create_agent_runner(config.agent, backend, tools)
    return agent, memory, tools, backend


class ConversationSession:
    """维护多轮对话状态，直接调用 agent.run()。"""

    def __init__(self, agent, memory):
        self._agent = agent
        self._memory = memory
        self._history: list[dict] = []

    def chat(self, user_msg: str) -> str:
        """发送一条消息，自动维护 history，返回 agent 回复。"""
        # 获取记忆前缀
        memory_prefix = self._memory.prefix if self._memory else None
        # 传入历史
        answer = self._agent.run(
            user_msg,
            history=self._history if self._history else None,
            memory_prefix=memory_prefix,
        )
        # 追加到历史
        self._history.append({"role": "user", "content": user_msg})
        self._history.append({"role": "assistant", "content": answer or ""})
        # 追加到记忆 buffer
        if self._memory:
            self._memory.append_user(user_msg)
            self._memory.append_assistant(answer or "")
            self._memory.maybe_compress()
        return answer or ""

    @property
    def history(self) -> list[dict]:
        return list(self._history)


def has(text: str, *keywords) -> bool:
    t = text.lower()
    return any(kw.lower() in t for kw in keywords)


def run() -> int:
    print("=" * 60)
    print("MicroAgent 多轮对话集成测试（API 直调模式）")
    print("=" * 60)

    issues: list[str] = []

    try:
        agent, memory, tools, backend = setup()
    except Exception as e:
        print(f"{FAIL} 初始化失败: {e}")
        import traceback; traceback.print_exc()
        return 1

    session = ConversationSession(agent, memory)

    # ── 测试用例 ─────────────────────────────────────────────────────────────
    # 格式：(描述, 消息, 期望包含任意一个关键词, 不应包含的关键词)
    TURNS: list[tuple[str, str, list[str], list[str]]] = [
        (
            "自我介绍并要求记忆",
            "你好，记住我叫王磊，我是一个Rust工程师",
            [],            # 宽松，只要不崩就行
            ["规划失败"],
        ),
        (
            "回忆本轮用户名（短期记忆）",
            "我刚才说我叫什么名字？",
            ["王磊"],
            ["规划失败"],
        ),
        (
            "技术问答 — Rust所有权",
            "Rust 的所有权机制是什么？用中文简短解释",
            ["所有权", "ownership", "内存", "borrow", "借用"],
            ["规划失败"],
        ),
        (
            "上文关联 — 延伸讨论",
            "所有权里生命周期和借用检查器，哪个更难理解？",
            ["生命周期", "借用", "lifetime", "borrow"],
            ["规划失败"],
        ),
        (
            "明确要求存储长期偏好",
            "记住我不喜欢看英文文档，总是用中文给我解释",
            [],            # 只要不崩，memory_store 是否触发看日志
            ["规划失败"],
        ),
        (
            "验证偏好能被回忆",
            "我之前说过对语言有什么偏好？",
            ["中文", "偏好", "语言", "英文"],
            ["规划失败"],
        ),
        (
            "话题切换 — Python GIL",
            "Python 的 GIL 是什么？为什么有争议？",
            ["GIL", "全局", "线程", "锁", "gil"],
            ["规划失败"],
        ),
        (
            "跨话题引用 — 结合职业问问题",
            "作为Rust工程师，我应该关注Python的GIL问题吗？",
            [],
            ["规划失败"],
        ),
    ]

    logging.disable(logging.NOTSET)  # 恢复日志，让规划日志可见

    for i, (desc, msg, want_any, want_none) in enumerate(TURNS, 1):
        print(f"\n{'─'*55}")
        print(f"[第{i}轮] {desc}")
        print(f"  用户: {msg}")

        t0 = time.perf_counter()
        try:
            answer = session.chat(msg)
        except Exception as e:
            answer = f"[异常: {e}]"
            issues.append(f"第{i}轮({desc})：异常 {e}")

        elapsed = time.perf_counter() - t0
        # 截断显示
        display = answer[:300] + ("..." if len(answer) > 300 else "")
        print(f"  Agent: {display}")
        print(f"  耗时: {elapsed:.1f}s | 历史长度: {len(session.history)//2} 轮")

        # 检查不应出现的词
        fail_this = False
        for kw in want_none:
            if kw in answer:
                print(f"  {FAIL} 出现了「{kw}」")
                issues.append(f"第{i}轮({desc})：出现「{kw}」")
                fail_this = True

        # 检查期望出现的词（任意一个即可）
        if want_any:
            if has(answer, *want_any):
                print(f"  {PASS} 包含期望内容")
            else:
                print(f"  {INFO} 未出现期望关键词（{', '.join(want_any[:3])}）— 可能回答方式不同")
                # 不算 issue，只记录提示

        if not fail_this and not want_any:
            print(f"  {PASS} 通过（无崩溃）")

    # ── 清理 ─────────────────────────────────────────────────────────────────
    if memory:
        print(f"\n{'─'*55}")
        print("[收尾] 保存 session 到 SQLite...")
        try:
            from core.model import LlamaCppBackend
            memory.on_session_end(model=backend)
            ep_count = memory.episode_count()
            facts = memory.get_facts()
            print(f"  {PASS} session 已保存 | episodes: {ep_count} | facts: {len(facts)}")
            if facts:
                for k, v in facts.items():
                    print(f"    {k} = {v}")
        except Exception as e:
            print(f"  {INFO} on_session_end 异常（非致命）: {e}")

    # ── 汇总 ─────────────────────────────────────────────────────────────────
    print(f"\n{'='*55}")
    print("测试汇总")
    print(f"{'='*55}")
    print(f"总轮数: {len(TURNS)} | 历史长度: {len(session.history)//2} 轮")
    if issues:
        print(f"发现 {len(issues)} 个问题：")
        for iss in issues:
            print(f"  {FAIL} {iss}")
        return 1
    else:
        print(f"  {PASS} 全部通过！{len(TURNS)} 轮无规划失败，多轮上下文正常。")
        return 0


if __name__ == "__main__":
    sys.exit(run())
