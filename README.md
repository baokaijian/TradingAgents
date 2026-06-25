# TradingAgents A/H 自动化交易平台

这是一个基于 [TauricResearch/TradingAgents](https://github.com/TauricResearch/TradingAgents) 改造的 A 股与港股自动化交易工具平台。项目保留 TradingAgents 的多 Agent 研究框架，并在外层新增面向真实交易系统的确定性组件：证券解析、信号标准化、市场规则、账户风控、订单意图和 paper broker。

> 重要声明：本项目是研究与工程原型，不构成投资建议。当前默认目标是 `research_only` 与 `paper_trading`，不应直接连接实盘账户自动下单。任何实盘使用都必须经过数据授权、券商授权、合规评估、人工审批、风控灰度和完整审计。

## 平台定位

原始 TradingAgents 擅长让多个 LLM Agent 扮演分析师、研究员、交易员、风险经理和组合经理，生成结构化研究结论。本平台在此基础上增加交易系统所需的确定性边界：

- LLM 负责研究与解释，不直接下单。
- `SignalNormalizer` 把 Agent 的 Markdown 决策转成强类型 `SignalIntent`。
- `MarketRuleEngine` 检查 A 股/港股交易时段、手数、tick size、A 股涨跌幅和可卖数量。
- `RiskEngine` 检查账户现金、单笔金额、仓位权重、置信度和黑名单。
- `PaperBrokerGateway` 提供内存级仿真成交，先验证策略流程。
- `AHAutoTradingPlatform` 串起“研究结论 -> 信号 -> 规则/风控 -> paper 订单”的 MVP 流程。

详细设计见：

[docs/ah_share_hk_auto_trading_platform_design.md](docs/ah_share_hk_auto_trading_platform_design.md)

## 当前代码结构

```text
tradingagents/              # 原 TradingAgents 多 Agent 研究框架
trading_platform/           # A股/港股自动化交易平台层
  models.py                 # Instrument、SignalIntent、OrderIntent、AccountSnapshot 等领域模型
  instruments.py            # A股/港股证券解析与基础市场属性
  signals.py                # TradingAgents Markdown 决策标准化
  market_rules.py           # A股/港股市场规则检查
  risk.py                   # 确定性账户与组合风控
  platform.py               # 高层 signal-to-paper-order 编排
  brokers/
    paper.py                # 内存级 paper broker
tests/trading_platform/     # 平台层单元测试
docs/                       # 设计文档
```

## MVP 能力

已实现：

- A 股符号解析：`600519.SH`、`000001.SZ`，兼容 `.SS` 输入并规范到 `.SH`。
- 港股符号解析：`700.HK` 自动规范为 `0700.HK`。
- A 股基础规则：100 股手数、0.01 tick、主板 10%、ST 5%、科创/创业板 20%、T+1 可卖数量检查。
- 港股基础规则：每手股数、HKEX 常用 tick size、交易时段、订单类型约束。
- TradingAgents 决策解析：支持 `**Rating**`、`**Action**`、`FINAL TRANSACTION PROPOSAL`、价格目标、入场价、止损、周期。
- 风控：最小置信度、最大单笔金额、最大仓位权重、现金、可卖数量、禁用默认市价单。
- paper broker：基于 quote 的限价成交和账户持仓/现金更新。

尚未实现：

- 实时行情、盘口、逐笔、公告和财务数据生产接入。
- 券商实盘网关。
- 事件驱动回测撮合。
- Web 控制台。
- Stock Connect 额度、港股 VCM/CAS 完整规则、卖空规则、费用税费模型。
- 数据库持久化、审计回放、权限系统。

## 安装

建议使用 Python 3.10+。

```bash
git clone git@github.com:baokaijian/TradingAgents.git
cd TradingAgents
python3.12 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
```

如果只运行原 TradingAgents CLI，需要配置相应 LLM API key。平台层的 paper trading 示例不需要外部 API。

## 快速示例：港股 paper trading

下面示例把组合经理的 Markdown 决策转为信号，经过港股市场规则和风控后，在 paper broker 中成交。

```python
from datetime import datetime
from zoneinfo import ZoneInfo

from trading_platform.models import AccountSnapshot, Currency, Quote, RiskLimits
from trading_platform.platform import AHAutoTradingPlatform

account = AccountSnapshot(
    account_id="paper",
    cash={Currency.HKD: 100_000.0},
    equity=200_000.0,
)

platform = AHAutoTradingPlatform(
    account,
    risk_limits=RiskLimits(
        max_order_notional=50_000.0,
        max_position_weight=0.50,
    ),
)

decision_markdown = """
**Rating**: Buy

**Executive Summary**: Strong setup with controlled risk.

**Price Target**: 390

**Time Horizon**: 1-3 months
"""

quote = Quote(symbol="0700.HK", last=350.0, bid=349.8, ask=350.0)

result = platform.evaluate_markdown_decision(
    decision_markdown,
    symbol="0700.HK",
    quote=quote,
    account_id="paper",
    default_notional=35_000.0,
    as_of=datetime(2026, 6, 25, 10, 0, tzinfo=ZoneInfo("Asia/Hong_Kong")),
)

print(result.validation.accepted)
print(result.order.status if result.order else "NO_ORDER")
print(account.positions["0700.HK"].quantity)
```

## 快速示例：A 股规则拒单

```python
from datetime import datetime
from zoneinfo import ZoneInfo

from trading_platform.instruments import InstrumentResolver
from trading_platform.market_rules import MarketRuleEngine
from trading_platform.models import OrderIntent, OrderSide, OrderType, Quote

instrument = InstrumentResolver().resolve("600519.SH")
order = OrderIntent(
    signal_id="sig",
    account_id="paper",
    symbol=instrument.symbol,
    side=OrderSide.BUY,
    order_type=OrderType.LIMIT,
    quantity=100,
    limit_price=111.0,
)
quote = Quote(symbol=instrument.symbol, last=100.0, previous_close=100.0)

result = MarketRuleEngine().validate_order(
    instrument,
    order,
    quote,
    as_of=datetime(2026, 6, 25, 10, 0, tzinfo=ZoneInfo("Asia/Shanghai")),
)

print(result.accepted)       # False
print(result.issues[0].code) # above_limit_up
```

## 与 TradingAgents 的关系

本项目不是从零重写研究框架，而是采用分层方式：

```text
TradingAgents 多 Agent 研究引擎
        |
        v
PortfolioDecision / TraderProposal Markdown
        |
        v
SignalNormalizer -> SignalIntent
        |
        v
MarketRuleEngine + RiskEngine
        |
        v
OrderIntent -> PaperBrokerGateway
```

后续接入实盘时，原则上只替换 broker gateway 和数据源，不允许绕过 `MarketRuleEngine` 与 `RiskEngine`。

## 运行测试

```bash
python -m pytest tests/trading_platform -q
```

当前开发环境需要 Python 3.10+。如果系统默认 `python3` 是 3.9 或更低，请显式使用 3.10/3.11/3.12。

## 开发路线

近期优先级：

1. 接入 A 股/港股主数据与日线/分钟线数据源。
2. 扩展 TradingAgents 的 A/H 股专用工具：公告、财报、资金流、AH 溢价、停复牌、涨跌停。
3. 增加事件驱动 paper backtest。
4. 持久化 signals、orders、fills、positions 和 audit logs。
5. 增加人工审批队列与 Web 控制台。
6. 接入一个港股 paper/live broker 适配器和一个 A 股模拟 broker 适配器。

## 安全边界

默认安全策略：

- 默认不开实盘。
- 默认禁止市价单。
- 默认 `Hold` 不生成订单。
- 默认任何规则/风控失败都会拒绝订单。
- 默认缺少 A 股 `previous_close` 时不能通过涨跌幅检查。
- 默认 A 股卖出检查 `sellable_quantity`，避免违反 T+1 可卖约束。
- 默认所有实盘能力必须通过独立 broker gateway 显式接入。

## License

本仓库保留原 TradingAgents 项目的开源许可文件。新增平台层代码同仓库许可发布。
