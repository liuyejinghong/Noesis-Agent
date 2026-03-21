# Noesis Agent — 阶段 1+2 实施计划

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**目标：** 从 QPorter Lite (v1) 迁移核心基础设施到 Noesis Agent (v2)，搭建 Agent 层所需的全部地基。

**架构：** 渐进式迁移 — 先搬底层类型和协议，再建配置系统，然后数据层适配器化，最后搭 Agent 基础设施（记忆、模型路由、技能注册、调度器）。每个模块独立可测，不依赖交易所 API 或 LLM API key。

**技术栈：** Python 3.11+ / Pydantic v2 / PydanticAI 1.x / LiteLLM / SQLite + FTS5 / TOML / APScheduler / httpx / Ruff / pytest

**v1 代码位置：** `/Users/ethan/Qporter Lite/src/qporter_lite/`
**v2 代码位置：** `/Users/ethan/noesis-agent/src/noesis_agent/`

---

## 依赖关系图

```
Task 1: core/enums + core/models (零依赖)
    ↓
Task 2: config 系统 (依赖 core)
    ↓
Task 3: data 协议 + 工具函数 (依赖 config)
    ↓
Task 4: data Binance 适配器 (依赖 data 协议)
    ↓
Task 5: execution 协议 + 风控纯函数 (依赖 core)  ← 可与 Task 3-4 并行
    ↓
Task 6: strategy 基类 + 工厂 (依赖 core)  ← 可与 Task 5 并行
    ↓
Task 7: backtest/optimize 引擎迁移 (依赖 strategy + data)
    ↓
Task 8: 调度器 (独立，仅依赖 config)  ← 可与 Task 7 并行
    ↓
Task 9: 记忆系统 (依赖 config)
    ↓
Task 10: 模型路由 (依赖 config)
    ↓
Task 11: 技能注册表 (依赖以上所有)
```

---

## Task 1: 核心类型迁移

> 从 v1 的 dataclass 迁移到 v2 的 Pydantic v2 模型。零外部依赖，TDD 起点。

**文件：**
- 创建: `src/noesis_agent/core/enums.py`
- 创建: `src/noesis_agent/core/models.py`
- 创建: `tests/unit/__init__.py`
- 创建: `tests/unit/test_core_enums.py`
- 创建: `tests/unit/test_core_models.py`

**v1 参考：**
- `/Users/ethan/Qporter Lite/src/qporter_lite/core/enums.py` (27 行，4 个枚举)
- `/Users/ethan/Qporter Lite/src/qporter_lite/core/models.py` (71 行，6 个 dataclass + 1 个工具函数)

### Step 1: 写 enums 测试

```python
# tests/unit/test_core_enums.py
from noesis_agent.core.enums import RuntimeMode, SignalSide, OrderType, StrategyStatus


class TestRuntimeMode:
    def test_values(self):
        assert RuntimeMode.BACKTEST == "backtest"
        assert RuntimeMode.TESTNET == "testnet"
        assert RuntimeMode.LIVE == "live"

    def test_is_str_enum(self):
        assert isinstance(RuntimeMode.BACKTEST, str)


class TestSignalSide:
    def test_values(self):
        assert SignalSide.LONG == "long"
        assert SignalSide.SHORT == "short"
        assert SignalSide.FLAT == "flat"


class TestOrderType:
    def test_values(self):
        assert OrderType.MARKET == "market"
        assert OrderType.LIMIT == "limit"
        assert OrderType.STOP == "stop"


class TestStrategyStatus:
    def test_values(self):
        assert StrategyStatus.ACTIVE == "active"
        assert StrategyStatus.DRAFT == "draft"
        assert StrategyStatus.ARCHIVED == "archived"
```

### Step 2: 运行测试确认失败

运行: `uv run pytest tests/unit/test_core_enums.py -v`
预期: FAIL — `ModuleNotFoundError: No module named 'noesis_agent.core.enums'`

### Step 3: 实现 enums

```python
# src/noesis_agent/core/enums.py
from __future__ import annotations

from enum import Enum


class RuntimeMode(str, Enum):
    BACKTEST = "backtest"
    TESTNET = "testnet"
    LIVE = "live"


class SignalSide(str, Enum):
    LONG = "long"
    SHORT = "short"
    FLAT = "flat"


class OrderType(str, Enum):
    MARKET = "market"
    LIMIT = "limit"
    STOP = "stop"


class StrategyStatus(str, Enum):
    ACTIVE = "active"
    DRAFT = "draft"
    ARCHIVED = "archived"
```

### Step 4: 运行测试确认通过

运行: `uv run pytest tests/unit/test_core_enums.py -v`
预期: 4 tests PASSED

### Step 5: 写 models 测试

```python
# tests/unit/test_core_models.py
from datetime import UTC, datetime

from noesis_agent.core.enums import OrderType, RuntimeMode, SignalSide
from noesis_agent.core.models import (
    AccountSnapshot,
    AppContext,
    OrderIntent,
    PositionSnapshot,
    SignalEvent,
    StrategyRuntimeConfig,
    generate_run_id,
)


class TestGenerateRunId:
    def test_format(self):
        run_id = generate_run_id("backtest")
        assert run_id.startswith("backtest_")
        # format: prefix_YYYYMMDDTHHMMSSz_hex8
        parts = run_id.split("_")
        assert len(parts) == 3
        assert len(parts[2]) == 8

    def test_default_prefix(self):
        run_id = generate_run_id()
        assert run_id.startswith("run_")

    def test_uniqueness(self):
        ids = {generate_run_id() for _ in range(100)}
        assert len(ids) == 100


class TestPositionSnapshot:
    def test_defaults(self):
        pos = PositionSnapshot(symbol="BTCUSDT", side=SignalSide.LONG, quantity=0.01)
        assert pos.entry_price is None
        assert pos.entry_bar_index is None

    def test_frozen(self):
        pos = PositionSnapshot(symbol="BTCUSDT", side=SignalSide.LONG, quantity=0.01)
        # Pydantic frozen model — assignment should raise
        try:
            pos.symbol = "ETHUSDT"
            assert False, "Should have raised"
        except (AttributeError, TypeError, ValueError):
            pass


class TestAccountSnapshot:
    def test_defaults(self):
        acc = AccountSnapshot(balance=10000.0, equity=10000.0)
        assert acc.leverage is None


class TestSignalEvent:
    def test_defaults(self):
        sig = SignalEvent(
            strategy_id="sma_cross",
            symbol="BTCUSDT",
            side=SignalSide.LONG,
            timestamp=datetime.now(tz=UTC),
            reason="golden cross",
        )
        assert sig.metadata == {}


class TestOrderIntent:
    def test_defaults(self):
        intent = OrderIntent(
            strategy_id="sma_cross",
            symbol="BTCUSDT",
            side=SignalSide.LONG,
            order_type=OrderType.MARKET,
            quantity=0.01,
        )
        assert intent.limit_price is None
        assert intent.stop_price is None
        assert intent.metadata == {}


class TestStrategyRuntimeConfig:
    def test_defaults(self):
        cfg = StrategyRuntimeConfig(
            strategy_id="sma_cross",
            symbol="BTCUSDT",
            timeframe="15m",
            mode=RuntimeMode.BACKTEST,
        )
        assert cfg.parameters == {}
        assert cfg.risk == {}
        assert cfg.trade_management == {}


class TestAppContext:
    def test_create(self, tmp_path):
        ctx = AppContext(
            root_dir=tmp_path,
            config_dir=tmp_path / "config",
            data_dir=tmp_path / "data",
            state_dir=tmp_path / "state",
            artifacts_dir=tmp_path / "artifacts",
            logs_dir=tmp_path / "logs",
        )
        assert ctx.root_dir == tmp_path
```

### Step 6: 实现 models

v1 用 dataclass，v2 用 Pydantic BaseModel（`frozen=True` 对应 v1 的 `slots=True` 不可变语义）。
增加 `data_dir` 和 `state_dir` 字段到 `AppContext`（v1 中这些是分散传参的，v2 统一收口）。

```python
# src/noesis_agent/core/models.py
from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field

from noesis_agent.core.enums import OrderType, RuntimeMode, SignalSide


def generate_run_id(prefix: str = "run") -> str:
    stamp = datetime.now(tz=UTC).strftime("%Y%m%dT%H%M%SZ")
    return f"{prefix}_{stamp}_{uuid4().hex[:8]}"


class PositionSnapshot(BaseModel):
    model_config = ConfigDict(frozen=True)

    symbol: str
    side: SignalSide
    quantity: float
    entry_price: float | None = None
    entry_bar_index: int | None = None


class AccountSnapshot(BaseModel):
    model_config = ConfigDict(frozen=True)

    balance: float
    equity: float
    leverage: float | None = None


class SignalEvent(BaseModel):
    model_config = ConfigDict(frozen=True)

    strategy_id: str
    symbol: str
    side: SignalSide
    timestamp: datetime
    reason: str
    metadata: dict[str, Any] = Field(default_factory=dict)


class OrderIntent(BaseModel):
    model_config = ConfigDict(frozen=True)

    strategy_id: str
    symbol: str
    side: SignalSide
    order_type: OrderType
    quantity: float
    limit_price: float | None = None
    stop_price: float | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class StrategyRuntimeConfig(BaseModel):
    model_config = ConfigDict(frozen=True)

    strategy_id: str
    symbol: str
    timeframe: str
    mode: RuntimeMode
    parameters: dict[str, Any] = Field(default_factory=dict)
    risk: dict[str, Any] = Field(default_factory=dict)
    trade_management: dict[str, Any] = Field(default_factory=dict)


class AppContext(BaseModel):
    model_config = ConfigDict(frozen=True)

    root_dir: Path
    config_dir: Path
    data_dir: Path
    state_dir: Path
    artifacts_dir: Path
    logs_dir: Path
```

### Step 7: 运行全部测试

运行: `uv run pytest tests/unit/test_core_enums.py tests/unit/test_core_models.py -v`
预期: 全部 PASSED

### Step 8: Lint 检查

运行: `uv run ruff check src/noesis_agent/core/ tests/unit/test_core_enums.py tests/unit/test_core_models.py`
预期: 零违规

### Step 9: 提交

```bash
git add src/noesis_agent/core/ tests/unit/
git commit -m "feat(core): port enums and models from v1 dataclasses to Pydantic v2"
```

---

## Task 2: TOML 配置系统

> 替换 v1 的 .env + 3 层 YAML 合并为结构化 TOML 配置。保留策略级 TOML 覆盖机制。

**设计决策：**
- **系统配置**: `config/config.toml` — 全局设置（交易所、风控、Agent 角色、模型路由）
- **策略配置**: `config/strategies/{strategy_id}.toml` — 每个策略独立文件（参数、交易管理、优化空间）
- **合并语义**: 系统配置提供默认值，策略配置覆盖 `[risk]` 和 `[trade_management]` 部分
- **敏感值**: API key 等全部走环境变量，TOML 里不出现

**文件：**
- 创建: `src/noesis_agent/core/config.py`
- 创建: `config/config.example.toml`
- 创建: `config/strategies/template.toml`
- 创建: `tests/unit/test_config.py`

**v1 参考：**
- `/Users/ethan/Qporter Lite/src/qporter_lite/config/models.py` (ExchangeConfig, OptimizeConfigSpec)
- `/Users/ethan/Qporter Lite/src/qporter_lite/config/resolver.py` (3 层合并逻辑、trade_management 验证)
- `/Users/ethan/Qporter Lite/config/base.yaml` (默认配置 schema)
- `/Users/ethan/Qporter Lite/config/strategies/sma_cross.yaml` (策略配置示例)

### Step 1: 写配置测试

```python
# tests/unit/test_config.py
import os
import textwrap

import pytest

from noesis_agent.core.config import (
    AgentRoleConfig,
    ExchangeConfig,
    NoesisSettings,
    RiskConfig,
    StrategyConfig,
    TradeManagementConfig,
    load_strategy_config,
    resolve_strategy_runtime_config,
)
from noesis_agent.core.enums import RuntimeMode


class TestNoesisSettings:
    def test_defaults(self, tmp_path):
        """加载不带任何 TOML 文件的默认配置"""
        settings = NoesisSettings(
            _env_file=None,
            root_dir=tmp_path,
        )
        assert settings.mode == RuntimeMode.BACKTEST
        assert settings.symbol == "BTCUSDT"
        assert settings.timeframe == "15m"
        assert settings.risk.max_daily_loss_pct == 0.05

    def test_toml_override(self, tmp_path):
        """TOML 文件覆盖默认值"""
        config_file = tmp_path / "config.toml"
        config_file.write_text(textwrap.dedent("""\
            mode = "testnet"
            symbol = "ETHUSDT"
            timeframe = "1h"

            [risk]
            max_daily_loss_pct = 0.03
            max_leverage = 5
        """))
        settings = NoesisSettings(
            _env_file=None,
            root_dir=tmp_path,
            config_path=config_file,
        )
        assert settings.mode == RuntimeMode.TESTNET
        assert settings.symbol == "ETHUSDT"
        assert settings.risk.max_daily_loss_pct == 0.03
        assert settings.risk.max_leverage == 5

    def test_env_override_toml(self, tmp_path, monkeypatch):
        """环境变量优先于 TOML"""
        config_file = tmp_path / "config.toml"
        config_file.write_text('symbol = "BTCUSDT"')
        monkeypatch.setenv("NOESIS_SYMBOL", "SOLUSDT")
        settings = NoesisSettings(
            _env_file=None,
            root_dir=tmp_path,
            config_path=config_file,
        )
        assert settings.symbol == "SOLUSDT"


class TestExchangeConfig:
    def test_api_key_from_env(self, monkeypatch):
        monkeypatch.setenv("BINANCE_TESTNET_API_KEY", "test-key")
        monkeypatch.setenv("BINANCE_TESTNET_API_SECRET", "test-secret")
        cfg = ExchangeConfig(
            exchange_id="binance_usdm",
            account_type="futures",
            api_key_env="BINANCE_TESTNET_API_KEY",
            api_secret_env="BINANCE_TESTNET_API_SECRET",
        )
        assert cfg.resolve_api_key() == "test-key"
        assert cfg.resolve_api_secret() == "test-secret"

    def test_missing_env_returns_none(self):
        cfg = ExchangeConfig(
            exchange_id="binance_usdm",
            account_type="futures",
        )
        assert cfg.resolve_api_key() is None


class TestRiskConfig:
    def test_defaults(self):
        risk = RiskConfig()
        assert risk.max_position_size == 0.01
        assert risk.max_leverage == 3
        assert risk.max_daily_loss_pct == 0.05
        assert risk.read_only is False


class TestTradeManagementConfig:
    def test_defaults_all_none(self):
        tm = TradeManagementConfig()
        assert tm.stop_loss_pct is None
        assert tm.take_profit_pct is None
        assert tm.trailing_stop_pct is None
        assert tm.max_holding_bars is None
        assert tm.cooldown_bars is None
        assert tm.confirm_bars is None

    def test_validation_positive_float(self):
        with pytest.raises(ValueError):
            TradeManagementConfig(stop_loss_pct=-0.01)

    def test_validation_min_bars(self):
        with pytest.raises(ValueError):
            TradeManagementConfig(max_holding_bars=0)


class TestStrategyConfig:
    def test_load_from_toml(self, tmp_path):
        strat_file = tmp_path / "sma_cross.toml"
        strat_file.write_text(textwrap.dedent("""\
            strategy_id = "sma_cross"
            strategy_name = "SMA Crossover"
            status = "active"

            [parameters]
            fast_period = 5
            slow_period = 20

            [trade_management]
            stop_loss_pct = 0.02
            take_profit_pct = 0.04

            [optimize]
            default_method = "grid"
            timeframes = ["15m", "1h"]
            lookback_days = 90

            [optimize.parameter_space]
            fast_period = [3, 5, 8, 13]
            slow_period = [20, 50, 100]
        """))
        cfg = load_strategy_config(strat_file)
        assert cfg.strategy_id == "sma_cross"
        assert cfg.parameters == {"fast_period": 5, "slow_period": 20}
        assert cfg.trade_management.stop_loss_pct == 0.02
        assert cfg.optimize.default_method == "grid"
        assert cfg.optimize.parameter_space == {
            "fast_period": [3, 5, 8, 13],
            "slow_period": [20, 50, 100],
        }


class TestResolveStrategyRuntimeConfig:
    def test_merge_strategy_over_system(self, tmp_path):
        """策略配置覆盖系统默认的 risk 和 trade_management"""
        config_file = tmp_path / "config.toml"
        config_file.write_text(textwrap.dedent("""\
            symbol = "BTCUSDT"
            timeframe = "15m"

            [risk]
            max_daily_loss_pct = 0.05
            max_leverage = 3

            [trade_management]
            stop_loss_pct = 0.03
        """))
        strat_dir = tmp_path / "strategies"
        strat_dir.mkdir()
        strat_file = strat_dir / "sma_cross.toml"
        strat_file.write_text(textwrap.dedent("""\
            strategy_id = "sma_cross"

            [parameters]
            fast_period = 5

            [trade_management]
            stop_loss_pct = 0.02
            take_profit_pct = 0.04
        """))
        settings = NoesisSettings(
            _env_file=None,
            root_dir=tmp_path,
            config_path=config_file,
        )
        runtime_cfg = resolve_strategy_runtime_config(
            settings=settings,
            strategy_id="sma_cross",
            strategies_dir=strat_dir,
        )
        # 策略覆盖了 stop_loss_pct
        assert runtime_cfg.trade_management["stop_loss_pct"] == 0.02
        # 策略新增了 take_profit_pct
        assert runtime_cfg.trade_management["take_profit_pct"] == 0.04
        assert runtime_cfg.parameters == {"fast_period": 5}
        assert runtime_cfg.mode == RuntimeMode.BACKTEST
```

### Step 2: 运行测试确认失败

运行: `uv run pytest tests/unit/test_config.py -v`
预期: FAIL — `ModuleNotFoundError`

### Step 3: 实现配置系统

实现 `src/noesis_agent/core/config.py`。关键设计：
- `NoesisSettings` 继承 `pydantic_settings.BaseSettings`
- 支持 TOML 文件 + 环境变量，环境变量优先
- 环境变量前缀: `NOESIS_`
- `ExchangeConfig.resolve_api_key()` 从环境变量读取敏感值
- `TradeManagementConfig` 用 Pydantic validator 替代 v1 的手写验证
- `resolve_strategy_runtime_config()` 合并系统默认 + 策略覆盖 → `StrategyRuntimeConfig`

需要安装额外依赖: `pydantic-settings`

```python
# src/noesis_agent/core/config.py
from __future__ import annotations

import os
import tomllib
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

from noesis_agent.core.enums import RuntimeMode
from noesis_agent.core.models import StrategyRuntimeConfig


class RiskConfig(BaseModel):
    model_config = ConfigDict(frozen=True)

    max_position_size: float = 0.01
    max_leverage: int = 3
    read_only: bool = False
    max_daily_loss_pct: float = 0.05


class TradeManagementConfig(BaseModel):
    model_config = ConfigDict(frozen=True)

    stop_loss_pct: float | None = None
    take_profit_pct: float | None = None
    trailing_stop_pct: float | None = None
    max_holding_bars: int | None = None
    cooldown_bars: int | None = None
    confirm_bars: int | None = None

    @field_validator("stop_loss_pct", "take_profit_pct", "trailing_stop_pct")
    @classmethod
    def positive_float(cls, v: float | None) -> float | None:
        if v is not None and v <= 0:
            raise ValueError("必须为正数")
        return v

    @field_validator("max_holding_bars", "confirm_bars")
    @classmethod
    def min_one(cls, v: int | None) -> int | None:
        if v is not None and v < 1:
            raise ValueError("必须 >= 1")
        return v

    @field_validator("cooldown_bars")
    @classmethod
    def min_zero(cls, v: int | None) -> int | None:
        if v is not None and v < 0:
            raise ValueError("必须 >= 0")
        return v


class ExchangeConfig(BaseModel):
    exchange_id: str = "binance_usdm"
    account_type: str = "futures"
    base_url: str | None = None
    api_key_env: str | None = None
    api_secret_env: str | None = None

    def resolve_api_key(self) -> str | None:
        if self.api_key_env:
            return os.environ.get(self.api_key_env)
        return None

    def resolve_api_secret(self) -> str | None:
        if self.api_secret_env:
            return os.environ.get(self.api_secret_env)
        return None


class OptimizeConfig(BaseModel):
    default_method: str = "grid"
    timeframes: list[str] = Field(default_factory=lambda: ["15m"])
    lookback_days: int = 90
    random_max_trials: int = 50
    parameter_space: dict[str, list[Any]] = Field(default_factory=dict)
    trade_management_parameter_space: dict[str, list[Any]] = Field(default_factory=dict)


class AgentRoleConfig(BaseModel):
    """单个 Agent 角色的配置，对应架构文档的 Agent 角色表"""
    model: str = "openai:gpt-4o"
    fallback: str | None = None
    system_prompt: str = ""
    tools: list[str] = Field(default_factory=list)
    output_format: str = "text"


class StrategyConfig(BaseModel):
    """单个策略的完整配置（从策略 TOML 文件加载）"""
    strategy_id: str
    strategy_name: str = ""
    display_name: str = ""
    description: str = ""
    tags: list[str] = Field(default_factory=list)
    status: str = "active"
    source_type: str = "built_in"
    parameters: dict[str, Any] = Field(default_factory=dict)
    trade_management: TradeManagementConfig = Field(default_factory=TradeManagementConfig)
    optimize: OptimizeConfig = Field(default_factory=OptimizeConfig)


class NoesisSettings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="NOESIS_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # 基础设置
    mode: RuntimeMode = RuntimeMode.BACKTEST
    symbol: str = "BTCUSDT"
    timeframe: str = "15m"

    # 路径（运行时设置，非 TOML）
    root_dir: Path = Field(default_factory=lambda: Path.cwd())
    config_path: Path | None = None

    # 子配置
    risk: RiskConfig = Field(default_factory=RiskConfig)
    trade_management: TradeManagementConfig = Field(default_factory=TradeManagementConfig)
    exchange: ExchangeConfig = Field(default_factory=ExchangeConfig)
    agent_roles: dict[str, AgentRoleConfig] = Field(default_factory=dict)

    def model_post_init(self, __context: Any) -> None:
        # 如果提供了 config_path，从 TOML 加载并合并
        if self.config_path and self.config_path.exists():
            with open(self.config_path, "rb") as f:
                toml_data = tomllib.load(f)
            self._merge_toml(toml_data)

    def _merge_toml(self, toml_data: dict[str, Any]) -> None:
        """将 TOML 数据合并到当前设置（env var 优先级更高，不会被覆盖）"""
        # 只合并未被 env var 覆盖的字段
        for key in ("mode", "symbol", "timeframe"):
            env_key = f"NOESIS_{key.upper()}"
            if key in toml_data and not os.environ.get(env_key):
                object.__setattr__(self, key, toml_data[key] if key != "mode" else RuntimeMode(toml_data[key]))

        if "risk" in toml_data:
            merged_risk = {**self.risk.model_dump(), **toml_data["risk"]}
            object.__setattr__(self, "risk", RiskConfig(**merged_risk))

        if "trade_management" in toml_data:
            merged_tm = {**self.trade_management.model_dump(), **toml_data["trade_management"]}
            object.__setattr__(self, "trade_management", TradeManagementConfig(**merged_tm))

        if "exchange" in toml_data:
            merged_ex = {**self.exchange.model_dump(), **toml_data["exchange"]}
            object.__setattr__(self, "exchange", ExchangeConfig(**merged_ex))

        if "agent_roles" in toml_data:
            roles = {k: AgentRoleConfig(**v) for k, v in toml_data["agent_roles"].items()}
            object.__setattr__(self, "agent_roles", roles)


def load_strategy_config(path: Path) -> StrategyConfig:
    """从 TOML 文件加载单个策略配置"""
    with open(path, "rb") as f:
        data = tomllib.load(f)
    return StrategyConfig(**data)


def resolve_strategy_runtime_config(
    *,
    settings: NoesisSettings,
    strategy_id: str,
    strategies_dir: Path | None = None,
) -> StrategyRuntimeConfig:
    """合并系统配置 + 策略配置 → StrategyRuntimeConfig（v1 resolve_strategy_config 的 v2 等价物）"""
    # 系统默认的 trade_management
    base_tm = {k: v for k, v in settings.trade_management.model_dump().items() if v is not None}
    base_risk = settings.risk.model_dump()

    parameters: dict[str, Any] = {}
    strategy_tm: dict[str, Any] = {}

    # 加载策略特定配置
    if strategies_dir:
        strat_path = strategies_dir / f"{strategy_id}.toml"
        if strat_path.exists():
            strat_cfg = load_strategy_config(strat_path)
            parameters = strat_cfg.parameters
            strategy_tm = {k: v for k, v in strat_cfg.trade_management.model_dump().items() if v is not None}

    # 合并: 策略覆盖系统默认
    merged_tm = {**base_tm, **strategy_tm}

    return StrategyRuntimeConfig(
        strategy_id=strategy_id,
        symbol=settings.symbol,
        timeframe=settings.timeframe,
        mode=settings.mode,
        parameters=parameters,
        risk=base_risk,
        trade_management=merged_tm,
    )
```

### Step 4: 添加 pydantic-settings 依赖

在 `pyproject.toml` 的 `dependencies` 中添加 `pydantic-settings>=2.7`。

### Step 5: 运行测试

运行: `uv run pytest tests/unit/test_config.py -v`
预期: 全部 PASSED

### Step 6: 创建配置模板

```toml
# config/config.example.toml
# Noesis Agent 系统配置
# 复制为 config/config.toml 后编辑

mode = "backtest"   # backtest | testnet | live
symbol = "BTCUSDT"
timeframe = "15m"

[risk]
max_position_size = 0.01
max_leverage = 3
read_only = false
max_daily_loss_pct = 0.05

[trade_management]
# stop_loss_pct = 0.03
# take_profit_pct = 0.06
# trailing_stop_pct = 0.02
# max_holding_bars = 100
# cooldown_bars = 5
# confirm_bars = 2

[exchange]
exchange_id = "binance_usdm"
account_type = "futures"
# api_key_env = "BINANCE_TESTNET_API_KEY"
# api_secret_env = "BINANCE_TESTNET_API_SECRET"

# Agent 角色配置（阶段 2 启用）
# [agent_roles.analyst]
# model = "anthropic:claude-opus-4"
# fallback = "openai:gpt-4o"
# system_prompt = "你是一个加密货币策略分析师..."
# tools = ["get_trade_records", "compute_indicators"]
# output_format = "structured"
```

```toml
# config/strategies/template.toml
# 策略配置模板 — 复制并重命名为 {strategy_id}.toml

strategy_id = "my_strategy"
strategy_name = "My Strategy"
status = "active"

[parameters]
# 策略特有参数
# fast_period = 5

[trade_management]
# stop_loss_pct = 0.02
# take_profit_pct = 0.04

[optimize]
default_method = "grid"
timeframes = ["15m"]
lookback_days = 90

[optimize.parameter_space]
# fast_period = [3, 5, 8, 13]
```

### Step 7: Lint 检查 + 提交

运行: `uv run ruff check src/noesis_agent/core/config.py tests/unit/test_config.py`
预期: 零违规

```bash
git add src/noesis_agent/core/config.py config/ tests/unit/test_config.py pyproject.toml
git commit -m "feat(config): add TOML-based config system with Pydantic Settings"
```

---

## Task 3: 数据层协议 + 工具函数

> 定义 MarketDataAdapter Protocol，迁移不依赖交易所的工具函数。

**设计决策：**
- `MarketDataAdapter` Protocol 仿照 v1 的 `ExecutionAdapter` Protocol 模式
- `close_time` 列不进入标准 DataFrame — Binance 适配器内部处理
- `interval_to_milliseconds`、`write_market_data_csv`、`load_market_data_csv` 直接迁移
- HTTP 客户端从 urllib 升级为 httpx

**文件：**
- 创建: `src/noesis_agent/data/adapter.py`
- 创建: `src/noesis_agent/data/ingestion.py`（仅工具函数）
- 创建: `src/noesis_agent/data/catalog.py`（从 v1 直接迁移）
- 创建: `src/noesis_agent/data/resample.py`（从 v1 直接迁移）
- 创建: `tests/unit/test_data_adapter.py`
- 创建: `tests/unit/test_data_ingestion.py`

**v1 参考：**
- `/Users/ethan/Qporter Lite/src/qporter_lite/data/ingestion.py` (interval_to_milliseconds, write/load CSV)
- `/Users/ethan/Qporter Lite/src/qporter_lite/data/catalog.py`
- `/Users/ethan/Qporter Lite/src/qporter_lite/data/resample.py`

### Step 1: 写 adapter Protocol 测试

```python
# tests/unit/test_data_adapter.py
import pandas as pd
import pytest

from noesis_agent.data.adapter import MarketDataAdapter


class FakeAdapter:
    """测试用假适配器，验证 Protocol 合规性"""
    source_id = "fake_exchange"

    def fetch_klines(
        self,
        *,
        symbol: str,
        interval: str,
        limit: int = 500,
        start_time_ms: int | None = None,
        end_time_ms: int | None = None,
    ) -> pd.DataFrame:
        return pd.DataFrame(
            {"open": [1.0], "high": [2.0], "low": [0.5], "close": [1.5], "volume": [100.0]},
            index=pd.to_datetime(["2025-01-01"], utc=True),
        )

    def fetch_klines_range(
        self,
        *,
        symbol: str,
        interval: str,
        start_time_ms: int,
        end_time_ms: int,
        progress_callback=None,
    ) -> pd.DataFrame:
        return self.fetch_klines(symbol=symbol, interval=interval)


class TestMarketDataAdapterProtocol:
    def test_fake_adapter_is_protocol_compliant(self):
        adapter: MarketDataAdapter = FakeAdapter()
        assert adapter.source_id == "fake_exchange"

    def test_fetch_klines_returns_standard_columns(self):
        adapter = FakeAdapter()
        df = adapter.fetch_klines(symbol="BTCUSDT", interval="15m")
        assert list(df.columns) == ["open", "high", "low", "close", "volume"]
        assert df.index.tz is not None  # UTC timezone-aware

    def test_fetch_klines_range_returns_standard_columns(self):
        adapter = FakeAdapter()
        df = adapter.fetch_klines_range(
            symbol="BTCUSDT", interval="15m",
            start_time_ms=0, end_time_ms=1000,
        )
        assert list(df.columns) == ["open", "high", "low", "close", "volume"]
```

### Step 2: 实现 adapter Protocol

```python
# src/noesis_agent/data/adapter.py
from __future__ import annotations

from typing import Callable, Protocol

import pandas as pd


class MarketDataAdapter(Protocol):
    """市场数据适配器协议 — 仿照 ExecutionAdapter 的 Protocol 模式。

    所有适配器必须返回标准 5 列 DataFrame:
      Index: UTC DatetimeIndex
      Columns: open, high, low, close, volume (全部 float)

    交易所特有字段（如 Binance 的 close_time）不进入返回的 DataFrame。
    """

    source_id: str

    def fetch_klines(
        self,
        *,
        symbol: str,
        interval: str,
        limit: int = 500,
        start_time_ms: int | None = None,
        end_time_ms: int | None = None,
    ) -> pd.DataFrame:
        """单批拉取 K 线数据（最多 limit 根）"""
        ...

    def fetch_klines_range(
        self,
        *,
        symbol: str,
        interval: str,
        start_time_ms: int,
        end_time_ms: int,
        progress_callback: Callable[[int, int], None] | None = None,
    ) -> pd.DataFrame:
        """分页拉取指定时间范围的 K 线数据"""
        ...
```

### Step 3: 迁移工具函数

从 v1 迁移 `interval_to_milliseconds`、`write_market_data_csv`、`load_market_data_csv`。
这些函数零交易所耦合，直接搬过来。`load_market_data_csv` 需要兼容旧的含 `close_time` 列的 CSV。

```python
# src/noesis_agent/data/ingestion.py — 仅通用工具函数，不含交易所逻辑
from __future__ import annotations

from pathlib import Path

import pandas as pd

from noesis_agent.data.catalog import CatalogEntry, upsert_catalog_entry


def interval_to_milliseconds(interval: str) -> int:
    """将 K 线周期字符串转为毫秒。支持: m, h, d, w"""
    unit = interval[-1]
    value = int(interval[:-1])
    if unit == "m":
        return value * 60_000
    if unit == "h":
        return value * 3_600_000
    if unit == "d":
        return value * 86_400_000
    if unit == "w":
        return value * 604_800_000
    raise ValueError(f"Unsupported interval: {interval}")


def write_market_data_csv(
    data_dir: Path,
    *,
    source: str,
    symbol: str,
    timeframe: str,
    frame: pd.DataFrame,
) -> Path:
    """将 OHLCV DataFrame 写入 CSV，并更新 catalog"""
    target = data_dir / "raw" / source / symbol / f"{timeframe}.csv"
    target.parent.mkdir(parents=True, exist_ok=True)
    output = frame.copy()
    output.index.name = "timestamp"
    output.to_csv(target, index_label="timestamp")
    upsert_catalog_entry(
        data_dir,
        CatalogEntry(
            symbol=symbol,
            timeframe=timeframe,
            source=source,
            path=str(target.relative_to(data_dir)),
            rows=len(frame),
            start_ts=str(frame.index.min()) if not frame.empty else "",
            end_ts=str(frame.index.max()) if not frame.empty else "",
        ),
    )
    return target


def load_market_data_csv(
    data_dir: Path,
    *,
    source: str,
    symbol: str,
    timeframe: str,
) -> pd.DataFrame:
    """从 CSV 读取 OHLCV 数据。兼容含 close_time 列的旧格式。"""
    target = data_dir / "raw" / source / symbol / f"{timeframe}.csv"
    parse_dates = ["timestamp"]
    # 兼容 v1 格式：如果文件含 close_time 列也解析它
    with open(target) as f:
        header = f.readline()
    if "close_time" in header:
        parse_dates.append("close_time")
    frame = pd.read_csv(target, parse_dates=parse_dates, index_col="timestamp")
    frame.index = pd.to_datetime(frame.index, utc=True)
    return frame
```

### Step 4: 迁移 catalog.py 和 resample.py

从 v1 直接搬过来，仅修改 import 路径。这两个文件零交易所耦合。

（catalog.py 和 resample.py 的代码在 v1 中已经是干净的通用实现，直接复制并调整包名即可。具体内容从 v1 文件复制。）

### Step 5: 写工具函数测试

```python
# tests/unit/test_data_ingestion.py
import pandas as pd
import pytest

from noesis_agent.data.ingestion import (
    interval_to_milliseconds,
    load_market_data_csv,
    write_market_data_csv,
)


class TestIntervalToMilliseconds:
    def test_minutes(self):
        assert interval_to_milliseconds("15m") == 900_000
        assert interval_to_milliseconds("1m") == 60_000

    def test_hours(self):
        assert interval_to_milliseconds("1h") == 3_600_000
        assert interval_to_milliseconds("4h") == 14_400_000

    def test_days(self):
        assert interval_to_milliseconds("1d") == 86_400_000

    def test_weeks(self):
        assert interval_to_milliseconds("1w") == 604_800_000

    def test_invalid(self):
        with pytest.raises(ValueError, match="Unsupported interval"):
            interval_to_milliseconds("1x")


class TestWriteAndLoadCsv:
    def test_roundtrip(self, tmp_path):
        data_dir = tmp_path / "data"
        data_dir.mkdir()
        index = pd.to_datetime(["2025-01-01", "2025-01-02"], utc=True)
        df = pd.DataFrame(
            {"open": [1.0, 2.0], "high": [1.5, 2.5], "low": [0.5, 1.5],
             "close": [1.2, 2.2], "volume": [100.0, 200.0]},
            index=index,
        )
        df.index.name = "timestamp"
        write_market_data_csv(data_dir, source="test_exchange", symbol="BTCUSDT", timeframe="1d", frame=df)
        loaded = load_market_data_csv(data_dir, source="test_exchange", symbol="BTCUSDT", timeframe="1d")
        assert len(loaded) == 2
        assert list(loaded.columns) == ["open", "high", "low", "close", "volume"]

    def test_catalog_updated(self, tmp_path):
        data_dir = tmp_path / "data"
        data_dir.mkdir()
        df = pd.DataFrame(
            {"open": [1.0], "high": [1.5], "low": [0.5], "close": [1.2], "volume": [100.0]},
            index=pd.to_datetime(["2025-01-01"], utc=True),
        )
        df.index.name = "timestamp"
        write_market_data_csv(data_dir, source="test_ex", symbol="ETHUSDT", timeframe="15m", frame=df)
        catalog_file = data_dir / "catalog.json"
        assert catalog_file.exists()
```

### Step 6: 运行测试

运行: `uv run pytest tests/unit/test_data_adapter.py tests/unit/test_data_ingestion.py -v`
预期: 全部 PASSED

### Step 7: 提交

```bash
git add src/noesis_agent/data/ tests/unit/test_data_adapter.py tests/unit/test_data_ingestion.py
git commit -m "feat(data): define MarketDataAdapter protocol and port utility functions from v1"
```

---

## Task 4: Binance 数据适配器

> 实现 BinanceFuturesAdapter 和 BinanceSpotAdapter，替代 v1 的硬编码函数。

**文件：**
- 创建: `src/noesis_agent/data/binance.py`
- 创建: `tests/unit/test_data_binance.py`

**v1 参考：**
- `/Users/ethan/Qporter Lite/src/qporter_lite/data/ingestion.py` (_fetch_binance_klines, _fetch_binance_klines_range, 解析逻辑)

### Step 1: 写测试（用 mock httpx 响应，不调用真实 API）

测试 BinanceFuturesAdapter 和 BinanceSpotAdapter 实现 MarketDataAdapter Protocol。
Mock Binance API 响应格式（list[list]），验证解析为标准 5 列 DataFrame。
测试分页逻辑：mock 两页数据，验证 concat + dedup。
测试错误处理：API 返回 dict（错误响应）→ 抛出 ValueError。

### Step 2: 实现适配器

从 v1 的 `_fetch_binance_klines` 和 `_fetch_binance_klines_range` 提取逻辑，封装为类方法。
用 httpx 替代 urllib。`close_time` 列在解析后丢弃（不进入返回的标准 DataFrame）。

### Step 3: 运行测试 + Lint

运行: `uv run pytest tests/unit/test_data_binance.py -v`
预期: 全部 PASSED（adapter Protocol 合规、解析正确、分页 concat、错误处理）

运行: `uv run ruff check src/noesis_agent/data/binance.py tests/unit/test_data_binance.py`
预期: 零违规

### Step 4: 提交

```bash
git add src/noesis_agent/data/binance.py tests/unit/test_data_binance.py
git commit -m "feat(data): add Binance klines adapters implementing MarketDataAdapter"
```

---

## Task 5: 执行层协议 + 风控纯函数

> 迁移 ExecutionAdapter、ExecutionClient Protocol 和 emergency.py 纯函数。

**文件：**
- 创建: `src/noesis_agent/execution/base.py`
- 创建: `src/noesis_agent/execution/emergency.py`
- 创建: `tests/unit/test_execution_base.py`
- 创建: `tests/unit/test_emergency.py`

**v1 参考：**
- `/Users/ethan/Qporter Lite/src/qporter_lite/execution/base.py` (Protocol + 4 dataclass)
- `/Users/ethan/Qporter Lite/src/qporter_lite/execution/emergency.py` (纯函数，零副作用)

### Step 1-2: 写测试 → 确认失败

测试 ExecutionAdapter Protocol 合规性（用 FakeAdapter）。
测试 emergency 纯函数的所有分支：
- `evaluate_live_safety`: 正常通过、read_only 阻止、emergency_stop 阻止、日亏损超限阻止
- `evaluate_manual_order_safety`: 正常通过、read_only 阻止、未 reconcile 阻止

### Step 3: 实现

`base.py`: 从 v1 直接迁移 Protocol + 4 个 dataclass（改为 Pydantic BaseModel）。
`emergency.py`: 从 v1 直接迁移纯函数（仅改 import 路径）。

### Step 4: 运行测试 + Lint

运行: `uv run pytest tests/unit/test_execution_base.py tests/unit/test_emergency.py -v`
预期: 全部 PASSED（Protocol 合规、safety 所有分支覆盖）

运行: `uv run ruff check src/noesis_agent/execution/ tests/unit/test_execution_base.py tests/unit/test_emergency.py`
预期: 零违规

### Step 5: 提交

```bash
git add src/noesis_agent/execution/ tests/unit/test_execution_base.py tests/unit/test_emergency.py
git commit -m "feat(execution): port ExecutionAdapter protocol and risk evaluation pure functions"
```

---

## Task 6: 策略基类 + 工厂

> 迁移 StrategyBase ABC 和策略注册/发现机制。

**文件：**
- 创建: `src/noesis_agent/strategy/base.py`
- 创建: `src/noesis_agent/strategy/registry.py`
- 创建: `tests/unit/test_strategy_base.py`

**v1 参考：**
- `/Users/ethan/Qporter Lite/src/qporter_lite/strategy/base.py` (StrategyBase ABC)
- `/Users/ethan/Qporter Lite/src/qporter_lite/strategy/__init__.py` (build_strategy 工厂)

### Step 1-2: 写测试 → 确认失败

创建一个 `FakeStrategy(StrategyBase)` 实现所有抽象方法，验证接口合规。
测试 `build_strategy()` 能找到已注册策略。

### Step 3: 实现

StrategyBase ABC 从 v1 直接迁移。
策略注册表用 `dict[str, type[StrategyBase]]` 替代 v1 的 `match` + `importlib` 模式。

### Step 4: 运行测试 + Lint

运行: `uv run pytest tests/unit/test_strategy_base.py -v`
预期: 全部 PASSED（FakeStrategy 合规、build_strategy 工厂查找正确）

运行: `uv run ruff check src/noesis_agent/strategy/ tests/unit/test_strategy_base.py`
预期: 零违规

### Step 5: 提交

```bash
git add src/noesis_agent/strategy/ tests/unit/test_strategy_base.py
git commit -m "feat(strategy): port StrategyBase ABC and strategy registry"
```

---

## Task 7: 回测/优化引擎迁移

> 迁移 BacktestEngine、BrokerSimulator、metrics 计算和优化运行器。

**文件：**
- 创建: `src/noesis_agent/backtest/engine.py`
- 创建: `src/noesis_agent/backtest/broker.py`
- 创建: `src/noesis_agent/backtest/metrics.py`
- 创建: `src/noesis_agent/backtest/report.py`
- 创建: `src/noesis_agent/optimize/runner.py`
- 创建: `src/noesis_agent/optimize/optuna_runner.py`
- 创建: `tests/unit/test_backtest_engine.py`
- 创建: `tests/unit/test_optimize_runner.py`

**v1 参考：**
- `/Users/ethan/Qporter Lite/src/qporter_lite/backtest/` (engine, broker, metrics, report)
- `/Users/ethan/Qporter Lite/src/qporter_lite/optimize/` (runner, optuna_runner)

### 迁移策略

回测引擎和优化引擎在 v1 中已经是通用实现，没有交易所耦合。迁移重点：
1. dataclass → Pydantic BaseModel（BacktestRunResult, BrokerFill, BacktestSummary 等）
2. import 路径调整
3. 保留全部 trade management 逻辑（stop_loss, take_profit, trailing_stop, max_holding_bars, cooldown, confirm_bars）

### Step 1: 写引擎测试

用一个简单的 FakeStrategy（固定信号）+ 已知数据，验证：
- 回测产出 fills 和 bar_results
- 止损/止盈正确触发
- metrics 计算（total_return, drawdown, win_rate）

### Step 2: 迁移引擎代码

### Step 3: 写优化测试

Grid search 用 2x2 参数空间，验证产出 4 个 trial。
验证 ranking（total_return DESC）。

### Step 4: 迁移优化代码

### Step 5: 运行测试 + Lint

运行: `uv run pytest tests/unit/test_backtest_engine.py tests/unit/test_optimize_runner.py -v`
预期: 全部 PASSED（回测 fills 产出正确、止损/止盈触发、metrics 计算、grid search 产出 4 trial、ranking 正确）

运行: `uv run ruff check src/noesis_agent/backtest/ src/noesis_agent/optimize/`
预期: 零违规

### Step 6: 提交

```bash
git add src/noesis_agent/backtest/ src/noesis_agent/optimize/ tests/unit/test_backtest_engine.py tests/unit/test_optimize_runner.py
git commit -m "feat(backtest): port backtest engine, broker simulator, and optimization runners from v1"
```

---

## Task 8: 调度器

> APScheduler + asyncio 心跳系统。独立模块，不依赖 Agent 基础设施。

**文件：**
- 创建: `src/noesis_agent/services/scheduler.py`
- 创建: `tests/unit/test_scheduler.py`

### 设计

```python
# 三级心跳 + 事件驱动
class NoesisScheduler:
    def __init__(self, settings: NoesisSettings):
        self._scheduler = AsyncIOScheduler()
        self._event_handlers: dict[str, list[Callable]] = {}

    async def start(self):
        """启动调度器，注册心跳任务"""
        self._scheduler.add_job(self._heartbeat_minute, "interval", minutes=1)
        self._scheduler.add_job(self._heartbeat_daily, "cron", hour=0, minute=5)
        self._scheduler.add_job(self._heartbeat_monthly, "cron", day=1, hour=1)
        self._scheduler.start()

    async def stop(self): ...
    def on_event(self, event_type: str, handler: Callable): ...
    async def emit_event(self, event_type: str, payload: dict): ...

    async def _heartbeat_minute(self): ...   # 健康检查、风控状态
    async def _heartbeat_daily(self): ...    # 环境状态更新
    async def _heartbeat_monthly(self): ...  # 触发分析闭环
```

### Step 1: 写测试

测试心跳注册和事件分发。用 `AsyncIOScheduler` 的 mock 模式或短间隔测试。

### Step 2: 实现

### Step 3: 运行测试 + Lint

运行: `uv run pytest tests/unit/test_scheduler.py -v`
预期: 全部 PASSED（心跳注册、事件分发、start/stop 生命周期）

运行: `uv run ruff check src/noesis_agent/services/scheduler.py tests/unit/test_scheduler.py`
预期: 零违规

### Step 4: 提交

```bash
git add src/noesis_agent/services/scheduler.py tests/unit/test_scheduler.py
git commit -m "feat(scheduler): add APScheduler + asyncio heartbeat system"
```

---

## Task 9: 记忆系统

> SQLite + FTS5 三类记忆。最小 schema 起步，业务方法接口。

**文件：**
- 创建: `src/noesis_agent/agent/memory/store.py`
- 创建: `src/noesis_agent/agent/memory/models.py`
- 创建: `tests/unit/test_memory.py`

### 设计

**最小 schema — 一张主表 + FTS5 索引：**

```sql
CREATE TABLE memory_records (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    memory_type TEXT NOT NULL,        -- 'scratchpad' | 'knowledge' | 'failure'
    category TEXT NOT NULL DEFAULT '', -- 'analysis_report' | 'proposal' | 'backtest_comparison' | ...
    strategy_id TEXT DEFAULT NULL,
    title TEXT NOT NULL,
    content TEXT NOT NULL,             -- 完整内容（报告正文、提案内容等）
    tags TEXT DEFAULT '',              -- 逗号分隔的标签
    metadata_json TEXT DEFAULT '{}',   -- 开放式 JSON 元数据
    status TEXT DEFAULT 'active',      -- 'active' | 'archived' | 'rejected'
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE VIRTUAL TABLE memory_fts USING fts5(
    title, content, tags,
    content=memory_records,
    content_rowid=id
);
```

**业务方法接口：**

```python
class MemoryStore:
    def __init__(self, db_path: str | Path): ...

    # 写入
    def store(self, record: MemoryRecord) -> int: ...
    def store_failure(self, failure: FailureRecord) -> int: ...

    # 查询
    def query_failures(
        self, *, strategy_id: str | None = None,
        category: str | None = None, tags: list[str] | None = None,
        limit: int = 20,
    ) -> list[FailureRecord]: ...

    def search_similar(self, query: str, *, top_k: int = 10) -> list[MemoryRecord]: ...

    def get_proposals(
        self, *, strategy_id: str | None = None,
        status: str | None = None,
    ) -> list[MemoryRecord]: ...

    def get_reports(self, *, period: str | None = None) -> list[MemoryRecord]: ...
```

### Step 1: 写测试

```python
# tests/unit/test_memory.py
from noesis_agent.agent.memory.store import MemoryStore
from noesis_agent.agent.memory.models import FailureRecord, MemoryRecord


class TestMemoryStore:
    def test_store_and_retrieve(self):
        store = MemoryStore(":memory:")
        record_id = store.store(MemoryRecord(
            memory_type="knowledge",
            category="analysis_report",
            title="2025-01 BTC 月度分析",
            content="策略在震荡市中表现良好...",
        ))
        assert record_id > 0
        results = store.get_reports()
        assert len(results) == 1

    def test_store_failure_and_query(self):
        store = MemoryStore(":memory:")
        store.store_failure(FailureRecord(
            strategy_id="sma_cross",
            category="parameter_change",
            title="快慢周期过近导致过拟合",
            content="fast=8, slow=10 的组合在回测中夏普极高但 walk-forward 衰减 60%",
            tags=["overfitting", "parameter"],
        ))
        results = store.query_failures(strategy_id="sma_cross")
        assert len(results) == 1
        assert "overfitting" in results[0].tags

    def test_search_similar_fts5(self):
        store = MemoryStore(":memory:")
        store.store(MemoryRecord(
            memory_type="knowledge",
            category="analysis_report",
            title="震荡市分析",
            content="在窄幅震荡环境下，趋势跟踪策略连续亏损",
        ))
        store.store(MemoryRecord(
            memory_type="knowledge",
            category="analysis_report",
            title="趋势市分析",
            content="强趋势环境下策略表现优异",
        ))
        results = store.search_similar("震荡 亏损")
        assert len(results) >= 1
        assert "震荡" in results[0].title

    def test_failure_memory_not_returned_by_get_reports(self):
        store = MemoryStore(":memory:")
        store.store_failure(FailureRecord(
            strategy_id="sma_cross",
            category="rejected_proposal",
            title="被否决的提案",
            content="...",
        ))
        reports = store.get_reports()
        assert len(reports) == 0  # failure 不是 report
```

### Step 2: 实现

### Step 3: 运行测试 + Lint

运行: `uv run pytest tests/unit/test_memory.py -v`
预期: 全部 PASSED（store + retrieve、failure 查询、FTS5 搜索、类型隔离）

运行: `uv run ruff check src/noesis_agent/agent/memory/ tests/unit/test_memory.py`
预期: 零违规

### Step 4: 提交

```bash
git add src/noesis_agent/agent/memory/ tests/unit/test_memory.py
git commit -m "feat(memory): add SQLite + FTS5 memory system with business query interface"
```

---

## Task 10: 模型路由

> LiteLLM 集成 + TOML 配置的 Agent 角色 + PydanticAI 封装。

**文件：**
- 创建: `src/noesis_agent/agent/models.py`（PydanticAI 封装层，隔离 V2 迁移面）
- 创建: `tests/unit/test_agent_models.py`

### 设计

```python
# src/noesis_agent/agent/models.py
class ModelRouter:
    """根据 TOML 配置的 Agent 角色选择模型"""

    def __init__(self, agent_roles: dict[str, AgentRoleConfig]):
        self._roles = agent_roles

    def get_model(self, role: str) -> str:
        """返回 PydanticAI 兼容的模型标识符"""
        cfg = self._roles.get(role)
        if not cfg:
            raise ValueError(f"Unknown agent role: {role}")
        return cfg.model

    def get_fallback_model(self, role: str) -> str | None:
        cfg = self._roles.get(role)
        return cfg.fallback if cfg else None

    def create_agent(
        self,
        role: str,
        *,
        output_type: type | None = None,
        tools: list | None = None,
        deps_type: type | None = None,
    ) -> Agent:
        """创建已配置好模型的 PydanticAI Agent"""
        cfg = self._roles[role]
        model_id = cfg.model
        # 如果有 fallback，用 FallbackModel
        if cfg.fallback:
            from pydantic_ai.models.fallback import FallbackModel
            model = FallbackModel(model_id, cfg.fallback)
        else:
            model = model_id

        return Agent(
            model,
            system_prompt=cfg.system_prompt or None,
            output_type=output_type,
            tools=tools or [],
            deps_type=deps_type,
        )
```

**不依赖真实 LLM API key 的测试策略：**
- 测试 ModelRouter 的路由逻辑（纯 Python，不调用 LLM）
- 测试 Agent 创建参数正确性
- 真正的 LLM 集成测试留到后面

### Step 1: 写测试

### Step 2: 实现

### Step 3: 运行测试 + Lint

运行: `uv run pytest tests/unit/test_agent_models.py -v`
预期: 全部 PASSED（路由查找、fallback 模型、Agent 创建参数正确、unknown role 抛异常）

运行: `uv run ruff check src/noesis_agent/agent/models.py tests/unit/test_agent_models.py`
预期: 零违规

### Step 4: 提交

```bash
git add src/noesis_agent/agent/models.py tests/unit/test_agent_models.py
git commit -m "feat(agent): add model router with TOML-configured agent roles via LiteLLM"
```

---

## Task 11: 技能注册表

> 把已有引擎封装为 Agent 可调用的技能。

**文件：**
- 创建: `src/noesis_agent/agent/skills/registry.py`
- 创建: `src/noesis_agent/agent/skills/backtest_skill.py`
- 创建: `src/noesis_agent/agent/skills/optimize_skill.py`
- 创建: `src/noesis_agent/agent/skills/data_skill.py`
- 创建: `tests/unit/test_skill_registry.py`

### 设计

**关键决策：** 技能接收已解析的依赖（通过 `SkillContext`），不自己构造。避免循环依赖。

```python
@dataclass
class SkillContext:
    """技能执行时的依赖容器"""
    app_context: AppContext
    settings: NoesisSettings
    data_adapter: MarketDataAdapter
    memory: MemoryStore

class SkillResult(BaseModel):
    success: bool
    data: dict[str, Any] = Field(default_factory=dict)
    message: str = ""

class SkillRegistry:
    def __init__(self):
        self._skills: dict[str, Callable] = {}

    def register(self, name: str, fn: Callable) -> None: ...
    def get(self, name: str) -> Callable: ...
    def list_skills(self) -> list[str]: ...

    def register_defaults(self, ctx: SkillContext) -> None:
        """注册所有内置技能"""
        self.register("run_backtest", partial(run_backtest_skill, ctx=ctx))
        self.register("optimize_params", partial(optimize_params_skill, ctx=ctx))
        self.register("get_market_data", partial(get_market_data_skill, ctx=ctx))
        self.register("get_trade_records", partial(get_trade_records_skill, ctx=ctx))
```

### Step 1: 写测试

测试 SkillRegistry 的注册、查找、列表功能。
测试一个具体技能（如 `run_backtest`）用 FakeStrategy + 假数据的完整执行。

### Step 2: 实现

### Step 3: 运行测试 + Lint

运行: `uv run pytest tests/unit/test_skill_registry.py -v`
预期: 全部 PASSED（注册/查找/列表、run_backtest 技能用 FakeStrategy 完整执行）

运行: `uv run ruff check src/noesis_agent/agent/skills/ tests/unit/test_skill_registry.py`
预期: 零违规

### Step 4: 提交

```bash
git add src/noesis_agent/agent/skills/ tests/unit/test_skill_registry.py
git commit -m "feat(agent): add skill registry wrapping engine capabilities"
```

---

## 版本锁定

在所有 Task 开始前，先更新 `pyproject.toml`：

```toml
dependencies = [
    "fastapi>=0.115",
    "uvicorn>=0.34",
    "pydantic>=2.10",
    "pydantic-settings>=2.7",
    "pydantic-ai>=1.0,<2.0",    # pin: V2 breaking changes April 2026
    "litellm>=1.60,<2.0",        # pin: 隔离大版本变更
    "httpx>=0.28",
    "pandas>=2.2",
    "TA-Lib>=0.6",
    "ccxt>=4.4",
    "apscheduler>=3.10",
]
```

---

## 验收标准

1. `uv run pytest tests/ -x` — 零失败
2. `uv run ruff check src/` — 零违规
3. 不需要任何交易所 API key 即可跑完全部测试
4. 不需要任何 LLM API key 即可跑完全部测试
5. `python -c "from noesis_agent.core.config import NoesisSettings; print(NoesisSettings(root_dir='.').model_dump())"` — 输出有效默认配置
6. `python -c "from noesis_agent.agent.memory.store import MemoryStore; m = MemoryStore(':memory:'); print('OK')"` — 内存模式正常
