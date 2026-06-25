from trading_platform.instruments import InstrumentResolver, hk_tick_size
from trading_platform.models import Board, Currency, Market


def test_resolves_shanghai_a_share_with_main_board_rules():
    instrument = InstrumentResolver().resolve("600519.SH")

    assert instrument.symbol == "600519.SH"
    assert instrument.market == Market.CN_SH
    assert instrument.board == Board.MAIN
    assert instrument.currency == Currency.CNY
    assert instrument.lot_size == 100
    assert instrument.price_limit_pct == 0.10


def test_resolves_hong_kong_symbol_and_pads_code():
    instrument = InstrumentResolver().resolve("700.HK")

    assert instrument.symbol == "0700.HK"
    assert instrument.market == Market.HK
    assert instrument.currency == Currency.HKD
    assert instrument.lot_size == 100
    assert instrument.price_limit_pct is None


def test_hong_kong_tick_size_bands():
    assert hk_tick_size(0.2) == 0.001
    assert hk_tick_size(5.0) == 0.01
    assert hk_tick_size(50.0) == 0.05
    assert hk_tick_size(120.0) == 0.10

