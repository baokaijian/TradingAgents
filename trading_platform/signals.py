"""Normalize TradingAgents markdown decisions into executable signal intents."""

from __future__ import annotations

import re
from dataclasses import dataclass

from trading_platform.models import (
    Market,
    OrderIntent,
    OrderSide,
    OrderType,
    Quote,
    SignalIntent,
    SignalSide,
    TimeInForce,
    new_id,
)


_FIELD_RE = re.compile(r"\*\*(?P<field>[^*]+)\*\*\s*:\s*(?P<value>[^\n]+)")
_FINAL_RE = re.compile(r"FINAL\s+TRANSACTION\s+PROPOSAL:\s*\*\*(?P<action>BUY|SELL|HOLD)\*\*", re.I)


@dataclass(frozen=True)
class NormalizedDecision:
    rating: str | None
    action: str | None
    price_target: float | None
    entry_price: float | None
    stop_loss: float | None
    time_horizon: str | None
    summary: str


class SignalNormalizer:
    """Convert TradingAgents final markdown into deterministic platform signals."""

    rating_to_side = {
        "buy": SignalSide.BUY,
        "overweight": SignalSide.INCREASE,
        "hold": SignalSide.HOLD,
        "underweight": SignalSide.REDUCE,
        "sell": SignalSide.SELL,
    }

    action_to_side = {
        "buy": SignalSide.BUY,
        "hold": SignalSide.HOLD,
        "sell": SignalSide.SELL,
    }

    conviction_by_rating = {
        "buy": 0.80,
        "overweight": 0.65,
        "hold": 0.0,
        "underweight": 0.60,
        "sell": 0.80,
    }

    def parse_decision(self, markdown: str) -> NormalizedDecision:
        fields = {m.group("field").strip().lower(): m.group("value").strip() for m in _FIELD_RE.finditer(markdown)}
        final_match = _FINAL_RE.search(markdown)
        action = fields.get("action")
        if final_match:
            action = final_match.group("action").title()

        summary = fields.get("executive summary") or fields.get("reasoning") or fields.get("rationale") or markdown
        return NormalizedDecision(
            rating=fields.get("rating"),
            action=action,
            price_target=self._parse_float(fields.get("price target")),
            entry_price=self._parse_float(fields.get("entry price")),
            stop_loss=self._parse_float(fields.get("stop loss")),
            time_horizon=fields.get("time horizon"),
            summary=summary,
        )

    def from_markdown(
        self,
        markdown: str,
        *,
        symbol: str,
        market: Market,
        strategy_id: str = "tradingagents-ah",
        run_id: str | None = None,
        max_notional: float | None = None,
        target_weight: float | None = None,
        evidence_refs: tuple[str, ...] = (),
    ) -> SignalIntent:
        parsed = self.parse_decision(markdown)
        side = self._side_from(parsed)
        conviction = self._conviction_from(parsed, side)

        return SignalIntent(
            run_id=run_id or new_id("run"),
            strategy_id=strategy_id,
            symbol=symbol,
            market=market,
            side=side,
            conviction=conviction,
            target_weight=target_weight,
            max_notional=max_notional,
            entry_price=parsed.entry_price,
            stop_loss=parsed.stop_loss,
            take_profit=parsed.price_target,
            time_horizon=parsed.time_horizon,
            rationale=parsed.summary,
            evidence_refs=evidence_refs,
            raw_decision=markdown,
        )

    def to_order_intent(
        self,
        signal: SignalIntent,
        *,
        account_id: str,
        quote: Quote,
        lot_size: int,
        default_notional: float = 10_000.0,
        order_type: OrderType = OrderType.LIMIT,
    ) -> OrderIntent | None:
        if signal.side == SignalSide.HOLD:
            return None

        side = OrderSide.BUY if signal.side in {SignalSide.BUY, SignalSide.INCREASE} else OrderSide.SELL
        price = signal.entry_price or quote.ask or quote.last
        notional = signal.max_notional or default_notional
        raw_qty = int(notional // price)
        quantity = max(lot_size, (raw_qty // lot_size) * lot_size)
        if quantity <= 0:
            return None

        return OrderIntent(
            signal_id=signal.run_id,
            account_id=account_id,
            symbol=signal.symbol,
            side=side,
            order_type=order_type,
            quantity=quantity,
            limit_price=round(price, 4),
            tif=TimeInForce.DAY,
            source="agent",
        )

    def _side_from(self, parsed: NormalizedDecision) -> SignalSide:
        if parsed.action:
            side = self.action_to_side.get(parsed.action.strip().lower())
            if side is not None:
                return side
        if parsed.rating:
            side = self.rating_to_side.get(parsed.rating.strip().lower())
            if side is not None:
                return side
        return SignalSide.HOLD

    def _conviction_from(self, parsed: NormalizedDecision, side: SignalSide) -> float:
        if side == SignalSide.HOLD:
            return 0.0
        if parsed.rating:
            return self.conviction_by_rating.get(parsed.rating.strip().lower(), 0.60)
        if parsed.action:
            return {"buy": 0.70, "sell": 0.70}.get(parsed.action.strip().lower(), 0.0)
        return 0.0

    @staticmethod
    def _parse_float(value: str | None) -> float | None:
        if not value:
            return None
        match = re.search(r"-?\d+(?:\.\d+)?", value.replace(",", ""))
        if not match:
            return None
        return float(match.group(0))

