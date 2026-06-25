from datetime import datetime
from zoneinfo import ZoneInfo

from trading_platform.models import (
    AccountSnapshot,
    ApprovalStatus,
    Currency,
    OrderStatus,
    PlatformMode,
    Quote,
    RiskLimits,
)
from trading_platform.platform import AHAutoTradingPlatform
from trading_platform.workflows import PHASE_CAPABILITIES


def _buy_markdown() -> str:
    return "\n".join(
        [
            "**Rating**: Buy",
            "",
            "**Executive Summary**: Controlled paper setup.",
            "",
            "**Price Target**: 390",
        ]
    )


def _hk_quote() -> Quote:
    return Quote(symbol="0700.HK", last=350.0, bid=349.8, ask=350.0)


def _as_of():
    return datetime(2026, 6, 25, 10, 0, tzinfo=ZoneInfo("Asia/Hong_Kong"))


def test_four_phase_capabilities_are_declared():
    assert [capability.mode for capability in PHASE_CAPABILITIES] == [
        PlatformMode.RESEARCH_ONLY,
        PlatformMode.PAPER_TRADING,
        PlatformMode.LIVE_GUARDED,
        PlatformMode.LIVE_AUTO,
    ]


def test_research_only_returns_signal_without_order():
    account = AccountSnapshot(account_id="paper", cash={Currency.HKD: 100_000.0}, equity=200_000.0)
    platform = AHAutoTradingPlatform(account, mode=PlatformMode.RESEARCH_ONLY)

    decision = platform.evaluate_markdown_decision(
        _buy_markdown(),
        symbol="0700.HK",
        quote=_hk_quote(),
        account_id="paper",
        default_notional=35_000.0,
        as_of=_as_of(),
    )

    assert decision.mode == PlatformMode.RESEARCH_ONLY
    assert decision.signal is not None
    assert decision.order_intent is None
    assert decision.order is None


def test_live_guarded_creates_approval_ticket_and_executes_after_approval():
    account = AccountSnapshot(account_id="paper", cash={Currency.HKD: 100_000.0}, equity=200_000.0)
    platform = AHAutoTradingPlatform(
        account,
        mode=PlatformMode.LIVE_GUARDED,
        risk_limits=RiskLimits(max_order_notional=50_000.0, max_position_weight=0.50),
    )

    decision = platform.evaluate_markdown_decision(
        _buy_markdown(),
        symbol="0700.HK",
        quote=_hk_quote(),
        account_id="paper",
        default_notional=35_000.0,
        as_of=_as_of(),
    )

    assert decision.validation.accepted
    assert decision.order is None
    assert decision.approval_ticket is not None
    assert decision.approval_ticket.status == ApprovalStatus.PENDING

    order = platform.approve_and_execute(
        decision.approval_ticket.ticket_id,
        reviewer="risk-manager",
        quote=_hk_quote(),
    )

    assert order.status == OrderStatus.FILLED
    assert platform.approval_queue.get(decision.approval_ticket.ticket_id).status == ApprovalStatus.EXECUTED


def test_live_auto_requires_whitelist_and_auto_switch():
    account = AccountSnapshot(account_id="paper", cash={Currency.HKD: 100_000.0}, equity=200_000.0)
    platform = AHAutoTradingPlatform(
        account,
        mode=PlatformMode.LIVE_AUTO,
        risk_limits=RiskLimits(max_order_notional=50_000.0, max_position_weight=0.50),
    )

    rejected = platform.evaluate_markdown_decision(
        _buy_markdown(),
        symbol="0700.HK",
        quote=_hk_quote(),
        account_id="paper",
        default_notional=10_000.0,
        as_of=_as_of(),
    )

    assert not rejected.validation.accepted
    assert {issue.code for issue in rejected.validation.issues} == {
        "live_auto_disabled",
        "auto_symbol_not_allowed",
        "auto_notional_limit",
    }

    guarded = AHAutoTradingPlatform(
        account,
        mode=PlatformMode.LIVE_AUTO,
        risk_limits=RiskLimits(
            max_order_notional=50_000.0,
            max_position_weight=0.50,
            auto_trade_enabled=True,
            auto_trade_symbols=frozenset({"0700.HK"}),
            max_auto_order_notional=40_000.0,
        ),
    )
    accepted = guarded.evaluate_markdown_decision(
        _buy_markdown(),
        symbol="0700.HK",
        quote=_hk_quote(),
        account_id="paper",
        default_notional=10_000.0,
        as_of=_as_of(),
    )

    assert accepted.validation.accepted
    assert accepted.order is not None
    assert accepted.order.status == OrderStatus.FILLED
