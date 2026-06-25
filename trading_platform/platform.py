"""High-level orchestration for signal-to-paper-order workflows."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from trading_platform.brokers.paper import PaperBrokerGateway
from trading_platform.instruments import InstrumentResolver
from trading_platform.market_rules import MarketRuleEngine
from trading_platform.models import (
    AccountSnapshot,
    ApprovalTicket,
    Order,
    OrderIntent,
    PlatformMode,
    Quote,
    RiskLimits,
    SignalIntent,
    ValidationResult,
)
from trading_platform.risk import RiskEngine
from trading_platform.signals import SignalNormalizer
from trading_platform.workflows import ApprovalQueue, capability_for


@dataclass
class PlatformDecision:
    validation: ValidationResult
    mode: PlatformMode = PlatformMode.PAPER_TRADING
    signal: SignalIntent | None = None
    order_intent: OrderIntent | None = None
    order: Order | None = None
    approval_ticket: ApprovalTicket | None = None


class AHAutoTradingPlatform:
    """TradingAgents markdown -> signal -> phase-specific trading workflow."""

    def __init__(
        self,
        account: AccountSnapshot,
        *,
        risk_limits: RiskLimits | None = None,
        resolver: InstrumentResolver | None = None,
        mode: PlatformMode = PlatformMode.PAPER_TRADING,
        approval_queue: ApprovalQueue | None = None,
    ):
        self.resolver = resolver or InstrumentResolver()
        self.signal_normalizer = SignalNormalizer()
        self.market_rules = MarketRuleEngine()
        self.risk = RiskEngine(risk_limits)
        self.broker = PaperBrokerGateway(account)
        self.mode = mode
        self.approval_queue = approval_queue or ApprovalQueue()

    def evaluate_markdown_decision(
        self,
        markdown: str,
        *,
        symbol: str,
        quote: Quote,
        account_id: str,
        default_notional: float = 10_000.0,
        as_of: datetime | None = None,
        mode: PlatformMode | None = None,
    ) -> PlatformDecision:
        active_mode = mode or self.mode
        capability_for(active_mode)  # Fail fast for unsupported modes.
        instrument = self.resolver.resolve(symbol)
        signal = self.signal_normalizer.from_markdown(
            markdown,
            symbol=instrument.symbol,
            market=instrument.market,
            max_notional=default_notional,
        )

        if active_mode == PlatformMode.RESEARCH_ONLY:
            return PlatformDecision(
                validation=ValidationResult.accept(),
                mode=active_mode,
                signal=signal,
            )

        order_intent = self.signal_normalizer.to_order_intent(
            signal,
            account_id=account_id,
            quote=quote,
            lot_size=instrument.lot_size,
            default_notional=default_notional,
        )
        if order_intent is None:
            return PlatformDecision(
                validation=ValidationResult.accept(),
                mode=active_mode,
                signal=signal,
            )

        account = self.broker.get_account()
        position = account.position_for(instrument.symbol)
        validation = self.market_rules.validate_order(
            instrument,
            order_intent,
            quote,
            position=position,
            as_of=as_of,
        )
        validation.merge(self.risk.validate_order(signal, order_intent, account, instrument, quote))
        if not validation.accepted:
            return PlatformDecision(
                validation=validation,
                mode=active_mode,
                signal=signal,
                order_intent=order_intent,
            )

        if active_mode == PlatformMode.LIVE_GUARDED:
            ticket = self.approval_queue.submit(signal, order_intent, validation)
            return PlatformDecision(
                validation=validation,
                mode=active_mode,
                signal=signal,
                order_intent=order_intent,
                approval_ticket=ticket,
            )

        if active_mode == PlatformMode.LIVE_AUTO:
            auto_validation = self._validate_live_auto(signal, order_intent)
            if not auto_validation.accepted:
                return PlatformDecision(
                    validation=auto_validation,
                    mode=active_mode,
                    signal=signal,
                    order_intent=order_intent,
                )

        order = self.broker.submit_order(order_intent, quote, instrument.currency)
        return PlatformDecision(
            validation=validation,
            mode=active_mode,
            signal=signal,
            order_intent=order_intent,
            order=order,
        )

    def approve_and_execute(
        self,
        ticket_id: str,
        *,
        reviewer: str,
        quote: Quote,
    ) -> Order:
        ticket = self.approval_queue.approve(ticket_id, reviewer=reviewer)
        instrument = self.resolver.resolve(ticket.order_intent.symbol)
        order = self.broker.submit_order(ticket.order_intent, quote, instrument.currency)
        self.approval_queue.mark_executed(ticket_id)
        return order

    def reject_ticket(
        self,
        ticket_id: str,
        *,
        reviewer: str,
        comment: str | None = None,
    ) -> ApprovalTicket:
        return self.approval_queue.reject(ticket_id, reviewer=reviewer, comment=comment)

    def _validate_live_auto(
        self,
        signal: SignalIntent,
        order_intent: OrderIntent,
    ) -> ValidationResult:
        limits = self.risk.limits
        result = ValidationResult.accept()
        if not limits.auto_trade_enabled:
            result.add_error("live_auto_disabled", "Live auto mode requires auto_trade_enabled=True.")
        if signal.symbol not in limits.auto_trade_symbols:
            result.add_error("auto_symbol_not_allowed", f"{signal.symbol} is not in the auto-trade whitelist.")
        if order_intent.notional > limits.max_auto_order_notional:
            result.add_error(
                "auto_notional_limit",
                f"Order notional {order_intent.notional:.2f} exceeds auto cap {limits.max_auto_order_notional:.2f}.",
            )
        return result
