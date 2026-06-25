"""A/H-share automation layer built on top of TradingAgents.

The package keeps the LLM-powered TradingAgents graph as a research engine and
adds deterministic trading-platform primitives around it: instrument identity,
signal normalization, market rules, risk checks, and broker gateways.
"""

from trading_platform.instruments import InstrumentResolver
from trading_platform.market_rules import MarketRuleEngine
from trading_platform.models import PlatformMode
from trading_platform.risk import RiskEngine
from trading_platform.signals import SignalNormalizer
from trading_platform.workflows import ApprovalQueue, PHASE_CAPABILITIES

__all__ = [
    "ApprovalQueue",
    "InstrumentResolver",
    "MarketRuleEngine",
    "PHASE_CAPABILITIES",
    "PlatformMode",
    "RiskEngine",
    "SignalNormalizer",
]
