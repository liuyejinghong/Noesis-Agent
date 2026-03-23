"""Compare R-breaker performance across real Binance fee scenarios."""

from pathlib import Path

from noesis_agent.backtest.broker import BrokerSimulator
from noesis_agent.backtest.engine import BacktestEngine
from noesis_agent.backtest.metrics import calculate_summary
from noesis_agent.core.enums import RuntimeMode
from noesis_agent.core.models import StrategyRuntimeConfig
from noesis_agent.data.ingestion import load_market_data_csv
from noesis_agent.strategy.registry import StrategyRegistry

df = load_market_data_csv(Path("data"), source="binance_usdm", symbol="BTCUSDT", timeframe="15m")

print("=== R-breaker 费率对比 (官方数据, 0.04 BTC) ===\n")

scenarios = [
    ("BTCUSDT Taker 原始", 0.000500, 2.0),
    ("BTCUSDT Taker + BNB", 0.000450, 2.0),
    ("BTCUSDT Maker + BNB", 0.000180, 1.0),
    ("BTCUSDC Taker + BNB", 0.000360, 2.0),
    ("BTCUSDC Taker 原始", 0.000400, 2.0),
    ("BTCUSDC Maker", 0.000000, 0.0),
]

for label, fee, slip in scenarios:
    config = StrategyRuntimeConfig(
        strategy_id="r_breaker",
        symbol="BTCUSDT",
        timeframe="15m",
        mode=RuntimeMode.BACKTEST,
        parameters={"pivot_mode": "rolling", "rolling_bars": 16, "reverse_enabled": True},
        risk={"max_position_size": 0.04},
        trade_management={"stop_loss_pct": 0.03, "take_profit_pct": 0.06},
    )
    strategy = StrategyRegistry().build_strategy("r_breaker", config)
    result = BacktestEngine(BrokerSimulator(initial_cash=10_000, fee_rate=fee, slippage_bps=slip)).run(
        strategy, df, config
    )
    s = calculate_summary(result, initial_cash=10_000)
    fee_pct = (s.fees_paid / s.realized_pnl * 100) if s.realized_pnl > 0 else 0
    print(
        f"{label:24s} | 净利={s.total_return_pct:+.3f}% | 盈亏=${s.realized_pnl:+.2f} | 手续费=${s.fees_paid:.2f} | 费占比={fee_pct:.0f}%"
    )
