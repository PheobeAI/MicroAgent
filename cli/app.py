# cli/app.py
from typing import List, Any

from rich.prompt import Prompt
from rich.rule import Rule

from core.agent import AgentRunner
from core.config import AppConfig
from ui.console import console

_COMMANDS = {
    "/help": "显示此帮助信息",
    "/tools": "列出已加载的工具及说明",
    "/clear": "清空屏幕",
    "/config": "显示当前配置摘要",
    "/memory": "显示记忆系统状态（token 使用、事实、历史条数）",
    "/memory set <key> <value>": "手动设置/更新一条事实",
    "/memory forget <key>": "删除指定事实",
    "/compress": "手动压缩当前对话历史",
}


def run_cli(agent: AgentRunner, config: AppConfig, tools: List[Any], memory=None) -> None:
    _print_header(tools)
    first_turn = True
    while True:
        try:
            user_input = Prompt.ask("[bold cyan]>[/]", console=console).strip()
        except (KeyboardInterrupt, EOFError):
            console.print("\n[yellow]再见！[/]")
            break

        if not user_input:
            continue

        if user_input.startswith("/"):
            _handle_command(user_input, tools, config, memory=memory)
        else:
            # 首轮：懒加载 RAG 第三层
            if memory and first_turn:
                memory.inject_rag_layer(user_input)
                first_turn = False

            # 从记忆中取历史消息和记忆前缀
            history = memory.get_messages_for_llm() if memory else None
            memory_prefix = memory.prefix if memory else None

            result = _run_task(
                agent,
                user_input,
                verbose=config.agent.verbose,
                show_thinking=config.agent.show_thinking,
                history=history,
                memory_prefix=memory_prefix,
            )

            # 追加本轮对话到记忆
            if memory and result:
                memory.append_user(user_input)
                memory.append_assistant(result)
                memory.maybe_compress()


def _print_header(tools: List[Any]) -> None:
    console.print(Rule("[bold green]MicroAgent[/]"))
    console.print(f"工具已加载: [green]{len(tools)}[/] 个 | 输入 [bold]/help[/] 查看命令，Ctrl+C 退出")
    console.print(Rule())


def _handle_command(cmd: str, tools: List[Any], config: AppConfig, memory=None) -> None:
    if cmd == "/help":
        for c, desc in _COMMANDS.items():
            console.print(f"  [bold]{c}[/]  {desc}")
    elif cmd == "/tools":
        for tool in tools:
            console.print(f"  [green]+[/] [bold]{tool.name}[/]: {tool.description}")
    elif cmd == "/clear":
        console.clear()
        _print_header(tools)
    elif cmd == "/config":
        import json
        data = config.model_dump()
        # Redact API key
        if data.get("tools", {}).get("web_search", {}).get("tavily_api_key"):
            data["tools"]["web_search"]["tavily_api_key"] = "***"
        console.print_json(json.dumps(data, indent=2, ensure_ascii=False))
    elif cmd == "/compress" and memory:
        memory.force_compress()
        console.print("[green]已手动压缩对话历史。[/]")
    elif cmd.startswith("/memory") and memory:
        parts = cmd.split(maxsplit=3)
        if len(parts) == 1:
            # /memory — 显示状态
            budget = memory.token_usage()
            facts = memory.get_facts()
            count = memory.episode_count()
            console.print(f"  Token: {budget.used_in_current_context}/{budget.context_window} | 压缩次数: {budget.compact_count}")
            console.print(f"  历史会话: {count} 条 | 已知事实: {len(facts)} 条")
            if facts:
                for k, v in facts.items():
                    console.print(f"    [green]{k}[/]: {v}")
            else:
                console.print("  [dim]（暂无已知事实）[/]")
        elif len(parts) >= 4 and parts[1] == "set":
            # /memory set <key> <value>
            key, value = parts[2], parts[3]
            memory.set_fact(key, value)
            console.print(f"[green]已设置事实：{key} = {value}[/]")
        elif len(parts) == 3 and parts[1] == "forget":
            # /memory forget <key>
            key = parts[2]
            memory.delete_fact(key)
            console.print(f"[yellow]已删除事实：{key}[/]")
        else:
            console.print("[red]用法：/memory | /memory set <key> <value> | /memory forget <key>[/]")
    else:
        console.print(f"[red]未知命令: {cmd}[/]。输入 /help 查看可用命令。")


def _run_task(
    agent: AgentRunner,
    prompt: str,
    verbose: bool,
    show_thinking: bool = True,
    history: list | None = None,
    memory_prefix: str | None = None,
) -> str | None:
    try:
        if verbose or show_thinking:
            result = agent.run(prompt, history=history, memory_prefix=memory_prefix)
        else:
            with console.status("[bold]思考中...[/]"):
                result = agent.run(prompt, history=history, memory_prefix=memory_prefix)
        console.print(Rule())
        if result is None or result.strip() == "":
            console.print("[yellow]未能生成回答。请重新提问，或尝试更具体的问题。[/]")
        else:
            console.print(f"[bold green]结果:[/] {result}")
        console.print(Rule())
        return result
    except Exception as e:
        console.print(f"[red]错误: {e}[/]")
        return None
