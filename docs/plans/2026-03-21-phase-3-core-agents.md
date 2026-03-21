# 阶段 3：核心 Agent + 审批协议 实施计划

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**目标：** 实现分析 Agent、提案 Agent、验证 Agent 和完整审批协议状态机，形成 AI 驱动的策略改进闭环。

**架构：** 三个 PydanticAI Agent 串联 → 审批协议（5 道自动门控 + 人工审批节点）→ 状态机驱动提案生命周期。门控是纯函数（不依赖 LLM），Agent 用 PydanticAI 结构化输出。测试分两层：门控/类型用纯 Python TDD，Agent LLM 调用用 `pydantic_ai.models.test.TestModel` mock。

**技术栈：** PydanticAI 1.x (Agent + 结构化输出 + tools) / SQLite (记忆系统) / pytest

**已有基础（阶段 2 交付）：**
- `src/noesis_agent/agent/models.py` — ModelRouter（路由到 TOML 配置的模型）
- `src/noesis_agent/agent/memory/store.py` — MemoryStore（SQLite + FTS5）
- `src/noesis_agent/agent/skills/registry.py` — SkillRegistry + SkillContext + SkillResult
- `src/noesis_agent/backtest/` — BacktestEngine, BacktestSummary, calculate_summary
- `src/noesis_agent/core/config.py` — AgentRoleConfig（model, fallback, system_prompt, tools, output_format）

---

## 依赖关系图

```
Task 1: Agent 输出类型 (零依赖，纯 Pydantic 模型)
    ↓
Task 2: 审批门控纯函数 (依赖 Task 1 的类型)
    ↓
Task 3: 提案状态机 (依赖 Task 1 + 2)
    ↓
Task 4: ModelRouter.create_agent() (依赖 PydanticAI，补全阶段 2 缺失)
    ↓
Task 5: 分析 Agent (依赖 Task 1 + 4)
    ↓
Task 6: 提案 Agent (依赖 Task 1 + 4 + 5)
    ↓
Task 7: 验证 Agent (依赖 Task 1 + 4 + 6)
    ↓
Task 8: 闭环编排器 (依赖 Task 3 + 5 + 6 + 7)
```

---

## Task 1: Agent 输出类型定义

> 定义三个 Agent 的结构化输出模型和提案状态枚举。纯 Pydantic，零外部依赖。

**文件：**
- 创建: `src/noesis_agent/agent/roles/__init__.py`（重新导出）
- 创建: `src/noesis_agent/agent/roles/types.py`
- 创建: `tests/unit/test_agent_types.py`

### Step 1: 写测试

```python
# tests/unit/test_agent_types.py
import pytest
from noesis_agent.agent.roles.types import (
    AnalysisReport,
    PerformanceSummary,
    Proposal,
    ProposalStatus,
    ValidationReport,
    BacktestComparison,
    GateResult,
)


class TestProposalStatus:
    def test_initial_states(self):
        assert ProposalStatus.DRAFT == "draft"
        assert ProposalStatus.GATE_1_MEMORY == "gate_1_memory"
        assert ProposalStatus.REJECTED == "rejected"
        assert ProposalStatus.GRADUATED == "graduated"

    def test_all_states_in_pipeline(self):
        """验证完整状态机路径"""
        pipeline = [
            ProposalStatus.DRAFT,
            ProposalStatus.GATE_1_MEMORY,
            ProposalStatus.GATE_2_BACKTEST,
            ProposalStatus.GATE_3_WALKFORWARD,
            ProposalStatus.PENDING_APPROVAL,
            ProposalStatus.APPROVED,
            ProposalStatus.TESTNET_DEPLOYED,
            ProposalStatus.GATE_4_MIN_PERIOD,
            ProposalStatus.GATE_5_PERFORMANCE,
            ProposalStatus.PENDING_LIVE_APPROVAL,
            ProposalStatus.LIVE_DEPLOYED,
            ProposalStatus.MONITORING,
        ]
        assert len(pipeline) == 12


class TestAnalysisReport:
    def test_create(self):
        report = AnalysisReport(
            period="2025-01",
            strategy_id="sma_cross",
            performance=PerformanceSummary(
                total_return_pct=5.2,
                max_drawdown_pct=3.1,
                win_rate_pct=62.0,
                trade_count=45,
            ),
            market_regime="trending",
            strengths=["趋势跟踪效果好"],
            weaknesses=["震荡市连续止损"],
            patterns=["均线交叉在4h级别信号更稳定"],
            recommendations=["考虑增加确认柱数"],
        )
        assert report.strategy_id == "sma_cross"
        assert report.performance.trade_count == 45

    def test_frozen(self):
        report = AnalysisReport(
            period="2025-01",
            strategy_id="test",
            performance=PerformanceSummary(
                total_return_pct=0, max_drawdown_pct=0, win_rate_pct=0, trade_count=0,
            ),
        )
        with pytest.raises((AttributeError, TypeError, ValueError)):
            report.strategy_id = "other"


class TestProposal:
    def test_create_parameter_change(self):
        proposal = Proposal(
            strategy_id="sma_cross",
            analysis_report_id=1,
            change_type="parameter",
            parameter_changes={"fast_period": {"old": 5, "new": 8}},
            rationale="回测显示 8 周期均线在趋势市中表现更好",
            expected_impact="预计夏普比率提升 15%",
        )
        assert proposal.change_type == "parameter"
        assert proposal.status == ProposalStatus.DRAFT

    def test_create_code_change(self):
        proposal = Proposal(
            strategy_id="sma_cross",
            analysis_report_id=1,
            change_type="code",
            code_changes="def on_bar(self, data, position, account):\n    # 新增 RSI 过滤\n    ...",
            rationale="加入 RSI 过滤避免震荡市虚假信号",
            expected_impact="减少 30% 的假信号交易",
        )
        assert proposal.change_type == "code"


class TestValidationReport:
    def test_create(self):
        report = ValidationReport(
            proposal_id="prop_001",
            baseline=BacktestComparison(
                total_return_pct=5.0, max_drawdown_pct=3.0, win_rate_pct=60.0,
                trade_count=40, sharpe_ratio=1.2,
            ),
            proposed=BacktestComparison(
                total_return_pct=7.0, max_drawdown_pct=2.5, win_rate_pct=65.0,
                trade_count=35, sharpe_ratio=1.5,
            ),
            walk_forward_decay_pct=15.0,
            verdict="pass",
            concerns=[],
        )
        assert report.verdict == "pass"
        assert report.walk_forward_decay_pct == 15.0


class TestGateResult:
    def test_pass(self):
        result = GateResult(gate_name="gate_1_memory", passed=True, reason="无历史失败命中")
        assert result.passed is True

    def test_fail(self):
        result = GateResult(gate_name="gate_2_backtest", passed=False, reason="夏普下降 20%")
        assert result.passed is False
```

### Step 2: 运行测试确认失败

运行: `uv run pytest tests/unit/test_agent_types.py -v`
预期: FAIL — `ModuleNotFoundError`

### Step 3: 实现类型

```python
# src/noesis_agent/agent/roles/types.py
from __future__ import annotations

from enum import Enum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from noesis_agent.core.models import generate_run_id


class ProposalStatus(str, Enum):
    DRAFT = "draft"
    GATE_1_MEMORY = "gate_1_memory"
    GATE_2_BACKTEST = "gate_2_backtest"
    GATE_3_WALKFORWARD = "gate_3_walkforward"
    PENDING_APPROVAL = "pending_approval"
    APPROVED = "approved"
    TESTNET_DEPLOYED = "testnet_deployed"
    GATE_4_MIN_PERIOD = "gate_4_min_period"
    GATE_5_PERFORMANCE = "gate_5_performance"
    PENDING_LIVE_APPROVAL = "pending_live_approval"
    LIVE_DEPLOYED = "live_deployed"
    MONITORING = "monitoring"
    REJECTED = "rejected"
    AUTO_ROLLBACK = "auto_rollback"
    GRADUATED = "graduated"


class PerformanceSummary(BaseModel):
    model_config = ConfigDict(frozen=True)
    total_return_pct: float
    max_drawdown_pct: float
    win_rate_pct: float
    trade_count: int
    sharpe_ratio: float | None = None


class AnalysisReport(BaseModel):
    model_config = ConfigDict(frozen=True)
    period: str
    strategy_id: str
    performance: PerformanceSummary
    market_regime: str = "unknown"
    strengths: list[str] = Field(default_factory=list)
    weaknesses: list[str] = Field(default_factory=list)
    patterns: list[str] = Field(default_factory=list)
    recommendations: list[str] = Field(default_factory=list)


class Proposal(BaseModel):
    model_config = ConfigDict(frozen=True)
    proposal_id: str = Field(default_factory=lambda: generate_run_id("prop"))
    strategy_id: str
    analysis_report_id: int
    change_type: str  # "parameter" | "code" | "trade_management"
    parameter_changes: dict[str, Any] = Field(default_factory=dict)
    code_changes: str = ""
    trade_management_changes: dict[str, Any] = Field(default_factory=dict)
    rationale: str = ""
    expected_impact: str = ""
    status: ProposalStatus = ProposalStatus.DRAFT


class BacktestComparison(BaseModel):
    model_config = ConfigDict(frozen=True)
    total_return_pct: float
    max_drawdown_pct: float
    win_rate_pct: float
    trade_count: int
    sharpe_ratio: float | None = None


class ValidationReport(BaseModel):
    model_config = ConfigDict(frozen=True)
    proposal_id: str
    baseline: BacktestComparison
    proposed: BacktestComparison
    walk_forward_decay_pct: float = 0.0
    verdict: str = "pending"  # "pass" | "fail" | "marginal"
    concerns: list[str] = Field(default_factory=list)


class GateResult(BaseModel):
    model_config = ConfigDict(frozen=True)
    gate_name: str
    passed: bool
    reason: str = ""
    details: dict[str, Any] = Field(default_factory=dict)
```

### Step 4: 运行测试 + Lint

运行: `uv run pytest tests/unit/test_agent_types.py -v`
预期: 全部 PASSED

运行: `uv run ruff check src/noesis_agent/agent/roles/ tests/unit/test_agent_types.py`
预期: 零违规

### Step 5: 提交

```bash
git add src/noesis_agent/agent/roles/ tests/unit/test_agent_types.py
git commit -m "feat(agent): add structured output types for analysis, proposal, and validation"
```

---

## Task 2: 审批门控纯函数

> 5 道自动门控，全是纯函数。不依赖 LLM，完美的 TDD 目标。

**文件：**
- 创建: `src/noesis_agent/agent/gates.py`
- 创建: `tests/unit/test_gates.py`

### Step 1: 写测试

```python
# tests/unit/test_gates.py
from noesis_agent.agent.gates import (
    gate_1_failure_memory,
    gate_2_backtest_comparison,
    gate_3_walk_forward,
    gate_4_testnet_period,
    gate_5_testnet_performance,
)
from noesis_agent.agent.roles.types import BacktestComparison, GateResult


class TestGate1FailureMemory:
    def test_no_failures_passes(self):
        result = gate_1_failure_memory(
            strategy_id="sma_cross",
            change_type="parameter",
            failure_records=[],
        )
        assert result.passed is True

    def test_matching_failure_blocks(self):
        failures = [{"strategy_id": "sma_cross", "category": "parameter", "title": "过拟合"}]
        result = gate_1_failure_memory(
            strategy_id="sma_cross",
            change_type="parameter",
            failure_records=failures,
        )
        assert result.passed is False
        assert "历史失败" in result.reason

    def test_different_strategy_passes(self):
        failures = [{"strategy_id": "ema_rsi", "category": "parameter", "title": "过拟合"}]
        result = gate_1_failure_memory(
            strategy_id="sma_cross",
            change_type="parameter",
            failure_records=failures,
        )
        assert result.passed is True


class TestGate2BacktestComparison:
    def test_improvement_passes(self):
        baseline = BacktestComparison(total_return_pct=5.0, max_drawdown_pct=3.0, win_rate_pct=60.0, trade_count=40)
        proposed = BacktestComparison(total_return_pct=7.0, max_drawdown_pct=2.5, win_rate_pct=65.0, trade_count=35)
        result = gate_2_backtest_comparison(baseline, proposed)
        assert result.passed is True

    def test_return_degradation_fails(self):
        baseline = BacktestComparison(total_return_pct=5.0, max_drawdown_pct=3.0, win_rate_pct=60.0, trade_count=40)
        proposed = BacktestComparison(total_return_pct=2.0, max_drawdown_pct=3.0, win_rate_pct=60.0, trade_count=40)
        result = gate_2_backtest_comparison(baseline, proposed)
        assert result.passed is False

    def test_drawdown_increase_fails(self):
        baseline = BacktestComparison(total_return_pct=5.0, max_drawdown_pct=3.0, win_rate_pct=60.0, trade_count=40)
        proposed = BacktestComparison(total_return_pct=5.0, max_drawdown_pct=6.0, win_rate_pct=60.0, trade_count=40)
        result = gate_2_backtest_comparison(baseline, proposed)
        assert result.passed is False


class TestGate3WalkForward:
    def test_low_decay_passes(self):
        result = gate_3_walk_forward(decay_pct=15.0, threshold=30.0)
        assert result.passed is True

    def test_high_decay_fails(self):
        result = gate_3_walk_forward(decay_pct=45.0, threshold=30.0)
        assert result.passed is False

    def test_exact_threshold_passes(self):
        result = gate_3_walk_forward(decay_pct=30.0, threshold=30.0)
        assert result.passed is True


class TestGate4TestnetPeriod:
    def test_meets_requirements(self):
        result = gate_4_testnet_period(days_running=15, trade_count=25, min_days=14, min_trades=20)
        assert result.passed is True

    def test_insufficient_days(self):
        result = gate_4_testnet_period(days_running=7, trade_count=25, min_days=14, min_trades=20)
        assert result.passed is False

    def test_insufficient_trades(self):
        result = gate_4_testnet_period(days_running=15, trade_count=10, min_days=14, min_trades=20)
        assert result.passed is False


class TestGate5TestnetPerformance:
    def test_within_tolerance(self):
        result = gate_5_testnet_performance(actual_return_pct=4.0, expected_return_pct=5.0, tolerance=-0.5)
        assert result.passed is True

    def test_exceeds_tolerance(self):
        result = gate_5_testnet_performance(actual_return_pct=1.0, expected_return_pct=5.0, tolerance=-0.5)
        assert result.passed is False

    def test_better_than_expected(self):
        result = gate_5_testnet_performance(actual_return_pct=8.0, expected_return_pct=5.0, tolerance=-0.5)
        assert result.passed is True
```

### Step 2: 运行测试确认失败

运行: `uv run pytest tests/unit/test_gates.py -v`
预期: FAIL — `ModuleNotFoundError`

### Step 3: 实现门控函数

```python
# src/noesis_agent/agent/gates.py
from __future__ import annotations

from typing import Any

from noesis_agent.agent.roles.types import BacktestComparison, GateResult


def gate_1_failure_memory(
    *,
    strategy_id: str,
    change_type: str,
    failure_records: list[dict[str, Any]],
) -> GateResult:
    """Gate 1: 检查失败记忆库，命中同策略+同类型历史失败则拒绝。"""
    matching = [
        f for f in failure_records
        if f.get("strategy_id") == strategy_id and f.get("category") == change_type
    ]
    if matching:
        titles = ", ".join(f.get("title", "未知") for f in matching[:3])
        return GateResult(
            gate_name="gate_1_memory",
            passed=False,
            reason=f"命中 {len(matching)} 条历史失败记录: {titles}",
            details={"matching_count": len(matching)},
        )
    return GateResult(gate_name="gate_1_memory", passed=True, reason="无历史失败命中")


def gate_2_backtest_comparison(
    baseline: BacktestComparison,
    proposed: BacktestComparison,
) -> GateResult:
    """Gate 2: 新版本回测不能劣于旧版本。"""
    reasons = []
    if proposed.total_return_pct < baseline.total_return_pct:
        reasons.append(f"收益下降: {baseline.total_return_pct:.1f}% → {proposed.total_return_pct:.1f}%")
    if proposed.max_drawdown_pct > baseline.max_drawdown_pct * 1.5:
        reasons.append(f"回撤增大: {baseline.max_drawdown_pct:.1f}% → {proposed.max_drawdown_pct:.1f}%")
    if reasons:
        return GateResult(gate_name="gate_2_backtest", passed=False, reason="; ".join(reasons))
    return GateResult(gate_name="gate_2_backtest", passed=True, reason="关键指标不劣于旧版本")


def gate_3_walk_forward(
    *,
    decay_pct: float,
    threshold: float = 30.0,
) -> GateResult:
    """Gate 3: Walk-forward 样本外衰减不超过阈值。"""
    if decay_pct > threshold:
        return GateResult(
            gate_name="gate_3_walkforward",
            passed=False,
            reason=f"样本外衰减 {decay_pct:.1f}% 超过阈值 {threshold:.1f}%",
        )
    return GateResult(gate_name="gate_3_walkforward", passed=True, reason=f"衰减 {decay_pct:.1f}% 在可接受范围内")


def gate_4_testnet_period(
    *,
    days_running: int,
    trade_count: int,
    min_days: int = 14,
    min_trades: int = 20,
) -> GateResult:
    """Gate 4: 测试网运行天数和交易笔数达标。"""
    reasons = []
    if days_running < min_days:
        reasons.append(f"运行天数 {days_running} 未达最低要求 {min_days}")
    if trade_count < min_trades:
        reasons.append(f"交易笔数 {trade_count} 未达最低要求 {min_trades}")
    if reasons:
        return GateResult(gate_name="gate_4_min_period", passed=False, reason="; ".join(reasons))
    return GateResult(gate_name="gate_4_min_period", passed=True, reason="测试网运行达标")


def gate_5_testnet_performance(
    *,
    actual_return_pct: float,
    expected_return_pct: float,
    tolerance: float = -0.5,
) -> GateResult:
    """Gate 5: 测试网实际表现不显著偏离回测预期。tolerance=-0.5 表示允许偏离到预期的 -50%。"""
    if expected_return_pct == 0:
        return GateResult(gate_name="gate_5_performance", passed=True, reason="预期收益为零，跳过检查")
    deviation = (actual_return_pct - expected_return_pct) / abs(expected_return_pct)
    if deviation < tolerance:
        return GateResult(
            gate_name="gate_5_performance",
            passed=False,
            reason=f"实际收益 {actual_return_pct:.1f}% 偏离预期 {expected_return_pct:.1f}% 达 {deviation:.0%}",
        )
    return GateResult(gate_name="gate_5_performance", passed=True, reason="表现在可接受范围内")
```

### Step 4: 运行测试 + Lint

运行: `uv run pytest tests/unit/test_gates.py -v`
预期: 全部 PASSED（12 tests）

运行: `uv run ruff check src/noesis_agent/agent/gates.py tests/unit/test_gates.py`
预期: 零违规

### Step 5: 提交

```bash
git add src/noesis_agent/agent/gates.py tests/unit/test_gates.py
git commit -m "feat(agent): add 5 approval gate pure functions with TDD coverage"
```

---

## Task 3: 提案状态机

> 管理提案从 draft 到 graduated/rejected 的完整生命周期。纯 Python，不依赖 LLM。

**文件：**
- 创建: `src/noesis_agent/agent/proposal_manager.py`
- 创建: `tests/unit/test_proposal_manager.py`

### Step 1: 写测试

测试提案状态机的合法/非法转换：
- draft → gate_1_memory（合法）
- draft → approved（非法，跳过门控）
- gate_3_walkforward → pending_approval（合法）
- pending_approval → approved（合法，人工审批通过）
- pending_approval → rejected（合法，人工拒绝）
- 任意状态 → rejected（合法，总可以拒绝）
- approved → draft（非法，不能回退）

测试 ProposalManager：
- advance_proposal() 推进状态
- reject_proposal() 拒绝提案并记录失败记忆
- get_pending_approvals() 返回等待审批的提案

### Step 2: 实现

状态机定义合法转换表：
```python
VALID_TRANSITIONS: dict[ProposalStatus, list[ProposalStatus]] = {
    ProposalStatus.DRAFT: [ProposalStatus.GATE_1_MEMORY, ProposalStatus.REJECTED],
    ProposalStatus.GATE_1_MEMORY: [ProposalStatus.GATE_2_BACKTEST, ProposalStatus.REJECTED],
    # ... 完整映射
}
```

ProposalManager 维护提案生命周期，每次状态变更存入 MemoryStore。

### Step 3: 运行测试 + Lint

运行: `uv run pytest tests/unit/test_proposal_manager.py -v`
预期: 全部 PASSED

运行: `uv run ruff check src/noesis_agent/agent/proposal_manager.py`
预期: 零违规

### Step 4: 提交

```bash
git add src/noesis_agent/agent/proposal_manager.py tests/unit/test_proposal_manager.py
git commit -m "feat(agent): add proposal state machine with lifecycle management"
```

---

## Task 4: ModelRouter.create_agent() — 补全 PydanticAI 集成

> 阶段 2 的 ModelRouter 只做路由查询。现在补上 `create_agent()` 方法，用 PydanticAI Agent 类实例化。

**文件：**
- 修改: `src/noesis_agent/agent/models.py`
- 修改: `tests/unit/test_agent_models.py`

### Step 1: 写测试

```python
# 追加到 tests/unit/test_agent_models.py
from pydantic_ai.models.test import TestModel
from pydantic import BaseModel

class SimpleOutput(BaseModel):
    answer: str

class TestCreateAgent:
    def test_create_agent_returns_pydantic_agent(self):
        roles = {"analyst": AgentRoleConfig(model="test", system_prompt="你是分析师")}
        router = ModelRouter(roles)
        agent = router.create_agent("analyst", output_type=SimpleOutput)
        assert agent is not None

    def test_create_agent_with_fallback(self):
        roles = {"analyst": AgentRoleConfig(model="test", fallback="test", system_prompt="你是分析师")}
        router = ModelRouter(roles)
        agent = router.create_agent("analyst", output_type=SimpleOutput)
        assert agent is not None

    def test_create_agent_unknown_role_raises(self):
        router = ModelRouter({})
        with pytest.raises(ValueError, match="Unknown agent role"):
            router.create_agent("nonexistent")

    def test_agent_can_run_with_test_model(self):
        """用 PydanticAI TestModel 验证 agent 可以产出结构化输出"""
        roles = {"analyst": AgentRoleConfig(model="test", system_prompt="你是分析师")}
        router = ModelRouter(roles)
        agent = router.create_agent("analyst", output_type=SimpleOutput)
        # TestModel 自动填充 structured output
        result = agent.run_sync("测试", model=TestModel())
        assert isinstance(result.output, SimpleOutput)
```

### Step 2: 实现 create_agent

```python
# 追加到 src/noesis_agent/agent/models.py
from pydantic_ai import Agent

def create_agent(
    self,
    role: str,
    *,
    output_type: type | None = None,
    tools: list | None = None,
    deps_type: type | None = None,
) -> Agent:
    """创建已配置好模型的 PydanticAI Agent"""
    config = self.get_role_config(role)
    model = config.model
    if config.fallback:
        from pydantic_ai.models.fallback import FallbackModel
        model = FallbackModel(model, config.fallback)

    kwargs = {}
    if output_type is not None:
        kwargs["output_type"] = output_type
    if deps_type is not None:
        kwargs["deps_type"] = deps_type

    return Agent(
        model,
        instructions=config.system_prompt or None,
        tools=tools or [],
        **kwargs,
    )
```

### Step 3: 运行测试 + Lint

运行: `uv run pytest tests/unit/test_agent_models.py -v`
预期: 全部 PASSED

运行: `uv run ruff check src/noesis_agent/agent/models.py`
预期: 零违规

### Step 4: 提交

```bash
git add src/noesis_agent/agent/models.py tests/unit/test_agent_models.py
git commit -m "feat(agent): add ModelRouter.create_agent() with PydanticAI integration"
```

---

## Task 5: 分析 Agent

> 第一个真正的 AI Agent。输入交易记录 + 市场数据，输出结构化 AnalysisReport。

**文件：**
- 创建: `src/noesis_agent/agent/roles/analyst.py`
- 创建: `tests/unit/test_analyst_agent.py`

### 设计

```python
# src/noesis_agent/agent/roles/analyst.py
from pydantic_ai import Agent, RunContext
from noesis_agent.agent.roles.types import AnalysisReport, PerformanceSummary

@dataclass
class AnalystDeps:
    memory_store: MemoryStore
    skill_registry: SkillRegistry

ANALYST_INSTRUCTIONS = """你是一个加密货币策略分析师。
你的任务是分析策略在指定周期内的交易表现，生成结构化分析报告。

分析维度：
1. 绩效概览（收益率、回撤、胜率、交易频率）
2. 市场环境判断（趋势/震荡/混合）
3. 策略优势（哪些环境下表现好）
4. 策略弱点（哪些环境下表现差）
5. 发现的规律（时间规律、品种规律等）
6. 改进建议（具体可操作的方向）

输出必须是中文。用数据支撑每个观点。"""

def create_analyst_agent(router: ModelRouter) -> Agent[AnalystDeps, AnalysisReport]:
    agent = router.create_agent("analyst", output_type=AnalysisReport, deps_type=AnalystDeps)
    agent.instructions = ANALYST_INSTRUCTIONS

    @agent.tool
    async def get_trade_records(ctx: RunContext[AnalystDeps], period: str, strategy_id: str) -> str:
        """获取指定周期的交易记录摘要"""
        # 从 memory_store 查询
        records = ctx.deps.memory_store.get_reports(period=period)
        return str([r.content for r in records[:10]])

    @agent.tool
    async def get_backtest_summary(ctx: RunContext[AnalystDeps], strategy_id: str) -> str:
        """获取策略最近一次回测的绩效摘要"""
        if ctx.deps.skill_registry.has_skill("run_backtest"):
            return "回测技能可用但未在此上下文中执行"
        return "回测技能不可用"

    return agent
```

### 测试

用 `pydantic_ai.models.test.TestModel` mock LLM 调用。验证：
- Agent 创建成功
- 工具注册正确
- TestModel 能产出 AnalysisReport 结构化输出
- 报告存入 MemoryStore

### Step 1: 写测试 + Step 2: 实现 + Step 3: 运行测试 + Lint

运行: `uv run pytest tests/unit/test_analyst_agent.py -v`
预期: 全部 PASSED

运行: `uv run ruff check src/noesis_agent/agent/roles/analyst.py`
预期: 零违规

### Step 4: 提交

```bash
git add src/noesis_agent/agent/roles/analyst.py tests/unit/test_analyst_agent.py
git commit -m "feat(agent): add analyst agent with PydanticAI structured output"
```

---

## Task 6: 提案 Agent

> 输入 AnalysisReport + 策略源码，输出 Proposal（含参数变更或代码 diff）。

**文件：**
- 创建: `src/noesis_agent/agent/roles/proposer.py`
- 创建: `tests/unit/test_proposer_agent.py`

### 设计

```python
PROPOSER_INSTRUCTIONS = """你是一个加密货币策略改进师。
基于分析报告的发现，提出具体的策略改进提案。

提案类型：
1. parameter — 调整现有参数（如均线周期、止损比例）
2. code — 修改策略逻辑（如增加过滤条件、改变入场条件）
3. trade_management — 调整交易管理（如止损方式、持仓时间限制）

每个提案必须：
- 明确指出改什么、为什么改
- 给出预期效果
- 基于分析报告中的具体发现，不要凭空想象
- 一个提案只改一件事（最小变更原则）

输出必须是中文。"""
```

工具：
- `read_strategy_source(strategy_id)` — 读取策略 Python 源码
- `query_failure_memory(strategy_id, change_type)` — 查询历史失败（提案前强制）

### 测试

用 TestModel 验证 Proposal 结构化输出。

### Step 1-4: 同 Task 5 模式

**提交:** `git commit -m "feat(agent): add proposer agent for strategy improvement proposals"`

---

## Task 7: 验证 Agent

> 输入 Proposal + 历史数据，运行新旧版本回测对比，输出 ValidationReport。

**文件：**
- 创建: `src/noesis_agent/agent/roles/validator.py`
- 创建: `tests/unit/test_validator_agent.py`

### 设计

```python
VALIDATOR_INSTRUCTIONS = """你是一个提案验证员。
你的任务是客观评估改进提案的效果，通过回测对比和 walk-forward 验证给出判断。

验证流程：
1. 用当前参数运行基准回测
2. 用提案参数运行改进回测
3. 对比关键指标（收益率、回撤、胜率）
4. 运行 walk-forward 验证（样本内训练 + 样本外测试）
5. 计算样本外衰减率
6. 给出 pass / fail / marginal 判定

判定标准：
- pass: 所有指标不劣于基准 AND 衰减率 < 30%
- fail: 关键指标明显劣化 OR 衰减率 > 50%
- marginal: 介于两者之间，需要人工判断

输出必须客观、数据驱动。列出所有风险点。"""
```

工具：
- `run_backtest(strategy_id, params)` — 调用回测引擎
- `run_walk_forward(strategy_id, params, split_ratio)` — 分割数据做 walk-forward

### 测试

用 TestModel + mock backtest 结果验证 ValidationReport 输出。

### Step 1-4: 同 Task 5 模式

**提交:** `git commit -m "feat(agent): add validator agent for proposal verification with backtest comparison"`

---

## Task 8: 闭环编排器

> 把分析 → 提案 → 门控 → 验证 → 审批串联成完整闭环。

**文件：**
- 创建: `src/noesis_agent/agent/orchestrator.py`
- 创建: `tests/unit/test_orchestrator.py`

### 设计

```python
class AgentOrchestrator:
    """编排分析 → 提案 → 验证的完整闭环。"""

    def __init__(
        self,
        router: ModelRouter,
        memory: MemoryStore,
        proposal_manager: ProposalManager,
        skill_registry: SkillRegistry,
    ): ...

    async def run_analysis_cycle(
        self,
        strategy_id: str,
        period: str,
    ) -> AnalysisReport:
        """运行分析 Agent，存储报告到记忆系统。"""

    async def run_proposal_cycle(
        self,
        analysis_report: AnalysisReport,
        analysis_report_id: int,
    ) -> Proposal:
        """运行提案 Agent，创建提案。"""

    async def run_validation_cycle(
        self,
        proposal: Proposal,
    ) -> ValidationReport:
        """运行验证 Agent，产出验证报告。"""

    async def run_gate_sequence(
        self,
        proposal: Proposal,
        validation_report: ValidationReport,
    ) -> list[GateResult]:
        """依次运行 Gate 1-3，返回所有结果。"""

    async def run_full_cycle(
        self,
        strategy_id: str,
        period: str,
    ) -> dict:
        """完整闭环: 分析 → 提案 → Gate 1 → 验证 → Gate 2-3 → 等待审批。
        返回 {analysis, proposal, validation, gates, final_status}。"""
```

### 测试

用 TestModel mock 所有 Agent 调用，验证完整闭环流程：
- 分析 → 产出 AnalysisReport
- 提案 → 产出 Proposal (status=DRAFT)
- Gate 1 通过 → 状态推进
- 验证 → 产出 ValidationReport
- Gate 2-3 通过 → 状态变为 PENDING_APPROVAL
- Gate 2-3 失败 → 状态变为 REJECTED

### Step 1: 写测试 + Step 2: 实现 + Step 3: 运行测试 + Lint

运行: `uv run pytest tests/unit/test_orchestrator.py -v`
预期: 全部 PASSED

运行: `uv run ruff check src/noesis_agent/agent/orchestrator.py`
预期: 零违规

### Step 4: 提交

```bash
git add src/noesis_agent/agent/orchestrator.py tests/unit/test_orchestrator.py
git commit -m "feat(agent): add orchestrator for analysis → proposal → validation closed loop"
```

---

## 验收标准

1. `uv run pytest tests/ -x` — 零失败
2. `uv run ruff check src/ tests/` — 零违规
3. 不需要任何 LLM API key 即可跑完全部测试（用 PydanticAI TestModel）
4. 不需要任何交易所 API key
5. 完整闭环可测试：分析 → 提案 → 门控 → 验证 → 状态推进到 PENDING_APPROVAL
6. 门控拒绝路径可测试：失败记忆命中 → REJECTED
7. 所有 Agent 输出都是 Pydantic 结构化模型（可序列化、可验证）
