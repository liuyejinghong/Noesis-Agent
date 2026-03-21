# pyright: reportMissingImports=false

from __future__ import annotations

from noesis_agent.core.enums import RuntimeMode
from noesis_agent.execution.emergency import (
    LiveSafetyRequest,
    ManualOrderSafetyRequest,
    evaluate_live_safety,
    evaluate_manual_order_safety,
)


def test_evaluate_live_safety_allows_non_live_mode_unconditionally() -> None:
    decision = evaluate_live_safety(
        LiveSafetyRequest(
            mode=RuntimeMode.BACKTEST,
            read_only=True,
            live_confirmed=False,
            emergency_stop=True,
            daily_pnl_pct=-99.0,
            max_daily_loss_pct=5.0,
        )
    )

    assert decision.allowed is True
    assert decision.reasons == []


def test_evaluate_live_safety_allows_live_when_all_checks_pass() -> None:
    decision = evaluate_live_safety(
        LiveSafetyRequest(
            mode=RuntimeMode.LIVE,
            read_only=False,
            live_confirmed=True,
            emergency_stop=False,
            daily_pnl_pct=-1.0,
            max_daily_loss_pct=5.0,
        )
    )

    assert decision.allowed is True
    assert decision.reasons == []


def test_evaluate_live_safety_blocks_read_only_mode() -> None:
    decision = evaluate_live_safety(
        LiveSafetyRequest(
            mode=RuntimeMode.LIVE,
            read_only=True,
            live_confirmed=True,
            emergency_stop=False,
            daily_pnl_pct=0.0,
            max_daily_loss_pct=5.0,
        )
    )

    assert decision.allowed is False
    assert decision.reasons == ["read_only_mode_enabled"]


def test_evaluate_live_safety_blocks_missing_live_confirmation() -> None:
    decision = evaluate_live_safety(
        LiveSafetyRequest(
            mode=RuntimeMode.LIVE,
            read_only=False,
            live_confirmed=False,
            emergency_stop=False,
            daily_pnl_pct=0.0,
            max_daily_loss_pct=5.0,
        )
    )

    assert decision.allowed is False
    assert decision.reasons == ["live_confirmation_missing"]


def test_evaluate_live_safety_blocks_emergency_stop() -> None:
    decision = evaluate_live_safety(
        LiveSafetyRequest(
            mode=RuntimeMode.LIVE,
            read_only=False,
            live_confirmed=True,
            emergency_stop=True,
            daily_pnl_pct=0.0,
            max_daily_loss_pct=5.0,
        )
    )

    assert decision.allowed is False
    assert decision.reasons == ["emergency_stop_active"]


def test_evaluate_live_safety_blocks_when_daily_loss_limit_is_exceeded() -> None:
    decision = evaluate_live_safety(
        LiveSafetyRequest(
            mode=RuntimeMode.LIVE,
            read_only=False,
            live_confirmed=True,
            emergency_stop=False,
            daily_pnl_pct=-5.0,
            max_daily_loss_pct=5.0,
        )
    )

    assert decision.allowed is False
    assert decision.reasons == ["daily_loss_limit_exceeded"]


def test_evaluate_manual_order_safety_allows_when_all_checks_pass() -> None:
    decision = evaluate_manual_order_safety(
        ManualOrderSafetyRequest(
            read_only=False,
            emergency_stop=False,
            remote_enabled=True,
            last_reconciled_at="2026-03-21T00:00:00Z",
            reconcile_divergence_count=0,
        )
    )

    assert decision.allowed is True
    assert decision.reasons == []


def test_evaluate_manual_order_safety_blocks_read_only_mode() -> None:
    decision = evaluate_manual_order_safety(
        ManualOrderSafetyRequest(
            read_only=True,
            emergency_stop=False,
            remote_enabled=True,
            last_reconciled_at="2026-03-21T00:00:00Z",
            reconcile_divergence_count=0,
        )
    )

    assert decision.allowed is False
    assert decision.reasons == ["read_only_mode_enabled"]


def test_evaluate_manual_order_safety_blocks_emergency_stop() -> None:
    decision = evaluate_manual_order_safety(
        ManualOrderSafetyRequest(
            read_only=False,
            emergency_stop=True,
            remote_enabled=True,
            last_reconciled_at="2026-03-21T00:00:00Z",
            reconcile_divergence_count=0,
        )
    )

    assert decision.allowed is False
    assert decision.reasons == ["emergency_stop_active"]


def test_evaluate_manual_order_safety_blocks_without_remote_execution() -> None:
    decision = evaluate_manual_order_safety(
        ManualOrderSafetyRequest(
            read_only=False,
            emergency_stop=False,
            remote_enabled=False,
            last_reconciled_at="2026-03-21T00:00:00Z",
            reconcile_divergence_count=0,
        )
    )

    assert decision.allowed is False
    assert decision.reasons == ["remote_execution_client_required"]


def test_evaluate_manual_order_safety_blocks_when_not_reconciled() -> None:
    decision = evaluate_manual_order_safety(
        ManualOrderSafetyRequest(
            read_only=False,
            emergency_stop=False,
            remote_enabled=True,
            last_reconciled_at=None,
            reconcile_divergence_count=0,
        )
    )

    assert decision.allowed is False
    assert decision.reasons == ["reconcile_required_before_manual_order"]


def test_evaluate_manual_order_safety_blocks_when_divergence_exists() -> None:
    decision = evaluate_manual_order_safety(
        ManualOrderSafetyRequest(
            read_only=False,
            emergency_stop=False,
            remote_enabled=True,
            last_reconciled_at="2026-03-21T00:00:00Z",
            reconcile_divergence_count=2,
        )
    )

    assert decision.allowed is False
    assert decision.reasons == ["reconcile_divergence_active"]


def test_evaluate_manual_order_safety_combines_multiple_reasons_in_order() -> None:
    decision = evaluate_manual_order_safety(
        ManualOrderSafetyRequest(
            read_only=True,
            emergency_stop=True,
            remote_enabled=False,
            last_reconciled_at=None,
            reconcile_divergence_count=3,
        )
    )

    assert decision.allowed is False
    assert decision.reasons == [
        "read_only_mode_enabled",
        "emergency_stop_active",
        "remote_execution_client_required",
        "reconcile_required_before_manual_order",
        "reconcile_divergence_active",
    ]
