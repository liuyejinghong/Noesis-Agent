from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Annotated, cast

import typer
from rich.console import Console
from rich.table import Table

from noesis_agent.agent.roles.types import AnalysisReport, ProposalStatus
from noesis_agent.auth.openai_oauth import OpenAIAuthManager, openai_login
from noesis_agent.bootstrap import AppBootstrap

app = typer.Typer(
    name="noesis",
    help="Noesis Agent - AI 驱动的加密货币策略研究与执行系统",
    no_args_is_help=True,
)
config_app = typer.Typer(help="配置管理")
login_app = typer.Typer(help="登录管理")
models_app = typer.Typer(help="模型管理")
app.add_typer(config_app, name="config")
app.add_typer(login_app, name="login")
app.add_typer(models_app, name="models")
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


@app.command(help="审批通过提案")
def approve(
    proposal_id: Annotated[int, typer.Argument(help="提案记录 ID")],
    root_dir: Annotated[Path | None, typer.Option("--root-dir")] = None,
    config: Annotated[Path | None, typer.Option("--config", "-c")] = None,
) -> None:
    bootstrap = _get_app(root_dir, config)
    try:
        bootstrap.proposal_manager.advance_proposal(proposal_id, ProposalStatus.APPROVED, reason="人工审批通过")
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


def main() -> None:
    app()
