"""Instrument resolution for A-share and Hong Kong symbols."""

from __future__ import annotations

import re

from trading_platform.models import (
    AssetClass,
    Board,
    Currency,
    Instrument,
    Market,
    SettlementRule,
)


_A_SHARE_RE = re.compile(r"^(?P<code>\d{6})\.(?P<suffix>SH|SS|SZ)$", re.IGNORECASE)
_HK_RE = re.compile(r"^(?P<code>\d{1,5})\.HK$", re.IGNORECASE)


DEFAULT_HK_LOT_SIZES = {
    "0005.HK": 400,
    "0388.HK": 100,
    "0700.HK": 100,
    "0939.HK": 1000,
    "0941.HK": 500,
    "1299.HK": 200,
    "1810.HK": 200,
    "2318.HK": 500,
    "3690.HK": 100,
    "9988.HK": 100,
}


class InstrumentResolver:
    """Resolve user-entered symbols into platform `Instrument` objects.

    The resolver is intentionally deterministic and offline. Production systems
    should enrich the result with exchange master data, ST flags, suspensions,
    board-lot files, Stock Connect eligibility, and corporate actions.
    """

    def __init__(self, hk_lot_sizes: dict[str, int] | None = None):
        self.hk_lot_sizes = {**DEFAULT_HK_LOT_SIZES, **(hk_lot_sizes or {})}

    def resolve(self, raw_symbol: str, *, name: str | None = None, is_st: bool = False) -> Instrument:
        symbol = raw_symbol.strip().upper()
        a_match = _A_SHARE_RE.fullmatch(symbol)
        if a_match:
            return self._resolve_a_share(a_match.group("code"), a_match.group("suffix"), name, is_st)

        hk_match = _HK_RE.fullmatch(symbol)
        if hk_match:
            return self._resolve_hk(hk_match.group("code"), name)

        raise ValueError(
            f"Unsupported symbol {raw_symbol!r}. Use A-share symbols like 600519.SH "
            "or Hong Kong symbols like 0700.HK."
        )

    def _resolve_a_share(
        self,
        code: str,
        suffix: str,
        name: str | None,
        is_st: bool,
    ) -> Instrument:
        canonical_suffix = "SH" if suffix.upper() in {"SH", "SS"} else "SZ"
        market = Market.CN_SH if canonical_suffix == "SH" else Market.CN_SZ
        board = self._infer_a_share_board(code, market, is_st)
        limit_pct = self._a_share_price_limit(board)

        return Instrument(
            symbol=f"{code}.{canonical_suffix}",
            market=market,
            asset_class=AssetClass.STOCK,
            board=board,
            currency=Currency.CNY,
            lot_size=100,
            tick_size_rule="fixed_0.01",
            price_limit_pct=limit_pct,
            settlement_rule=SettlementRule.T_PLUS_1,
            tradable=True,
            name=name,
            metadata={"source": "synthetic_exchange_rules"},
        )

    def _resolve_hk(self, code: str, name: str | None) -> Instrument:
        canonical = f"{int(code):04d}.HK"
        lot_size = self.hk_lot_sizes.get(canonical, 100)
        return Instrument(
            symbol=canonical,
            market=Market.HK,
            asset_class=AssetClass.STOCK,
            board=Board.HK_MAIN,
            currency=Currency.HKD,
            lot_size=lot_size,
            tick_size_rule="hkex_equity_tick_table",
            price_limit_pct=None,
            settlement_rule=SettlementRule.T_PLUS_0,
            tradable=True,
            name=name,
            metadata={"source": "synthetic_hk_rules"},
        )

    @staticmethod
    def _infer_a_share_board(code: str, market: Market, is_st: bool) -> Board:
        if is_st:
            return Board.ST
        if market == Market.CN_SH and code.startswith(("688", "689")):
            return Board.STAR
        if market == Market.CN_SZ and code.startswith(("300", "301")):
            return Board.CHINEXT
        if market == Market.CN_SZ and code.startswith("002"):
            return Board.SME
        return Board.MAIN

    @staticmethod
    def _a_share_price_limit(board: Board) -> float:
        if board == Board.ST:
            return 0.05
        if board in {Board.STAR, Board.CHINEXT}:
            return 0.20
        return 0.10


def hk_tick_size(price: float) -> float:
    """Return the HKEX equity tick size for common price bands.

    This covers the standard board-lot securities table used by the platform
    MVP. Production code should load the official table as reference data.
    """

    if price < 0.25:
        return 0.001
    if price < 0.50:
        return 0.005
    if price < 10.0:
        return 0.01
    if price < 20.0:
        return 0.02
    if price < 100.0:
        return 0.05
    if price < 200.0:
        return 0.10
    if price < 500.0:
        return 0.20
    if price < 1000.0:
        return 0.50
    if price < 2000.0:
        return 1.00
    if price < 5000.0:
        return 2.00
    if price < 9995.0:
        return 5.00
    return 10.00

