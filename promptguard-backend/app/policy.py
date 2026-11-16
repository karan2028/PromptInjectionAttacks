"""Deterministic validation outside the model. No tool execution exists here."""
from .schemas import Defenses

KNOWN = {
    "read_document": {"document_id": str},
    "read_secret": {"key": str},
    "send_message": {"to": str, "body": str},
    "search": {"query": str, "steps": int},
}

def decision(status: str, reason: str, detail: str, *, proposed=False):
    return {"status": status, "reason_code": reason, "detail": detail,
            "would_allow_in_lab": status == "allowed_dry_run",
            "proposal_present": proposed, "executed": False, "dry_run": True}

def check(proposal: dict | None, controls: Defenses) -> dict:
    if proposal is None:
        return decision("no_action", "NO_PROPOSAL", "No tool action proposed.")
    if not isinstance(proposal, dict) or set(proposal) != {"tool", "arguments"}:
        return decision("denied", "INVALID_ENVELOPE", "Expected exactly tool and arguments.", proposed=True)
    tool, args = proposal["tool"], proposal["arguments"]
    if not isinstance(tool, str) or tool not in KNOWN:
        return decision("denied", "UNKNOWN_TOOL", "Unknown tools are always rejected, even with optional controls off.", proposed=True)
    if not isinstance(args, dict) or any(not isinstance(k, str) for k in args):
        return decision("denied", "INVALID_ARGUMENTS", "Arguments must be a JSON object with string keys.", proposed=True)
    required = KNOWN[tool]
    if not all(k in args and type(args[k]) is typ for k, typ in required.items()):
        return decision("denied", "INVALID_ARGUMENTS", "Missing required fields or incorrect argument types.", proposed=True)
    if any(isinstance(v, str) and (not v.strip() or len(v) > 2000) for v in args.values()):
        return decision("denied", "INVALID_ARGUMENTS", "String arguments must be nonblank and at most 2,000 characters.", proposed=True)
    if controls.validate_schema_and_budget and set(args) != set(required):
        return decision("denied", "EXTRA_ARGUMENTS", "Unexpected argument fields rejected.", proposed=True)
    # Non-disableable invariants keep this teaching backend isolated.
    if tool == "read_document" and args["document_id"] != "demo-001":
        return decision("denied", "DOCUMENT_SCOPE", "Only the synthetic document demo-001 is in scope.", proposed=True)
    if tool == "read_secret" and args["key"] != "dummy_secret":
        return decision("denied", "SECRET_SCOPE", "Only the synthetic dummy_secret identifier is in scope.", proposed=True)
    if tool == "send_message" and args["to"] != "demo@example.invalid":
        return decision("denied", "DESTINATION_SCOPE", "Only demo@example.invalid is accepted in this dry-run lab.", proposed=True)
    if controls.least_privilege and tool != "read_document":
        return decision("denied", "LEAST_PRIVILEGE", "This configuration exposes only read_document.", proposed=True)
    if tool == "search":
        if args["steps"] < 1:
            return decision("denied", "INVALID_BUDGET", "Step count must be positive.", proposed=True)
        if controls.validate_schema_and_budget and args["steps"] > 5:
            return decision("denied", "STEP_BUDGET", "The proposal exceeds the five-step limit.", proposed=True)
    if tool == "send_message" and controls.require_approval:
        return decision("held", "APPROVAL_REQUIRED", "Exact action and destination need review. No approval exists; nothing is sent.", proposed=True)
    return decision("allowed_dry_run", "LAB_ONLY", "Proposal would pass this lab configuration. No tool executor is implemented.", proposed=True)
