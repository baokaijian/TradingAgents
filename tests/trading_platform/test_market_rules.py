from datetime import datetime
from zoneinfo import ZoneInfo

from trading_platform.instruments import InstrumentResolver
from trading_platform.market_rules import MarketRuleEngine
from trading_platform.models import OrderIntent, OrderSide, OrderType, Position, Quote


def test_a_share_rejects_order_above_limit_up():
    instrument = InstrumentResolver().resolve("600519.SH")
    order = OrderIntent(
        signal_id="sig",
        account_id="acct",
        symbol=instrument.symbol,
        side=OrderSide.BUY,
        order_type=OrderType.LIMIT,
        quantity=100,
        limit_price=111.0,
    )
    quote = Quote(symbol=instrument.symbol, last=100.0, previous_close=100.0)

    result = MarketRuleEngine().validate_order(
        instrument,
        order,
        quote,
        as_of=datetime(2026, 6, 25, 10, 0, tzinfo=ZoneInfo("Asia/Shanghai")),
    )

    assert not result.accepted
    assert any(issue.code == "above_limit_up" for issue in result.issues)


def test_a_share_rejects_unsellable_t_plus_one_quantity():
    instrument = InstrumentResolver().resolve("000001.SZ")
    order = OrderIntent(
        signal_id="sig",
        account_id="acct",
        symbol=instrument.symbol,
        side=OrderSide.SELL,
        order_type=OrderType.LIMIT,
        quantity=100,
        limit_price=10.0,
    )
    quote = Quote(symbol=instrument.symbol, last=10.0, previous_close=10.0)
    position = Position(symbol=instrument.symbol, quantity=100, sellable_quantity=0, avg_cost=9.5)

    result = MarketRuleEngine().validate_order(
        instrument,
        order,
        quote,
        position=position,
        as_of=datetime(2026, 6, 25, 10, 0, tzinfo=ZoneInfo("Asia/Shanghai")),
    )

    assert not result.accepted
    assert any(issue.code == "sellable_quantity" for issue in result.issues)


def test_hong_kong_rejects_quantity_below_board_lot_multiple():
    instrument = InstrumentResolver().resolve("0700.HK")
    order = OrderIntent(
        signal_id="sig",
        account_id="acct",
        symbol=instrument.symbol,
        side=OrderSide.BUY,
        order_type=OrderType.LIMIT,
        quantity=50,
        limit_price=350.0,
    )
    quote = Quote(symbol=instrument.symbol, last=350.0)

    result = MarketRuleEngine().validate_order(
        instrument,
        order,
        quote,
        as_of=datetime(2026, 6, 25, 10, 0, tzinfo=ZoneInfo("Asia/Hong_Kong")),
    )

    assert not result.accepted
    assert any(issue.code == "lot_size" for issue in result.issues)

