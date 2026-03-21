# pyright: reportAny=false

from __future__ import annotations

from collections import Counter
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from noesis_agent.backtest.engine import BacktestRunResult


class BacktestSummary(BaseModel):
    model_config = ConfigDict(frozen=True)

    run_id: str
    strategy_id: str
    total_return_pct: float
    max_drawdown_pct: float
    win_rate_pct: float
    trade_count: int
    final_equity: float
    realized_pnl: float
    fees_paid: float
    exit_reason_counts: dict[str, int] = Field(default_factory=dict)
    trade_management_exit_count: int = 0

    def to_dict(self) -> dict[str, Any]:
        return self.model_dump()


def calculate_summary(result: BacktestRunResult, initial_cash: float) -> BacktestSummary:
    equity_curve = [bar.equity for bar in result.bar_results]
    peak = initial_cash
    max_drawdown = 0.0
    for equity in equity_curve:
        peak = max(peak, equity)
        if peak > 0:
            drawdown = (peak - equity) / peak
            max_drawdown = max(max_drawdown, drawdown)

    realized_trades = [fill for fill in result.fills if float(fill.metadata.get("realized_pnl", 0.0)) != 0.0]
    wins = [fill for fill in realized_trades if float(fill.metadata.get("realized_pnl", 0.0)) > 0.0]
    trade_count = len(result.fills)
    win_rate = 0.0 if not realized_trades else (len(wins) / len(realized_trades)) * 100
    exit_reason_counts = Counter(
        str(fill.metadata["exit_reason"]) for fill in result.fills if "exit_reason" in fill.metadata
    )

    return BacktestSummary(
        run_id=result.run_id,
        strategy_id=result.strategy_id,
        total_return_pct=((result.final_equity - initial_cash) / initial_cash) * 100,
        max_drawdown_pct=max_drawdown * 100,
        win_rate_pct=win_rate,
        trade_count=trade_count,
        final_equity=result.final_equity,
        realized_pnl=result.realized_pnl,
        fees_paid=result.fees_paid,
        exit_reason_counts=dict(exit_reason_counts),
        trade_management_exit_count=sum(exit_reason_counts.values()),
    )
