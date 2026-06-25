"""In-memory paper broker for simulation and guarded development."""

from __future__ import annotations

from datetime import datetime

from trading_platform.models import (
    AccountSnapshot,
    Currency,
    Order,
    OrderIntent,
    OrderSide,
    OrderStatus,
    Position,
    Quote,
    new_id,
)


class PaperBrokerGateway:
    """A deterministic paper gateway that fills limit orders against a quote."""

    def __init__(self, account: AccountSnapshot):
        self.account = account
        self.orders: dict[str, Order] = {}

    def get_account(self) -> AccountSnapshot:
        return self.account

    def get_positions(self) -> list[Position]:
        return list(self.account.positions.values())

    def submit_order(self, intent: OrderIntent, quote: Quote, currency: Currency) -> Order:
        order = Order(order_id=new_id("ord"), intent=intent, status=OrderStatus.SUBMITTED)
        fill_price = self._fill_price(intent, quote)
        if fill_price is None:
            order.status = OrderStatus.SUBMITTED
            order.reject_reason = "Not marketable against the supplied paper quote."
        else:
            self._apply_fill(intent, fill_price, currency)
            order.status = OrderStatus.FILLED
            order.filled_qty = intent.quantity
            order.avg_price = fill_price
        order.updated_at = datetime.utcnow()
        self.orders[order.order_id] = order
        return order

    def cancel_order(self, order_id: str) -> Order:
        order = self.orders[order_id]
        if order.status == OrderStatus.FILLED:
            return order
        order.status = OrderStatus.CANCELLED
        order.updated_at = datetime.utcnow()
        return order

    def _fill_price(self, intent: OrderIntent, quote: Quote) -> float | None:
        if intent.limit_price is None:
            return quote.last
        if intent.side == OrderSide.BUY:
            ask = quote.ask or quote.last
            return ask if intent.limit_price >= ask else None
        bid = quote.bid or quote.last
        return bid if intent.limit_price <= bid else None

    def _apply_fill(self, intent: OrderIntent, price: float, currency: Currency) -> None:
        notional = intent.quantity * price
        position = self.account.position_for(intent.symbol)

        if intent.side == OrderSide.BUY:
            self.account.cash[currency] = self.account.cash_available(currency) - notional
            new_qty = position.quantity + intent.quantity
            total_cost = position.avg_cost * position.quantity + notional
            avg_cost = total_cost / new_qty if new_qty else 0.0
            self.account.positions[intent.symbol] = Position(
                symbol=intent.symbol,
                quantity=new_qty,
                sellable_quantity=position.sellable_quantity,
                avg_cost=avg_cost,
                market_value=new_qty * price,
                currency=currency,
            )
        else:
            new_qty = max(0, position.quantity - intent.quantity)
            self.account.cash[currency] = self.account.cash_available(currency) + notional
            self.account.positions[intent.symbol] = Position(
                symbol=intent.symbol,
                quantity=new_qty,
                sellable_quantity=max(0, position.sellable_quantity - intent.quantity),
                avg_cost=position.avg_cost if new_qty else 0.0,
                market_value=new_qty * price,
                currency=currency,
            )

