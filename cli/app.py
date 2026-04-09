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
}


def run_cli(agent: AgentRunner, config: AppConfig, tools: List[Any]) -> None:
    _print_header(tools)
    while True:
        try:
            user_input = Prompt.ask("[bold cyan]>[/]", console=console).strip()
        except (KeyboardInterrupt, EOFError):
            console.print("\n[yellow]再见！[/]")
            break

        if not user_input:
            continue

        if user_input.startswith("/"):
            _handle_command(user_input, tools, config)
        else:
            _run_task(agent, user_input, verbose=config.agent.verbose)


def _print_header(tools: List[Any]) -> None:
    console.print(Rule("[bold green]MicroAgent[/]"))
    console.print(f"工具已加载: [green]{len(tools)}[/] 个 | 输入 [bold]/help[/] 查看命令，Ctrl+C 退出")
    console.print(Rule())


def _handle_command(cmd: str, tools: List[Any], config: AppConfig) -> None:
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
    else:
        console.print(f"[red]未知命令: {cmd}[/]。输入 /help 查看可用命令。")


def _run_task(agent: AgentRunner, prompt: str, verbose: bool) -> None:
    try:
        if verbose:
            result = agent.run(prompt)
        else:
            with console.status("[bold]思考中...[/]"):
                result = agent.run(prompt)
        console.print(Rule())
        console.print(f"[bold green]结果:[/] {result}")
        console.print(Rule())
    except Exception as e:
        console.print(f"[red]错误: {e}[/]")
