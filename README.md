# Noesis Agent

> 面向加密市场的 AI 交易智能体

一个以真实交易反馈为燃料、以 AI 假设生成和验证闭环为核心的持续适应系统。

## 项目状态

🚧 **架构设计中** — 尚未进入开发阶段。

前身项目：[QPorter Lite](https://github.com/你的用户名/qporter-lite)（v1 原型，已完成基础交易执行链路）

## 定位

- **不是**一个"更好的量化策略"
- **不是**一个"AI 自动赚钱机器"
- **是**一个能从自身交易行为中持续学习的 AI 交易研究与执行系统

## 核心理念

1. AI 是假设生成器，不是事实生成器
2. 研究层与生产层必须分离
3. AI 权限只随证据增长，不随想象增长
4. 系统竞争力在适应速度，不在某个策略
5. 失败记忆和成功记忆同样重要

## 架构概览

```
交互层（Web Agent 控制台 + Telegram）
         ↓
Agent 智能体层（PydanticAI + 自建编排）
  - 策略分析师 / 策略改进师 / 提案验证员
  - 多头辩手 / 空头辩手 / 报告撰写员
  - 环境观察员（规则引擎，不用 LLM）
         ↓
引擎层（v1 演进）
  - 策略仓库（插件式）/ 回测引擎 / 优化引擎
  - 数据层（MarketDataAdapter）/ 特征识别 / 日志审计
         ↓
执行层（v1 演进）
  - ExecutionAdapter（Binance 已有，Hyperliquid 待开发）
  - 统一风控（止损 / 熔断 / 紧急停机）
```

## 技术栈

| 领域 | 选型 |
|---|---|
| 语言 | Python |
| Agent 框架 | PydanticAI + 自建编排层 |
| LLM 路由 | LiteLLM（支持官方 API / 中转站 / 本地模型） |
| Web 后端 | FastAPI |
| Web 前端 | React + Ant Design + Vite |
| 数据库 | SQLite + FTS5 |
| 配置 | TOML |
| 技术指标 | TA-Lib |
| 任务调度 | APScheduler + asyncio |
| 部署 | Docker Compose |

## 文档

- [v2 架构文档](docs/plans/2026-03-21-qporter-v2-architecture.md)
- [策略进化系统探讨记录](docs/plans/2026-03-20-strategy-evolution-system.md)

## License

MIT
