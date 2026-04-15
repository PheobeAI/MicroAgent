# main.py
import sys
import time

from ui.console import console

__version__ = "0.1.0"


def main() -> None:
    # ── 1. Load config ────────────────────────────────────────────────────────
    from core.paths import find_config, resolve_relative
    from core.config import load_config
    config_path = find_config()
    config = load_config(config_path)
    config.model.path = str(resolve_relative(config_path.parent, config.model.path))

    # ── 2. Load tools ─────────────────────────────────────────────────────────
    from tools.registry import ToolRegistry
    tools = ToolRegistry(config.tools).load()

    # ── 3. Load model ─────────────────────────────────────────────────────────
    model_path = config.model.path
    console.print(f"[bold]正在加载模型:[/] {model_path} ...")

    # Set up file logging before model load so llama.cpp's C-level stderr
    # (fd 2) is redirected to the log file and stays off the terminal.
    from ui.logger import setup as setup_logging
    log_file = setup_logging(config.runtime.log_level)
    console.print(f"[dim]日志写入: {log_file}[/]")

    t0 = time.perf_counter()
    from core.model import LlamaCppBackend
    backend = LlamaCppBackend(config.model)
    try:
        backend.load()
    except Exception as e:
        console.print(f"[red]模型加载失败: {e}[/]")
        console.print("请检查 config.yaml 中的 model.path 是否指向有效的 .gguf 文件。")
        sys.exit(1)

    elapsed = time.perf_counter() - t0
    mem_gb = backend.get_memory_usage_gb()
    gpu_info = backend.get_gpu_info()
    console.print(
        f"[green]模型加载完成[/] ({elapsed:.1f}s) | "
        f"内存占用: {mem_gb:.1f}GB | "
        f"推理后端: {gpu_info} | "
        f"工具: {len(tools)} 个已启用"
    )

    # ── 4. Create memory manager ──────────────────────────────────────────────
    from memory.manager import MemoryManager
    memory = None
    if config.memory.enabled:
        from core.paths import resolve_relative
        db_path = str(resolve_relative(config_path.parent, config.memory.db_path))
        config.memory.db_path = db_path

        def _token_counter(messages: list) -> int:
            """Estimate token count using llama-cpp tokenizer."""
            try:
                text = " ".join(str(m.get("content", "")) for m in messages)
                return len(backend._llm.tokenize(text.encode()))
            except Exception:
                return sum(len(str(m)) // 3 for m in messages)

        memory = MemoryManager(config.memory, _token_counter)
        memory_prefix = memory.on_session_start()
        # Inject memory tools
        from tools.memory_tools import MemoryRecallTool, MemoryStoreTool, MemoryForgetTool
        tools.append(MemoryRecallTool(memory))
        tools.append(MemoryStoreTool(memory))
        tools.append(MemoryForgetTool(memory))

    # ── 5. Create agent ───────────────────────────────────────────────────────
    if config.runtime.console_verbose:
        config.agent.verbose = True
    from core.agent import create_agent_runner
    agent = create_agent_runner(config.agent, backend, tools)

    # ── 6. Start CLI ──────────────────────────────────────────────────────────
    from cli.app import run_cli
    try:
        run_cli(agent, config, tools, memory=memory)
    finally:
        if memory:
            memory.on_session_end(model=backend)


if __name__ == "__main__":
    main()
