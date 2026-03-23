from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Annotated, cast

import typer
from rich.console import Console
from rich.markdown import Markdown
from rich.table import Table

from noesis_agent.agent.roles.types import AnalysisReport, ProposalStatus
from noesis_agent.auth.openai_oauth import OpenAIAuthManager, openai_login
from noesis_agent.bootstrap import AppBootstrap
from noesis_agent.core.prompt_registry import PromptRegistry
from noesis_agent.logging.agent_tracer import log_approval_action

app = typer.Typer(
    name="noesis",
    help="Noesis Agent - AI 驱动的加密货币策略研究与执行系统",
    no_args_is_help=True,
)
batch_app = typer.Typer(help="批量操作")
config_app = typer.Typer(help="配置管理")
data_app = typer.Typer(help="数据管理")
login_app = typer.Typer(help="登录管理")
models_app = typer.Typer(help="模型管理")
prompts_app = typer.Typer(help="Prompt 版本管理")
app.add_typer(batch_app, name="batch")
app.add_typer(config_app, name="config")
app.add_typer(data_app, name="data")
app.add_typer(login_app, name="login")
app.add_typer(models_app, name="models")
app.add_typer(prompts_app, name="prompts")
console = Console()


def _get_app(root_dir: Path | None = None, config: Path | None = None) -> AppBootstrap:
    return AppBootstrap(root_dir=root_dir, config_path=config)


def _load_analysis_report(bootstrap: AppBootstrap, report_id: int) -> AnalysisReport:
    record = bootstrap.memory.get_record(report_id)
    if record is None or record.category != "analysis_report":
        raise ValueError(f"Analysis report not found: {report_id}")
    return AnalysisReport.model_validate(record.metadata)


def _get_model_registry(root_dir: Path | None = None):
    from noesis_agent.core.model_registry import ModelRegistry

    root = root_dir or Path.cwd()
    return ModelRegistry(root / "config" / "models.toml")


def _get_prompt_registry(root_dir: Path | None = None) -> PromptRegistry:
    root = root_dir or Path.cwd()
    return PromptRegistry(root / "config" / "prompts")


@app.command(help="运行分析 Agent，生成策略分析报告")
def analyze(
    strategy_id: Annotated[str, typer.Argument(help="策略 ID")],
    period: Annotated[str, typer.Option("--period", "-p", help="分析周期，如 2025-01")],
    root_dir: Annotated[Path | None, typer.Option("--root-dir", help="项目根目录")] = None,
    config: Annotated[Path | None, typer.Option("--config", "-c", help="配置文件路径")] = None,
) -> None:
    bootstrap = _get_app(root_dir, config)
    console.print(f"[bold]正在分析策略 [cyan]{strategy_id}[/cyan] 周期 [cyan]{period}[/cyan]...[/bold]")
    try:
        report = asyncio.run(bootstrap.orchestrator.run_analysis(strategy_id, period))
    except Exception as exc:
        console.print(f"[red]✗ 分析失败: {exc}[/red]")
        raise typer.Exit(code=1) from exc

    console.print("\n[green]✓ 分析完成[/green]")
    console.print(f"  市场环境: {report.market_regime}")
    console.print(f"  优势: {', '.join(report.strengths) if report.strengths else '无'}")
    console.print(f"  弱点: {', '.join(report.weaknesses) if report.weaknesses else '无'}")
    console.print(f"  建议: {', '.join(report.recommendations) if report.recommendations else '无'}")


@app.command(help="运行提案 Agent，生成改进提案")
def propose(
    strategy_id: Annotated[str, typer.Argument(help="策略 ID")],
    report_id: Annotated[int, typer.Option("--report-id", "-r", help="分析报告 ID")],
    root_dir: Annotated[Path | None, typer.Option("--root-dir")] = None,
    config: Annotated[Path | None, typer.Option("--config", "-c")] = None,
) -> None:
    bootstrap = _get_app(root_dir, config)
    console.print(f"[bold]正在为策略 [cyan]{strategy_id}[/cyan] 生成改进提案...[/bold]")
    try:
        report = _load_analysis_report(bootstrap, report_id)
        if report.strategy_id != strategy_id:
            raise ValueError(f"Analysis report {report_id} belongs to strategy {report.strategy_id}")
        proposal = asyncio.run(bootstrap.orchestrator.run_proposal(report, report_id))
    except Exception as exc:
        console.print(f"[red]✗ 提案生成失败: {exc}[/red]")
        raise typer.Exit(code=1) from exc

    console.print("\n[green]✓ 提案生成[/green]")
    console.print(f"  提案 ID: {proposal.proposal_id}")
    console.print(f"  变更类型: {proposal.change_type}")
    console.print(f"  理由: {proposal.rationale}")


@app.command(help="运行验证 Agent，验证改进提案")
def validate(
    proposal_id: Annotated[int, typer.Argument(help="提案记录 ID")],
    root_dir: Annotated[Path | None, typer.Option("--root-dir")] = None,
    config: Annotated[Path | None, typer.Option("--config", "-c")] = None,
) -> None:
    _ = _get_app(root_dir, config)
    console.print(f"[bold]正在验证提案 #{proposal_id}...[/bold]")
    console.print("[yellow]提案验证需要配置 LLM API key[/yellow]")


@app.command(help="运行完整闭环：分析 → 提案 → 门控 → 验证")
def cycle(
    strategy_id: Annotated[str, typer.Argument(help="策略 ID")],
    period: Annotated[str, typer.Option("--period", "-p", help="分析周期")],
    root_dir: Annotated[Path | None, typer.Option("--root-dir")] = None,
    config: Annotated[Path | None, typer.Option("--config", "-c")] = None,
) -> None:
    bootstrap = _get_app(root_dir, config)
    console.print(f"[bold]正在运行完整闭环 [cyan]{strategy_id}[/cyan] 周期 [cyan]{period}[/cyan]...[/bold]")
    try:
        result = cast(dict[str, object], asyncio.run(bootstrap.orchestrator.run_full_cycle(strategy_id, period)))
    except Exception as exc:
        console.print(f"[red]✗ 闭环失败: {exc}[/red]")
        raise typer.Exit(code=1) from exc

    console.print("\n[green]✓ 闭环完成[/green]")
    final_status = result.get("final_status", "unknown")
    rendered_status = final_status.value if isinstance(final_status, ProposalStatus) else str(final_status)
    console.print(f"  最终状态: {rendered_status}")


@batch_app.command("run")
def batch_run(
    period: Annotated[str, typer.Option("--period", "-p", help="分析周期，如 2026-03")],
    root_dir: Annotated[Path | None, typer.Option("--root-dir")] = None,
    config: Annotated[Path | None, typer.Option("--config", "-c")] = None,
) -> None:
    bootstrap = _get_app(root_dir, config)
    strategies = bootstrap.strategy_catalog.list_active()
    console.print(f"[bold]发现 {len(strategies)} 个活跃策略[/bold]")
    for strategy in strategies:
        console.print(f"  · {strategy.strategy_id} ({strategy.symbol} {strategy.timeframe})")

    result = asyncio.run(bootstrap.batch_coordinator.run(period))

    table = Table(title=f"月度批量结果 — {period}")
    table.add_column("策略", style="cyan")
    table.add_column("状态")
    for strategy_id, entry in result.strategy_results.items():
        raw_status = cast(object, entry.get("final_status", "unknown"))
        status = raw_status.value if isinstance(raw_status, ProposalStatus) else str(raw_status)
        table.add_row(strategy_id, f"[green]{status}[/green]")
    for strategy_id, error in result.errors.items():
        table.add_row(strategy_id, f"[red]{error}[/red]")
    console.print(table)
    console.print(f"\n成功: {result.succeeded}/{result.total}")


@app.command(help="审批通过提案")
def approve(
    proposal_id: Annotated[int, typer.Argument(help="提案记录 ID")],
    root_dir: Annotated[Path | None, typer.Option("--root-dir")] = None,
    config: Annotated[Path | None, typer.Option("--config", "-c")] = None,
) -> None:
    bootstrap = _get_app(root_dir, config)
    try:
        bootstrap.proposal_manager.advance_proposal(proposal_id, ProposalStatus.APPROVED, reason="人工审批通过")
        log_approval_action("approved", proposal_id, reason="人工审批通过")
    except Exception as exc:
        console.print(f"[red]✗ 审批失败: {exc}[/red]")
        raise typer.Exit(code=1) from exc

    console.print(f"[green]✓ 提案 #{proposal_id} 已通过[/green]")


@app.command(help="拒绝提案")
def reject(
    proposal_id: Annotated[int, typer.Argument(help="提案记录 ID")],
    reason: Annotated[str, typer.Option("--reason", "-r", help="拒绝原因")],
    root_dir: Annotated[Path | None, typer.Option("--root-dir")] = None,
    config: Annotated[Path | None, typer.Option("--config", "-c")] = None,
) -> None:
    bootstrap = _get_app(root_dir, config)
    try:
        bootstrap.proposal_manager.reject_proposal(proposal_id, reason=reason)
        log_approval_action("rejected", proposal_id, reason=reason)
    except Exception as exc:
        console.print(f"[red]✗ 拒绝失败: {exc}[/red]")
        raise typer.Exit(code=1) from exc

    console.print(f"[green]✓ 提案 #{proposal_id} 已拒绝[/green]")


@app.command(help="显示系统状态总览")
def status(
    root_dir: Annotated[Path | None, typer.Option("--root-dir")] = None,
    config: Annotated[Path | None, typer.Option("--config", "-c")] = None,
) -> None:
    bootstrap = _get_app(root_dir, config)
    pending = bootstrap.proposal_manager.get_pending_approvals()
    table = Table(title="Noesis Agent 系统状态")
    table.add_column("项目", style="cyan")
    table.add_column("值", style="green")
    table.add_row("运行模式", bootstrap.settings.mode.value)
    table.add_row("交易品种", bootstrap.settings.symbol)
    table.add_row("时间周期", bootstrap.settings.timeframe)
    table.add_row("已注册技能", str(len(bootstrap.skill_registry.list_skills())))
    table.add_row("Agent 角色", str(len(bootstrap.router.list_roles())))
    table.add_row("待审批提案", str(len(pending)))
    console.print(table)


@app.command(help="列出所有提案")
def proposals(
    status_filter: Annotated[str | None, typer.Option("--status", "-s", help="按状态过滤")] = None,
    root_dir: Annotated[Path | None, typer.Option("--root-dir")] = None,
    config: Annotated[Path | None, typer.Option("--config", "-c")] = None,
) -> None:
    bootstrap = _get_app(root_dir, config)
    records = bootstrap.memory.get_proposals(status=status_filter)
    if not records:
        console.print("[yellow]暂无提案[/yellow]")
        return

    table = Table(title="提案列表")
    table.add_column("ID", style="cyan")
    table.add_column("标题")
    table.add_column("状态", style="green")
    table.add_column("创建时间")
    for record in records:
        table.add_row(str(record.id), record.title, record.status, record.created_at or "")
    console.print(table)


@prompts_app.command("list", help="列出所有 Prompt 角色与激活版本")
def prompts_list(
    root_dir: Annotated[Path | None, typer.Option("--root-dir", help="项目根目录")] = None,
) -> None:
    registry = _get_prompt_registry(root_dir)
    roles = registry.list_roles()
    if not roles:
        console.print("[yellow]暂无 Prompt 配置[/yellow]")
        return

    table = Table(title="Prompt Roles")
    table.add_column("Role", style="cyan")
    table.add_column("Active Version", style="green")
    table.add_column("Versions")

    for role in roles:
        versions = registry.list_versions(role)
        active_version = registry.load_prompt(role).version
        table.add_row(role, active_version, ", ".join(item["version"] for item in versions))

    console.print(table)


@prompts_app.command("show", help="显示角色 Prompt 内容")
def prompts_show(
    role: Annotated[str, typer.Argument(help="角色名")],
    version: Annotated[str | None, typer.Option("--version", help="指定版本")] = None,
    root_dir: Annotated[Path | None, typer.Option("--root-dir", help="项目根目录")] = None,
) -> None:
    registry = _get_prompt_registry(root_dir)
    try:
        prompt = registry.load_prompt(role, version=version)
    except FileNotFoundError as exc:
        console.print(f"[red]✗ 读取 Prompt 失败: {exc}[/red]")
        raise typer.Exit(code=1) from exc

    console.print(f"[bold]{prompt.role} {prompt.version}[/bold]\n")
    console.print(Markdown(prompt.content))


@models_app.command("list", help="列出所有可用模型")
def models_list(
    tier: Annotated[str | None, typer.Option("--tier", "-t", help="按等级过滤: high/mid/low")] = None,
    root_dir: Annotated[Path | None, typer.Option("--root-dir")] = None,
) -> None:
    registry = _get_model_registry(root_dir)
    models = registry.list_models(tier=tier)

    table = Table(title="可用模型")
    table.add_column("模型", style="cyan")
    table.add_column("提供商")
    table.add_column("等级", style="green")
    table.add_column("能力")
    table.add_column("成本")

    for model in models:
        provider = registry.providers.get(model.provider_id)
        provider_name = provider.name if provider else "?"
        table.add_row(model.model_id, provider_name, model.tier, ", ".join(model.capabilities), model.cost)

    console.print(table)


@models_app.command("test", help="测试模型连通性（最小 token 消耗）")
def models_test(
    model_id: Annotated[str | None, typer.Argument(help="测试指定模型，不指定则测试全部")] = None,
    root_dir: Annotated[Path | None, typer.Option("--root-dir")] = None,
) -> None:
    registry = _get_model_registry(root_dir)
    results = [registry.test_model(model_id)] if model_id else registry.test_all()

    table = Table(title="模型连通性测试")
    table.add_column("模型", style="cyan")
    table.add_column("提供商")
    table.add_column("状态")
    table.add_column("延迟")
    table.add_column("错误")

    for result in results:
        status = "[green]OK[/green]" if result.success else "[red]FAIL[/red]"
        latency = f"{result.latency_ms:.0f}ms" if result.latency_ms > 0 else "-"
        table.add_row(result.model_id, result.provider, status, latency, result.error)

    console.print(table)


@login_app.command("openai", help="通过 OpenAI OAuth 登录")
def login_openai() -> None:
    try:
        tokens = openai_login()
    except Exception as exc:
        console.print(f"[red]✗ OpenAI 登录失败: {exc}[/red]")
        raise typer.Exit(code=1) from exc

    account_id = tokens.get("accountId") or "未知账户"
    console.print("[green]✓ OpenAI 登录成功[/green]")
    console.print(f"  账户: {account_id}")


@login_app.command("status", help="显示 OpenAI 登录状态")
def login_status() -> None:
    manager = OpenAIAuthManager()
    tokens = manager.load_tokens()
    if tokens is None:
        console.print("[yellow]未登录[/yellow]")
        return

    account_id = tokens.get("accountId") or "未知账户"
    console.print("[green]已登录[/green]")
    console.print(f"  账户: {account_id}")


@login_app.command("logout", help="清除 OpenAI OAuth 登录")
def login_logout() -> None:
    manager = OpenAIAuthManager()
    if manager.clear_tokens():
        console.print("[green]✓ 已退出 OpenAI 登录[/green]")
        return
    console.print("[yellow]未登录，无需退出[/yellow]")


@config_app.command("show", help="显示当前配置")
def config_show(
    root_dir: Annotated[Path | None, typer.Option("--root-dir")] = None,
    config: Annotated[Path | None, typer.Option("--config", "-c")] = None,
) -> None:
    bootstrap = _get_app(root_dir, config)
    table = Table(title="当前配置")
    table.add_column("配置项", style="cyan")
    table.add_column("值", style="green")
    table.add_row("模式", bootstrap.settings.mode.value)
    table.add_row("品种", bootstrap.settings.symbol)
    table.add_row("周期", bootstrap.settings.timeframe)
    table.add_row("最大仓位", str(bootstrap.settings.risk.max_position_size))
    table.add_row("最大杠杆", str(bootstrap.settings.risk.max_leverage))
    table.add_row("日亏损上限", f"{bootstrap.settings.risk.max_daily_loss_pct:.0%}")
    table.add_row("只读模式", str(bootstrap.settings.risk.read_only))
    console.print(table)


@data_app.command("collect", help="采集 Binance 快照数据")
def data_collect(
    symbols: Annotated[str, typer.Option("--symbols", "-s", help="逗号分隔的交易对列表")] = "BTCUSDT,ETHUSDT",
    root_dir: Annotated[Path | None, typer.Option("--root-dir", help="项目根目录")] = None,
) -> None:
    from noesis_agent.data.collector import BinanceDataCollector
    from noesis_agent.data.storage import DataStore

    store = DataStore((root_dir or Path.cwd()) / "data")
    collector = BinanceDataCollector(store, symbols=[item.strip() for item in symbols.split(",") if item.strip()])
    results = collector.collect_all()

    table = Table(title="数据采集结果")
    table.add_column("任务", style="cyan")
    table.add_column("记录数", style="green", justify="right")
    for name, count in sorted(results.items()):
        table.add_row(name, str(count))
    console.print(table)


_MAX_HISTORY_MESSAGES = 50


def _chat_welcome(session_name: str, model: str, history_count: int) -> None:
    console.print()
    console.print("[bold cyan]╭─────────────────────────────────────╮[/bold cyan]")
    console.print("[bold cyan]│         Noesis Agent v0.2.0         │[/bold cyan]")
    console.print("[bold cyan]╰─────────────────────────────────────╯[/bold cyan]")
    console.print()
    console.print(f"  [dim]模型:[/dim]  {model}")
    console.print(f"  [dim]会话:[/dim]  {session_name}")
    if history_count > 0:
        console.print(f"  [dim]历史:[/dim]  已恢复 {history_count} 条消息")
    console.print()
    console.print("  [dim]/help 查看命令  |  /clear 清空历史  |  Esc+Enter 换行  |  exit 退出[/dim]")
    console.print()


def _handle_slash_command(cmd: str, bootstrap: AppBootstrap, session_store: object, session_name: str) -> bool:
    parts = cmd.strip().split(maxsplit=1)
    command = parts[0].lower()

    if command == "/help":
        console.print()
        console.print("[bold]可用命令:[/bold]")
        console.print("  [cyan]/status[/cyan]   — 查看系统状态（不经过 LLM）")
        console.print("  [cyan]/config[/cyan]   — 查看风控配置")
        console.print("  [cyan]/clear[/cyan]    — 清空当前会话历史")
        console.print("  [cyan]/session[/cyan]  — 显示会话信息")
        console.print("  [cyan]/sessions[/cyan] — 列出所有会话")
        console.print("  [cyan]/help[/cyan]     — 显示此帮助")
        console.print("  [cyan]exit[/cyan]      — 退出对话")
        console.print()
        return True

    if command == "/status":
        pending = bootstrap.proposal_manager.get_pending_approvals()
        skills = bootstrap.skill_registry.list_skills()
        console.print()
        console.print(f"  运行模式: [green]{bootstrap.settings.mode.value}[/green]")
        console.print(f"  交易品种: [green]{bootstrap.settings.symbol}[/green]")
        console.print(f"  时间周期: [green]{bootstrap.settings.timeframe}[/green]")
        console.print(f"  Agent 角色: [green]{', '.join(bootstrap.router.list_roles())}[/green]")
        console.print(f"  已注册技能: [green]{len(skills)}[/green]")
        console.print(f"  待审批提案: [green]{len(pending)}[/green]")
        console.print()
        return True

    if command == "/config":
        risk = bootstrap.settings.risk
        console.print()
        console.print(f"  最大仓位: [green]{risk.max_position_size}[/green]")
        console.print(f"  最大杠杆: [green]{risk.max_leverage}[/green]")
        console.print(f"  日亏损上限: [green]{risk.max_daily_loss_pct:.0%}[/green]")
        console.print(f"  只读模式: [green]{risk.read_only}[/green]")
        console.print()
        return True

    if command == "/clear":
        return True

    if command == "/session":
        console.print(f"\n  当前会话: [cyan]{session_name}[/cyan]\n")
        return True

    if command == "/sessions":
        from noesis_agent.agent.chat_session import ChatSessionStore

        if isinstance(session_store, ChatSessionStore):
            sessions = session_store.list_sessions()
            if not sessions:
                console.print("\n  [yellow]暂无会话[/yellow]\n")
            else:
                console.print()
                for s in sessions:
                    marker = " [cyan]◀[/cyan]" if s["session_id"] == session_name else ""
                    console.print(f"  {s['session_id']} ({s['message_count']} 条消息){marker}")
                console.print()
        return True

    console.print(f"  [yellow]未知命令: {command}（输入 /help 查看可用命令）[/yellow]")
    return True


async def _run_chat_stream(
    agent: object,
    user_input: str,
    deps: object,
    history: list[object],
) -> tuple[str, list[object], bytes]:
    from pydantic_ai.messages import ModelResponse, ToolCallPart

    streamed_result = agent.run_stream(user_input, deps=deps, message_history=history)  # type: ignore[union-attr]
    async with await streamed_result as result:
        console.print()
        console.print("[bold cyan]Noesis:[/bold cyan] ", end="")

        collected_text = ""
        async for chunk in result.stream_text(delta=True):
            console.file.write(chunk)
            console.file.flush()
            collected_text += chunk

        console.print()

        for msg in result.new_messages():
            if isinstance(msg, ModelResponse):
                for part in msg.parts:
                    if isinstance(part, ToolCallPart):
                        console.print(f"  [dim]🔧 {part.tool_name}[/dim]")

        all_messages = result.all_messages()
        all_messages_json = result.all_messages_json()
        console.print()
        return collected_text, all_messages, all_messages_json


@app.command(help="与 Noesis Agent 对话（REPL 或单轮）")
def chat(
    message: Annotated[str | None, typer.Argument(help="单轮消息，不传则进入 REPL 对话")] = None,
    session: Annotated[str, typer.Option("--session", "-s", help="会话名")] = "default",
    new_session: Annotated[bool, typer.Option("--new", help="忽略历史，开启新会话")] = False,
    root_dir: Annotated[Path | None, typer.Option("--root-dir", help="项目根目录")] = None,
    config: Annotated[Path | None, typer.Option("--config", "-c", help="配置文件路径")] = None,
) -> None:
    from pydantic import TypeAdapter
    from pydantic_ai.messages import ModelMessage

    from noesis_agent.agent.chat_session import ChatSessionStore
    from noesis_agent.agent.roles.chat import ChatDeps, create_chat_agent

    bootstrap = _get_app(root_dir, config)
    agent = create_chat_agent(bootstrap.router, bootstrap)
    deps = ChatDeps(bootstrap=bootstrap)
    session_store = ChatSessionStore(bootstrap.app_context.state_dir / "chat_sessions")
    message_adapter = TypeAdapter(list[ModelMessage])
    model_name = bootstrap.router.get_model("chat")

    history: list[ModelMessage] = []
    if not new_session:
        saved = session_store.load(session)
        if saved is not None:
            history = message_adapter.validate_json(saved)

    if message is not None:
        with console.status("[bold cyan]思考中...[/bold cyan]"):
            result = asyncio.run(agent.run(message, deps=deps, message_history=history))
        console.print(Markdown(result.output))
        session_store.save(session, result.all_messages_json())
        return

    _chat_welcome(session, model_name, len(history))

    from prompt_toolkit import PromptSession as PTSession
    from prompt_toolkit.history import InMemoryHistory
    from prompt_toolkit.key_binding import KeyBindings
    from prompt_toolkit.key_binding.key_processor import KeyPressEvent

    bindings = KeyBindings()

    @bindings.add("escape", "enter")
    def _newline(event: KeyPressEvent) -> None:
        event.current_buffer.insert_text("\n")

    pt_session = PTSession(history=InMemoryHistory(), key_bindings=bindings, multiline=False)

    while True:
        try:
            user_input = pt_session.prompt("你: ").strip()
        except (EOFError, KeyboardInterrupt):
            console.print("\n[dim]再见 👋[/dim]")
            break

        if not user_input:
            continue
        if user_input.lower() in ("exit", "quit", "q"):
            console.print("[dim]再见 👋[/dim]")
            break

        if user_input.startswith("/"):
            if user_input.strip().lower() == "/clear":
                history = []
                session_store.save(session, b"[]")
                console.print("  [green]✓ 会话历史已清空[/green]\n")
                continue
            _handle_slash_command(user_input, bootstrap, session_store, session)
            continue

        try:
            with console.status("[bold cyan]思考中...[/bold cyan]"):
                result = asyncio.run(agent.run(user_input, deps=deps, message_history=history))
            history = result.all_messages()
            if len(history) > _MAX_HISTORY_MESSAGES:
                history = history[-_MAX_HISTORY_MESSAGES:]
            session_store.save(session, result.all_messages_json())
            console.print()
            console.print(Markdown(result.output))
            console.print()
        except KeyboardInterrupt:
            console.print("\n[yellow]已中断[/yellow]\n")
        except Exception as exc:
            _handle_chat_error(exc)


def _handle_chat_error(exc: Exception) -> None:
    error_type = type(exc).__name__
    msg = str(exc)

    if "401" in msg or "unauthorized" in msg.lower() or "auth" in msg.lower():
        console.print("[red]认证失败或已过期。[/red]")
        console.print("[yellow]运行 `noesis login openai` 重新登录[/yellow]\n")
    elif "timeout" in msg.lower() or "timed out" in msg.lower():
        console.print("[red]请求超时，请稍后重试[/red]\n")
    elif "connection" in msg.lower() or "network" in msg.lower():
        console.print("[red]网络连接失败，请检查网络[/red]\n")
    elif "rate" in msg.lower() and "limit" in msg.lower():
        console.print("[red]请求频率超限，请稍后重试[/red]\n")
    else:
        console.print(f"[red]错误 ({error_type}): {msg}[/red]\n")


def main() -> None:
    app()
