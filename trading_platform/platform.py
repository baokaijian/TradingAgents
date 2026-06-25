"""High-level orchestration for signal-to-paper-order workflows."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from trading_platform.brokers.paper import PaperBrokerGateway
from trading_platform.instruments import InstrumentResolver
from trading_platform.market_rules import MarketRuleEngine
from trading_platform.models import (
    AccountSnapshot,
    Order,
    Quote,
    RiskLimits,
    ValidationResult,
)
from trading_platform.risk import RiskEngine
from trading_platform.signals import SignalNormalizer


@dataclass
class PlatformDecision:
    validation: ValidationResult
    order: Order | None = None


class AHAutoTradingPlatform:
    """MVP pipeline: TradingAgents markdown -> signal -> rules/risk -> paper fill."""

    def __init__(
        self,
        account: AccountSnapshot,
        *,
        risk_limits: RiskLimits | None = None,
        resolver: InstrumentResolver | None = None,
    ):
        self.resolver = resolver or InstrumentResolver()
        self.signal_normalizer = SignalNormalizer()
        self.market_rules = MarketRuleEngine()
        self.risk = RiskEngine(risk_limits)
        self.broker = PaperBrokerGateway(account)

    def evaluate_markdown_decision(
        self,
        markdown: str,
        *,
        symbol: str,
        quote: Quote,
        account_id: str,
        default_notional: float = 10_000.0,
        as_of: datetime | None = None,
    ) -> PlatformDecision:
        instrument = self.resolver.resolve(symbol)
        signal = self.signal_normalizer.from_markdown(
            markdown,
            symbol=instrument.symbol,
            market=instrument.market,
            max_notional=default_notional,
        )
        order_intent = self.signal_normalizer.to_order_intent(
            signal,
            account_id=account_id,
            quote=quote,
            lot_size=instrument.lot_size,
            default_notional=default_notional,
        )
        if order_intent is None:
            return PlatformDecision(ValidationResult.accept())

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
            return PlatformDecision(validation)

        order = self.broker.submit_order(order_intent, quote, instrument.currency)
        return PlatformDecision(validation, order)

