# Changelog

本文件记录 Noesis Agent 的版本更新历史。

## [0.2.0] — 2026-03-23

### 量化基础设施

- **因子库**: 新增 `quant/factors/` 模块，7 个内置因子（动量/ATR/波动率%/成交量Z-Score/方向效率/均线斜率）
- **因子分析**: IC/IR 评估框架，判断因子预测力和稳定性
- **因子增强策略**: R-breaker 支持基于因子值的信号过滤（如方向效率 < 0.15 时暂停交易）

### 自动化运行

- **月度批量协调器**: `noesis batch run --period 2026-03`，自动遍历所有 active 策略
- **策略目录**: 从 `config/strategies/*.toml` 自动发现和加载策略
- **定期数据采集**: Binance 快照数据采集器（OI/多空比/资金费率/主动买卖比）

### 基础设施

- **日志系统**: 结构化 JSONL 日志 + Agent 调用追踪（记录 prompt tokens/延迟/状态）+ 审批操作审计
- **告警系统**: 分级告警 + 可插拔通道（console/log）+ 告警冷却收敛
- **数据存储**: Parquet 列式存储，分层目录（market/factors/snapshots），向后兼容 CSV
- **Prompt 版本管理**: Agent prompt 外部化为 `config/prompts/{role}/v1.md` + `meta.toml`

### 模型与认证

- **模型管理**: `config/models.toml` 注册表 + `noesis models list/test` 连通性测试
- **Agent 模型升级**: 分析师 → Claude Opus 4.6，改进师 → GPT-5.2
- **Maker/Taker 费率分离**: BrokerSimulator 支持分开的 maker/taker 费率

### 策略

- **R-breaker Limit 模式**: 支持限价单入场（Maker 零手续费）
- **市场环境分类器**: ATR + 均线斜率 + 方向效率规则引擎（不用 LLM）

## [0.1.0] — 2026-03-23

### 核心系统

- **阶段 1 基础解耦**: 核心类型（Pydantic v2）、TOML 配置系统、数据层（MarketDataAdapter Protocol）、Binance 适配器、执行层协议、风控纯函数、策略基类（StrategyBase ABC）、回测引擎、优化引擎
- **阶段 2 Agent 基础设施**: APScheduler 调度器、SQLite + FTS5 记忆系统、模型路由（ModelRouter）、技能注册表
- **阶段 3 核心 Agent**: 分析/提案/验证 Agent（PydanticAI 结构化输出）、5 道审批门控纯函数、提案状态机（15 个状态）、闭环编排器

### CLI

- 9 个核心命令: analyze/propose/validate/cycle/approve/reject/status/proposals/config show

### 认证

- **OpenAI OAuth**: PKCE 登录流程 + Token 自动刷新 + Codex API 适配（CodexResponsesModel）
- **中转站支持**: 自定义 base_url + api_key_env

### 策略

- **R-breaker**: 经典 R-breaker 加密市场适配，daily + rolling pivot 模式

### 验证

- 端到端 AI 闭环: Claude Opus 分析 → GPT-5.2 提案 → Claude Sonnet 验证 → 门控通过 → 人工审批
- 真实数据回测: BTCUSDT 15m 90天 8640 根 K 线
