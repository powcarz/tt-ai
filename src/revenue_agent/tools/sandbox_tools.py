"""Tools for applying and rolling back actions in the sandbox."""

import json
from datetime import date, datetime
from typing import Any
from uuid import uuid4

from langchain_core.tools import tool

from revenue_agent.config import settings
from revenue_agent.schemas.actions import ActionType

_APPLIED_INVOICES_FILE = "applied_invoices.json"
_APPLIED_CREDIT_MEMOS_FILE = "applied_credit_memos.json"
_APPLIED_AMENDMENTS_FILE = "applied_amendments.json"
_AUDIT_LOG_FILE = "audit_log.json"


def _load_sandbox_file(filename: str) -> list:
    """Load a sandbox JSON file."""
    path = settings.sandbox_dir / filename
    if not path.exists():
        return []
    with open(path, "r") as f:
        return json.load(f)


def _save_sandbox_file(filename: str, data: list) -> None:
    """Save data to a sandbox JSON file."""
    path = settings.sandbox_dir / filename
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w") as f:
        json.dump(data, f, indent=2, default=str)


def _append_audit_log(entry: dict[str, Any]) -> None:
    """Append an entry to the audit log."""
    log = _load_sandbox_file(_AUDIT_LOG_FILE)
    log.append(entry)
    _save_sandbox_file(_AUDIT_LOG_FILE, log)


def _append_and_save(filename: str, payload: dict[str, Any]) -> None:
    items = _load_sandbox_file(filename)
    items.append(payload)
    _save_sandbox_file(filename, items)


def _build_action_response(
    *,
    action_type: str,
    result_id: str,
    message: str,
    details: dict[str, Any],
) -> dict:
    return {
        "success": True,
        "action_type": action_type,
        "result_id": result_id,
        "message": message,
        "details": details,
    }


def _apply_make_good_invoice(
    *,
    plan_id: str,
    amount: float,
    currency: str,
    reason: str,
    billing_period_start: str,
    billing_period_end: str,
    applied_at: str,
) -> dict:
    invoice_id = f"INV-MG-{uuid4().hex[:6].upper()}"
    invoice_data = {
        "id": invoice_id,
        "plan_id": plan_id,
        "amount": amount,
        "currency": currency,
        "billing_period_start": billing_period_start,
        "billing_period_end": billing_period_end,
        "issue_date": date.today().isoformat(),
        "status": "issued",
        "reason": reason,
        "is_make_good": True,
        "applied_at": applied_at,
    }

    _append_and_save(_APPLIED_INVOICES_FILE, invoice_data)
    _append_audit_log(
        {
            "action": "apply_make_good_invoice",
            "result_id": invoice_id,
            "plan_id": plan_id,
            "amount": amount,
            "currency": currency,
            "reason": reason,
            "timestamp": applied_at,
        }
    )

    return _build_action_response(
        action_type=ActionType.MAKE_GOOD_INVOICE.value,
        result_id=invoice_id,
        message=f"Make-good invoice {invoice_id} has been applied to the sandbox.",
        details=invoice_data,
    )


def _apply_credit_memo(
    *,
    plan_id: str,
    invoice_id: str,
    amount: float,
    currency: str,
    reason: str,
    applied_at: str,
) -> dict:
    memo_id = f"CM-{uuid4().hex[:6].upper()}"
    memo_data = {
        "id": memo_id,
        "invoice_id": invoice_id,
        "plan_id": plan_id,
        "amount": amount,
        "currency": currency,
        "reason": reason,
        "issue_date": date.today().isoformat(),
        "applied_at": applied_at,
    }

    _append_and_save(_APPLIED_CREDIT_MEMOS_FILE, memo_data)
    _append_audit_log(
        {
            "action": "apply_credit_memo",
            "result_id": memo_id,
            "invoice_id": invoice_id,
            "plan_id": plan_id,
            "amount": amount,
            "currency": currency,
            "reason": reason,
            "timestamp": applied_at,
        }
    )

    return _build_action_response(
        action_type=ActionType.CREDIT_MEMO.value,
        result_id=memo_id,
        message=f"Credit memo {memo_id} has been applied to the sandbox.",
        details=memo_data,
    )


def _apply_plan_amendment(
    *,
    plan_id: str,
    changes: dict[str, Any],
    reason: str,
    applied_at: str,
) -> dict:
    amendment_id = f"AMD-{uuid4().hex[:6].upper()}"
    amendment_data = {
        "id": amendment_id,
        "plan_id": plan_id,
        "changes": changes,
        "reason": reason,
        "applied_at": applied_at,
    }

    _append_and_save(_APPLIED_AMENDMENTS_FILE, amendment_data)
    _append_audit_log(
        {
            "action": "apply_plan_amendment",
            "result_id": amendment_id,
            "plan_id": plan_id,
            "changes": changes,
            "reason": reason,
            "timestamp": applied_at,
        }
    )

    return _build_action_response(
        action_type=ActionType.PLAN_AMENDMENT.value,
        result_id=amendment_id,
        message=f"Plan amendment {amendment_id} has been applied to the sandbox.",
        details=amendment_data,
    )


# In-memory store for pending action drafts
_pending_actions: dict[str, dict] = {}


def store_pending_action(action_id: str, action_data: dict) -> None:
    """Store a pending action for later application."""
    _pending_actions[action_id] = action_data


def get_pending_action(action_id: str) -> dict | None:
    """Retrieve a pending action by ID."""
    return _pending_actions.get(action_id)


@tool
def apply_action(
    action_id: str,
) -> dict:
    """Apply a proposed action to the sandbox after user approval.

    Args:
        action_id: The proposed action draft ID (e.g., "ACT-1A2B3C4D")

    Returns:
        Dictionary with the result of the applied action.
    """
    applied_at = datetime.utcnow().isoformat()

    pending = get_pending_action(action_id)
    if not pending:
        return {
            "error": (
                f"Action {action_id} not found or no longer pending. "
                "The action must be proposed again before it can be applied."
            )
        }

    action_type = pending.get("action_type")
    details = pending.get("details") or {}

    if action_type == ActionType.MAKE_GOOD_INVOICE.value:
        billing_period_start = details.get("billing_period_start")
        billing_period_end = details.get("billing_period_end")
        if not billing_period_start or not billing_period_end:
            return {"error": "Missing billing period dates for make-good invoice"}
        return _apply_make_good_invoice(
            plan_id=details["plan_id"],
            amount=details["amount"],
            currency=details["currency"],
            reason=details["reason"],
            billing_period_start=billing_period_start,
            billing_period_end=billing_period_end,
            applied_at=applied_at,
        )

    if action_type == ActionType.CREDIT_MEMO.value:
        invoice_id = details.get("invoice_id")
        if not invoice_id:
            return {"error": "Missing invoice_id for credit memo"}
        return _apply_credit_memo(
            plan_id=details["plan_id"],
            invoice_id=invoice_id,
            amount=details["amount"],
            currency=details["currency"],
            reason=details["reason"],
            applied_at=applied_at,
        )

    if action_type == ActionType.PLAN_AMENDMENT.value:
        changes = details.get("changes")
        if not changes:
            return {"error": "Missing changes for plan amendment"}
        return _apply_plan_amendment(
            plan_id=details["plan_id"],
            changes=changes,
            reason=details["reason"],
            applied_at=applied_at,
        )

    return {"error": f"Unknown action type: {action_type}"}


@tool
def rollback_action(result_id: str) -> dict:
    """Rollback a previously applied action from the sandbox.

    Args:
        result_id: The result ID of the applied action to rollback (e.g., "INV-MG-ABC123")

    Returns:
        Dictionary indicating success or failure of the rollback.
    """
    timestamp = datetime.utcnow().isoformat()

    # Try to find and remove from each sandbox file
    for filename, action_type in [
        (_APPLIED_INVOICES_FILE, ActionType.MAKE_GOOD_INVOICE.value),
        (_APPLIED_CREDIT_MEMOS_FILE, ActionType.CREDIT_MEMO.value),
        (_APPLIED_AMENDMENTS_FILE, ActionType.PLAN_AMENDMENT.value),
    ]:
        items = _load_sandbox_file(filename)
        original_count = len(items)
        items = [item for item in items if item.get("id") != result_id]

        if len(items) < original_count:
            _save_sandbox_file(filename, items)

            _append_audit_log({
                "action": f"rollback_{action_type}",
                "result_id": result_id,
                "timestamp": timestamp,
            })

            return {
                "success": True,
                "result_id": result_id,
                "action_type": action_type,
                "message": f"Successfully rolled back {result_id} from the sandbox.",
            }

    return {
        "success": False,
        "result_id": result_id,
        "error": f"Action {result_id} not found in sandbox.",
    }
