"""Operational workflows for the four A/H platform rollout phases."""

from __future__ import annotations

from datetime import datetime

from trading_platform.models import (
    ApprovalStatus,
    ApprovalTicket,
    OrderIntent,
    PhaseCapability,
    PlatformMode,
    SignalIntent,
    ValidationResult,
    new_id,
)


PHASE_CAPABILITIES: tuple[PhaseCapability, ...] = (
    PhaseCapability(
        mode=PlatformMode.RESEARCH_ONLY,
        name="阶段一：A/H 研究版",
        description="TradingAgents 生成 A 股/港股研究报告和结构化 SignalIntent，不生成订单。",
        order_behavior="NO_ORDER",
        required_controls=("instrument_resolver", "ah_data_tools", "signal_normalizer"),
    ),
    PhaseCapability(
        mode=PlatformMode.PAPER_TRADING,
        name="阶段二：仿真交易版",
        description="SignalIntent 经过市场规则和风控后进入 paper broker，验证订单与持仓路径。",
        order_behavior="PAPER_ORDER",
        required_controls=("market_rules", "risk_engine", "paper_broker", "audit_log"),
    ),
    PhaseCapability(
        mode=PlatformMode.LIVE_GUARDED,
        name="阶段三：半自动实盘",
        description="通过规则和风控的订单进入人工审批队列，批准后才允许发送至券商网关。",
        order_behavior="APPROVAL_REQUIRED",
        required_controls=("approval_queue", "broker_gateway", "manual_review", "audit_log"),
    ),
    PhaseCapability(
        mode=PlatformMode.LIVE_AUTO,
        name="阶段四：小额度自动实盘",
        description="仅对白名单策略、白名单标的和小额度订单开放自动执行。",
        order_behavior="GUARDED_AUTO_ORDER",
        required_controls=("auto_whitelist", "notional_cap", "kill_switch", "audit_log"),
    ),
)


class ApprovalQueue:
    """In-memory approval queue used by the guarded-live phase."""

    def __init__(self):
        self._tickets: dict[str, ApprovalTicket] = {}

    def submit(
        self,
        signal: SignalIntent,
        order_intent: OrderIntent,
        validation: ValidationResult,
    ) -> ApprovalTicket:
        ticket = ApprovalTicket(
            ticket_id=new_id("apr"),
            signal=signal,
            order_intent=order_intent,
            validation=validation,
        )
        self._tickets[ticket.ticket_id] = ticket
        return ticket

    def approve(self, ticket_id: str, *, reviewer: str, comment: str | None = None) -> ApprovalTicket:
        ticket = self._require_ticket(ticket_id)
        if ticket.status != ApprovalStatus.PENDING:
            raise ValueError(f"Ticket {ticket_id} is not pending.")
        ticket.status = ApprovalStatus.APPROVED
        ticket.reviewer = reviewer
        ticket.comment = comment
        ticket.updated_at = datetime.utcnow()
        return ticket

    def reject(self, ticket_id: str, *, reviewer: str, comment: str | None = None) -> ApprovalTicket:
        ticket = self._require_ticket(ticket_id)
        if ticket.status != ApprovalStatus.PENDING:
            raise ValueError(f"Ticket {ticket_id} is not pending.")
        ticket.status = ApprovalStatus.REJECTED
        ticket.reviewer = reviewer
        ticket.comment = comment
        ticket.updated_at = datetime.utcnow()
        return ticket

    def mark_executed(self, ticket_id: str) -> ApprovalTicket:
        ticket = self._require_ticket(ticket_id)
        if ticket.status != ApprovalStatus.APPROVED:
            raise ValueError(f"Ticket {ticket_id} must be approved before execution.")
        ticket.status = ApprovalStatus.EXECUTED
        ticket.updated_at = datetime.utcnow()
        return ticket

    def list(self, status: ApprovalStatus | None = None) -> list[ApprovalTicket]:
        tickets = list(self._tickets.values())
        if status is not None:
            tickets = [ticket for ticket in tickets if ticket.status == status]
        return tickets

    def get(self, ticket_id: str) -> ApprovalTicket | None:
        return self._tickets.get(ticket_id)

    def _require_ticket(self, ticket_id: str) -> ApprovalTicket:
        ticket = self.get(ticket_id)
        if ticket is None:
            raise KeyError(f"Unknown approval ticket {ticket_id}.")
        return ticket


def capability_for(mode: PlatformMode) -> PhaseCapability:
    for capability in PHASE_CAPABILITIES:
        if capability.mode == mode:
            return capability
    raise ValueError(f"Unsupported platform mode {mode}.")

