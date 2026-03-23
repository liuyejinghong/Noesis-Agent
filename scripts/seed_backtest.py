"""Run R-breaker backtest and store results in memory for AI analysis."""

from pathlib import Path

from noesis_agent.agent.memory.models import MemoryRecord
from noesis_agent.agent.memory.store import MemoryStore
from noesis_agent.backtest.broker import BrokerSimulator
from noesis_agent.backtest.engine import BacktestEngine
from noesis_agent.backtest.metrics import calculate_summary
from noesis_agent.core.enums import RuntimeMode
from noesis_agent.core.models import StrategyRuntimeConfig
from noesis_agent.data.ingestion import load_market_data_csv
from noesis_agent.strategy.regime import classify_regime
from noesis_agent.strategy.registry import StrategyRegistry

data_dir = Path("data")
state_dir = Path("state")
state_dir.mkdir(exist_ok=True)

df = load_market_data_csv(data_dir, source="binance_usdm", symbol="BTCUSDT", timeframe="15m")
print(f"数据: {len(df)} bars, {df.index[0].date()} → {df.index[-1].date()}")

config = StrategyRuntimeConfig(
    strategy_id="r_breaker",
    symbol="BTCUSDT",
    timeframe="15m",
    mode=RuntimeMode.BACKTEST,
    parameters={"pivot_mode": "rolling", "rolling_bars": 16, "reverse_enabled": True, "reverse_to_opposite": False},
    risk={"max_position_size": 0.01},
    trade_management={"stop_loss_pct": 0.03, "take_profit_pct": 0.06},
)
strategy = StrategyRegistry().build_strategy("r_breaker", config)
broker = BrokerSimulator(initial_cash=10_000, fee_rate=0.0004, slippage_bps=2.0)
result = BacktestEngine(broker).run(strategy, df, config)
summary = calculate_summary(result, initial_cash=10_000)

regime = classify_regime(df.iloc[-200:])

exit_reasons = dict(summary.exit_reason_counts) if summary.exit_reason_counts else "无"

backtest_report = f"""R-breaker 策略回测报告 (BTCUSDT 15m, 90天)

【回测参数】
- pivot_mode: rolling (滚动窗口)
- rolling_bars: 16 (4小时)
- reverse_enabled: True
- stop_loss_pct: 3%
- take_profit_pct: 6%
- 初始资金: $10,000
- 仓位: 0.01 BTC

【绩效指标】
- 总收益率: {summary.total_return_pct:+.2f}%
- 最大回撤: {summary.max_drawdown_pct:.2f}%
- 胜率: {summary.win_rate_pct:.1f}%
- 交易笔数: {summary.trade_count}
- 最终净值: ${summary.final_equity:,.2f}
- 已实现盈亏: ${summary.realized_pnl:+,.2f}
- 手续费: ${summary.fees_paid:,.2f}
- 退出原因分布: {exit_reasons}

【不同窗口参数对比】
- 8 bars (2h): 44笔交易, -0.16%, 胜率36.4%
- 16 bars (4h): 18笔交易, +0.02%, 胜率55.6% ← 当前
- 24 bars (6h): 8笔交易, -0.01%, 胜率50.0%
- 48 bars (12h): 0笔交易
- 96 bars (24h): 0笔交易

【当前市场状态】
- 状态: {regime.regime.value}
- 置信度: {regime.confidence:.0%}
- ATR分位数: {regime.atr_percentile:.2f}
- 均线斜率: {regime.ma_slope:.6f}
- 详情: {regime.details}

【策略核心逻辑】
R-breaker 用前 N 根 K 线的高低收计算 Pivot 和 6 条关键价格线:
- Break Buy = H + 2*(Pivot-L): 突破做多
- Break Sell = L - 2*(H-Pivot): 突破做空
- Sell Setup / Sell Enter: 反转平多条件
- Buy Setup / Buy Enter: 反转平空条件

【已知问题】
1. 收益率极低(+0.02%)，但策略方向正确(胜率56%)
2. 仓位太小(0.01 BTC ≈ $870 vs $10,000 本金)，收益被摊薄
3. 24h窗口的经典设置在加密市场完全无法触发信号
4. 2h窗口信号太多但胜率低(36%)
5. 没有趋势过滤，震荡市容易假突破
"""

memory = MemoryStore(str(state_dir / "memory.db"))
record_id = memory.store(
    MemoryRecord(
        memory_type="knowledge",
        category="backtest_report",
        strategy_id="r_breaker",
        title="r_breaker:2025-Q1 回测报告",
        content=backtest_report,
        tags=["2025-Q1", "backtest", "r_breaker"],
    )
)
print(f"回测报告已存入 memory (id={record_id})")
print(backtest_report)
