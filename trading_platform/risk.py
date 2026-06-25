"""Deterministic account and portfolio risk controls."""

from __future__ import annotations

from trading_platform.models import (
    AccountSnapshot,
    Instrument,
    OrderIntent,
    OrderSide,
    OrderType,
    Quote,
    RiskLimits,
    SignalIntent,
    SignalSide,
    ValidationResult,
)


class RiskEngine:
    """Run non-LLM risk checks before an order can reach a broker gateway."""

    def __init__(self, limits: RiskLimits | None = None):
        self.limits = limits or RiskLimits()

    def validate_signal(self, signal: SignalIntent) -> ValidationResult:
        result = ValidationResult.accept()
        if signal.symbol in self.limits.blocked_symbols:
            result.add_error("blocked_symbol", f"{signal.symbol} is blocked by risk limits.")
        if signal.side != SignalSide.HOLD and signal.conviction < self.limits.min_conviction:
            result.add_error(
                "low_conviction",
                f"Signal conviction {signal.conviction:.2f} is below minimum {self.limits.min_conviction:.2f}.",
            )
        if signal.max_notional is not None and signal.max_notional > self.limits.max_order_notional:
            result.add_error(
                "signal_notional_limit",
                f"Signal max notional {signal.max_notional:.2f} exceeds {self.limits.max_order_notional:.2f}.",
            )
        return result

    def validate_order(
        self,
        signal: SignalIntent,
        order: OrderIntent,
        account: AccountSnapshot,
        instrument: Instrument,
        quote: Quote,
    ) -> ValidationResult:
        result = self.validate_signal(signal)

        if order.order_type == OrderType.MARKET and not self.limits.allow_market_orders:
            result.add_error("market_order_disabled", "Market orders are disabled by default.")

        price = order.limit_price or quote.last
        notional = abs(order.quantity * price)
        if notional > self.limits.max_order_notional:
            result.add_error(
                "order_notional_limit",
                f"Order notional {notional:.2f} exceeds {self.limits.max_order_notional:.2f}.",
            )

        if order.side == OrderSide.BUY:
            available = account.cash_available(instrument.currency)
            if notional > available:
                result.add_error(
                    "insufficient_cash",
                    f"Need {notional:.2f} {instrument.currency.value}, available {available:.2f}.",
                )
            projected_weight = self._projected_weight(account, order.symbol, order.quantity, price)
            if projected_weight > self.limits.max_position_weight:
                result.add_error(
                    "position_weight_limit",
                    f"Projected position weight {projected_weight:.2%} exceeds {self.limits.max_position_weight:.2%}.",
                )
        else:
            position = account.position_for(order.symbol)
            if order.quantity > position.sellable_quantity:
                result.add_error(
                    "risk_sellable_quantity",
                    f"Sell quantity {order.quantity} exceeds sellable {position.sellable_quantity}.",
                )

        return result

    @staticmethod
    def _projected_weight(account: AccountSnapshot, symbol: str, quantity: int, price: float) -> float:
        current = account.position_for(symbol).market_value
        projected_value = current + quantity * price
        if account.equity <= 0:
            return 1.0
        return projected_value / account.equity

