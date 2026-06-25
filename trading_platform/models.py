"""Core domain models for the A-share and Hong Kong automation platform."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime
from enum import Enum
from typing import Any
from uuid import uuid4


class Market(str, Enum):
    CN_SH = "CN_SH"
    CN_SZ = "CN_SZ"
    HK = "HK"


class AssetClass(str, Enum):
    STOCK = "stock"
    ETF = "etf"
    REIT = "reit"
    CBOND = "cbond"


class Board(str, Enum):
    MAIN = "main"
    STAR = "star"
    CHINEXT = "chinext"
    SME = "sme"
    ST = "st"
    HK_MAIN = "hk_main"


class Currency(str, Enum):
    CNY = "CNY"
    HKD = "HKD"
    CNH = "CNH"


class SettlementRule(str, Enum):
    T_PLUS_1 = "T+1"
    T_PLUS_0 = "T+0"


class SignalSide(str, Enum):
    BUY = "BUY"
    SELL = "SELL"
    HOLD = "HOLD"
    REDUCE = "REDUCE"
    INCREASE = "INCREASE"


class OrderSide(str, Enum):
    BUY = "BUY"
    SELL = "SELL"


class OrderType(str, Enum):
    LIMIT = "LIMIT"
    MARKET = "MARKET"
    ENHANCED_LIMIT = "ENHANCED_LIMIT"
    AUCTION = "AUCTION"


class TimeInForce(str, Enum):
    DAY = "DAY"
    IOC = "IOC"
    FOK = "FOK"


class OrderStatus(str, Enum):
    NEW = "NEW"
    SUBMITTED = "SUBMITTED"
    PARTIALLY_FILLED = "PARTIALLY_FILLED"
    FILLED = "FILLED"
    CANCELLED = "CANCELLED"
    REJECTED = "REJECTED"


class PlatformMode(str, Enum):
    RESEARCH_ONLY = "research_only"
    PAPER_TRADING = "paper_trading"
    LIVE_GUARDED = "live_guarded"
    LIVE_AUTO = "live_auto"


class ApprovalStatus(str, Enum):
    PENDING = "PENDING"
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"
    EXECUTED = "EXECUTED"


@dataclass(frozen=True)
class Instrument:
    symbol: str
    market: Market
    asset_class: AssetClass = AssetClass.STOCK
    board: Board = Board.MAIN
    currency: Currency = Currency.CNY
    lot_size: int = 100
    tick_size_rule: str = "fixed_0.01"
    price_limit_pct: float | None = 0.10
    settlement_rule: SettlementRule = SettlementRule.T_PLUS_1
    tradable: bool = True
    name: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class Quote:
    symbol: str
    last: float
    bid: float | None = None
    ask: float | None = None
    previous_close: float | None = None
    trading_day: date | None = None
    suspended: bool = False
    limit_up: float | None = None
    limit_down: float | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class Position:
    symbol: str
    quantity: int
    sellable_quantity: int
    avg_cost: float
    market_value: float = 0.0
    currency: Currency = Currency.CNY


@dataclass
class AccountSnapshot:
    account_id: str
    cash: dict[Currency, float]
    equity: float
    positions: dict[str, Position] = field(default_factory=dict)

    def position_for(self, symbol: str) -> Position:
        return self.positions.get(
            symbol,
            Position(symbol=symbol, quantity=0, sellable_quantity=0, avg_cost=0.0),
        )

    def cash_available(self, currency: Currency) -> float:
        return float(self.cash.get(currency, 0.0))


@dataclass(frozen=True)
class SignalIntent:
    run_id: str
    strategy_id: str
    symbol: str
    market: Market
    side: SignalSide
    conviction: float
    target_weight: float | None = None
    max_notional: float | None = None
    entry_price: float | None = None
    stop_loss: float | None = None
    take_profit: float | None = None
    time_horizon: str | None = None
    rationale: str = ""
    evidence_refs: tuple[str, ...] = ()
    raw_decision: str = ""


@dataclass(frozen=True)
class OrderIntent:
    signal_id: str
    account_id: str
    symbol: str
    side: OrderSide
    order_type: OrderType
    quantity: int
    limit_price: float | None
    tif: TimeInForce = TimeInForce.DAY
    source: str = "agent"
    created_at: datetime = field(default_factory=datetime.utcnow)

    @property
    def notional(self) -> float:
        return abs(self.quantity * float(self.limit_price or 0.0))


@dataclass
class Order:
    order_id: str
    intent: OrderIntent
    status: OrderStatus = OrderStatus.NEW
    broker_order_id: str | None = None
    filled_qty: int = 0
    avg_price: float | None = None
    reject_reason: str | None = None
    created_at: datetime = field(default_factory=datetime.utcnow)
    updated_at: datetime = field(default_factory=datetime.utcnow)


@dataclass(frozen=True)
class ValidationIssue:
    code: str
    message: str
    severity: str = "error"


@dataclass
class ValidationResult:
    accepted: bool
    issues: list[ValidationIssue] = field(default_factory=list)

    @classmethod
    def accept(cls) -> "ValidationResult":
        return cls(accepted=True)

    @classmethod
    def reject(cls, code: str, message: str) -> "ValidationResult":
        return cls(False, [ValidationIssue(code=code, message=message)])

    def add_error(self, code: str, message: str) -> None:
        self.accepted = False
        self.issues.append(ValidationIssue(code=code, message=message))

    def merge(self, other: "ValidationResult") -> "ValidationResult":
        self.accepted = self.accepted and other.accepted
        self.issues.extend(other.issues)
        return self

    def raise_if_rejected(self) -> None:
        if not self.accepted:
            details = "; ".join(f"{i.code}: {i.message}" for i in self.issues)
            raise ValueError(details)


@dataclass(frozen=True)
class RiskLimits:
    min_conviction: float = 0.55
    max_order_notional: float = 100_000.0
    max_position_weight: float = 0.20
    max_daily_notional: float = 500_000.0
    allow_market_orders: bool = False
    blocked_symbols: frozenset[str] = frozenset()
    require_manual_approval: bool = True
    auto_trade_enabled: bool = False
    auto_trade_symbols: frozenset[str] = frozenset()
    max_auto_order_notional: float = 20_000.0


@dataclass
class ApprovalTicket:
    ticket_id: str
    signal: SignalIntent
    order_intent: OrderIntent
    validation: ValidationResult
    status: ApprovalStatus = ApprovalStatus.PENDING
    reviewer: str | None = None
    comment: str | None = None
    created_at: datetime = field(default_factory=datetime.utcnow)
    updated_at: datetime = field(default_factory=datetime.utcnow)


@dataclass(frozen=True)
class PhaseCapability:
    mode: PlatformMode
    name: str
    description: str
    order_behavior: str
    required_controls: tuple[str, ...]


def new_id(prefix: str) -> str:
    return f"{prefix}_{uuid4().hex[:12]}"
