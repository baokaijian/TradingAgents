"""Deterministic market rule checks for A-share and Hong Kong orders."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, time
from math import isclose
from zoneinfo import ZoneInfo

from trading_platform.instruments import hk_tick_size
from trading_platform.models import (
    Board,
    Instrument,
    Market,
    OrderIntent,
    OrderSide,
    OrderType,
    Position,
    Quote,
    ValidationResult,
)


@dataclass(frozen=True)
class TradingSession:
    name: str
    start: time
    end: time

    def contains(self, value: time) -> bool:
        return self.start <= value <= self.end


CN_SESSIONS = (
    TradingSession("opening_auction", time(9, 15), time(9, 25)),
    TradingSession("continuous_am", time(9, 30), time(11, 30)),
    TradingSession("continuous_pm", time(13, 0), time(14, 57)),
    TradingSession("closing_auction", time(14, 57), time(15, 0)),
)

HK_SESSIONS = (
    TradingSession("pre_opening", time(9, 0), time(9, 30)),
    TradingSession("continuous_am", time(9, 30), time(12, 0)),
    TradingSession("continuous_pm", time(13, 0), time(16, 0)),
    TradingSession("closing_auction", time(16, 0), time(16, 10)),
)


class MarketRuleEngine:
    """Validate orders against exchange-specific deterministic constraints."""

    def validate_order(
        self,
        instrument: Instrument,
        order: OrderIntent,
        quote: Quote,
        *,
        position: Position | None = None,
        as_of: datetime | None = None,
    ) -> ValidationResult:
        result = ValidationResult.accept()
        as_of = as_of or datetime.now(self._timezone_for(instrument.market))

        if not instrument.tradable:
            result.add_error("instrument_not_tradable", f"{instrument.symbol} is not tradable.")
        if quote.suspended:
            result.add_error("suspended", f"{instrument.symbol} is suspended.")
        if order.quantity <= 0:
            result.add_error("invalid_quantity", "Order quantity must be positive.")

        if not self.is_trading_session(instrument.market, as_of):
            result.add_error("outside_session", f"{instrument.market.value} is outside supported trading sessions.")

        self._validate_lot_size(instrument, order, result)
        self._validate_order_type(instrument, order, result)
        self._validate_tick_size(instrument, order, result)
        self._validate_price_limits(instrument, order, quote, result)
        self._validate_sellable_quantity(instrument, order, position, result)
        return result

    def is_trading_session(self, market: Market, as_of: datetime) -> bool:
        local = as_of.astimezone(self._timezone_for(market)) if as_of.tzinfo else as_of
        sessions = CN_SESSIONS if market in {Market.CN_SH, Market.CN_SZ} else HK_SESSIONS
        return any(session.contains(local.time()) for session in sessions)

    def _validate_lot_size(self, instrument: Instrument, order: OrderIntent, result: ValidationResult) -> None:
        if order.quantity % instrument.lot_size != 0:
            result.add_error(
                "lot_size",
                f"{order.quantity} is not a multiple of board lot {instrument.lot_size}.",
            )

    def _validate_order_type(self, instrument: Instrument, order: OrderIntent, result: ValidationResult) -> None:
        if instrument.market in {Market.CN_SH, Market.CN_SZ} and order.order_type == OrderType.ENHANCED_LIMIT:
            result.add_error("order_type", "Enhanced limit orders are Hong Kong specific.")
        if instrument.market == Market.HK and order.order_type == OrderType.MARKET:
            result.add_error("order_type", "Use limit, enhanced limit, or auction order types for Hong Kong MVP.")

    def _validate_tick_size(self, instrument: Instrument, order: OrderIntent, result: ValidationResult) -> None:
        if order.limit_price is None:
            return
        tick = 0.01 if instrument.market in {Market.CN_SH, Market.CN_SZ} else hk_tick_size(order.limit_price)
        multiple = round(order.limit_price / tick)
        if not isclose(order.limit_price, multiple * tick, abs_tol=1e-8):
            result.add_error("tick_size", f"Price {order.limit_price} does not align with tick size {tick}.")

    def _validate_price_limits(
        self,
        instrument: Instrument,
        order: OrderIntent,
        quote: Quote,
        result: ValidationResult,
    ) -> None:
        if order.limit_price is None or instrument.price_limit_pct is None:
            return
        previous_close = quote.previous_close
        if previous_close is None:
            result.add_error("missing_previous_close", "A-share price-limit checks require previous_close.")
            return

        limit_up = quote.limit_up or round(previous_close * (1 + instrument.price_limit_pct), 2)
        limit_down = quote.limit_down or round(previous_close * (1 - instrument.price_limit_pct), 2)
        if order.limit_price > limit_up:
            result.add_error("above_limit_up", f"Price {order.limit_price} is above limit-up {limit_up}.")
        if order.limit_price < limit_down:
            result.add_error("below_limit_down", f"Price {order.limit_price} is below limit-down {limit_down}.")

        if instrument.board == Board.STAR and order.quantity < 200:
            result.add_error("star_min_order", "STAR board buy/sell quantity should be at least 200 shares in this MVP.")

    def _validate_sellable_quantity(
        self,
        instrument: Instrument,
        order: OrderIntent,
        position: Position | None,
        result: ValidationResult,
    ) -> None:
        if order.side != OrderSide.SELL:
            return
        sellable = position.sellable_quantity if position else 0
        if order.quantity > sellable:
            result.add_error(
                "sellable_quantity",
                f"Trying to sell {order.quantity}, but only {sellable} shares are sellable.",
            )

    @staticmethod
    def _timezone_for(market: Market) -> ZoneInfo:
        if market == Market.HK:
            return ZoneInfo("Asia/Hong_Kong")
        return ZoneInfo("Asia/Shanghai")

