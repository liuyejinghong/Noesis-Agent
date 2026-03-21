from __future__ import annotations

from dataclasses import dataclass, field

from noesis_agent.core.enums import RuntimeMode


@dataclass(slots=True)
class LiveSafetyRequest:
    mode: RuntimeMode
    read_only: bool
    live_confirmed: bool
    emergency_stop: bool
    daily_pnl_pct: float
    max_daily_loss_pct: float


@dataclass(slots=True)
class LiveSafetyDecision:
    allowed: bool
    reasons: list[str] = field(default_factory=list)


def evaluate_live_safety(request: LiveSafetyRequest) -> LiveSafetyDecision:
    reasons: list[str] = []
    if request.mode is not RuntimeMode.LIVE:
        return LiveSafetyDecision(allowed=True, reasons=[])
    if request.read_only:
        reasons.append("read_only_mode_enabled")
    if not request.live_confirmed:
        reasons.append("live_confirmation_missing")
    if request.emergency_stop:
        reasons.append("emergency_stop_active")
    if request.daily_pnl_pct <= -abs(request.max_daily_loss_pct):
        reasons.append("daily_loss_limit_exceeded")
    return LiveSafetyDecision(allowed=not reasons, reasons=reasons)


@dataclass(slots=True)
class ManualOrderSafetyRequest:
    read_only: bool
    emergency_stop: bool
    remote_enabled: bool
    last_reconciled_at: str | None
    reconcile_divergence_count: int


@dataclass(slots=True)
class ManualOrderSafetyDecision:
    allowed: bool
    reasons: list[str] = field(default_factory=list)


def evaluate_manual_order_safety(
    request: ManualOrderSafetyRequest,
) -> ManualOrderSafetyDecision:
    reasons: list[str] = []
    if request.read_only:
        reasons.append("read_only_mode_enabled")
    if request.emergency_stop:
        reasons.append("emergency_stop_active")
    if not request.remote_enabled:
        reasons.append("remote_execution_client_required")
    if not request.last_reconciled_at:
        reasons.append("reconcile_required_before_manual_order")
    if request.reconcile_divergence_count > 0:
        reasons.append("reconcile_divergence_active")
    return ManualOrderSafetyDecision(allowed=not reasons, reasons=reasons)
