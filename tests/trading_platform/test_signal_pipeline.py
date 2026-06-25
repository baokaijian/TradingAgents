from datetime import datetime
from zoneinfo import ZoneInfo

from trading_platform.models import AccountSnapshot, Currency, OrderStatus, Quote, RiskLimits
from trading_platform.platform import AHAutoTradingPlatform


def test_markdown_decision_can_flow_to_paper_fill():
    account = AccountSnapshot(
        account_id="paper",
        cash={Currency.HKD: 100_000.0},
        equity=200_000.0,
    )
    platform = AHAutoTradingPlatform(
        account,
        risk_limits=RiskLimits(max_order_notional=50_000.0, max_position_weight=0.50),
    )
    markdown = "\n".join(
        [
            "**Rating**: Buy",
            "",
            "**Executive Summary**: Strong setup with controlled risk.",
            "",
            "**Price Target**: 390",
            "",
            "**Time Horizon**: 1-3 months",
        ]
    )
    quote = Quote(symbol="0700.HK", last=350.0, bid=349.8, ask=350.0)

    decision = platform.evaluate_markdown_decision(
        markdown,
        symbol="0700.HK",
        quote=quote,
        account_id="paper",
        default_notional=35_000.0,
        as_of=datetime(2026, 6, 25, 10, 0, tzinfo=ZoneInfo("Asia/Hong_Kong")),
    )

    assert decision.validation.accepted
    assert decision.order is not None
    assert decision.order.status == OrderStatus.FILLED
    assert account.positions["0700.HK"].quantity == 100


def test_hold_decision_does_not_create_order():
    account = AccountSnapshot(account_id="paper", cash={Currency.CNY: 100_000.0}, equity=100_000.0)
    platform = AHAutoTradingPlatform(account)
    quote = Quote(symbol="600519.SH", last=100.0, previous_close=100.0)

    decision = platform.evaluate_markdown_decision(
        "**Rating**: Hold\n\n**Executive Summary**: Wait for confirmation.",
        symbol="600519.SH",
        quote=quote,
        account_id="paper",
        as_of=datetime(2026, 6, 25, 10, 0, tzinfo=ZoneInfo("Asia/Shanghai")),
    )

    assert decision.validation.accepted
    assert decision.order is None

