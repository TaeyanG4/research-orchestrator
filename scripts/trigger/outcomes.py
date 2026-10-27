"""Explain unusable trigger measurements without turning them into predictions."""
from __future__ import annotations


def inconclusive_reason(run: dict) -> dict | None:
    """Use the final attempt; an earlier failed retry does not invalidate recovery.

    This also accepts historical records. A use announcement in a timed-out
    full-task run is evidence of selection, but cannot retroactively supply the
    clean endpoint required by that run's measurement protocol.
    """
    invalid = {"code": "invalid_record", "detail": "Malformed trigger attempt or audit metadata."}
    if not isinstance(run, dict):
        return invalid
    attempts = run.get("attempts", [])
    if not isinstance(attempts, list):
        return invalid
    attempt = attempts[-1] if attempts else run
    if not isinstance(attempt, dict):
        return invalid
    status = attempt.get("status", run.get("status"))
    audit = attempt.get("contamination", {})
    detection = attempt.get("detection", {})
    if not isinstance(audit, dict) or not isinstance(detection, dict):
        return invalid
    if (status is not None and not isinstance(status, str)
            or attempt.get("failure_category") is not None and not isinstance(attempt["failure_category"], str)
            or attempt.get("returncode") is not None and type(attempt["returncode"]) is not int):
        return invalid
    findings = audit.get("findings", [])
    if not isinstance(findings, list) or any(not isinstance(f, dict) for f in findings):
        return invalid
    causes = sorted({finding.get("reason", "unclassified access")
                     if isinstance(finding.get("reason", "unclassified access"), str) else "unclassified access"
                     for finding in findings
                     if finding.get("contaminating", True)})
    if attempt.get("candidate_changed"):
        causes.append("candidate modified")
    if detection.get("other_skill_paths"):
        causes.append("outside candidate skill read")
    if (status == "contaminated" or run.get("status") == "contaminated" or run.get("contaminated")
            or attempt.get("contaminated") or audit.get("contaminated") or causes):
        return {"code": "contamination", "detail": "Excluded context: " + (
            "; ".join(causes) if causes else "saved contamination flag; inspect retained trace")}
    failure = attempt.get("failure_category")
    if status == "timeout" or failure == "timeout":
        suffix = (" Selection was observed, but the saved run did not reach a clean measurement endpoint."
                  if detection.get("triggered") else " No clean measurement endpoint was recorded.")
        return {"code": "timeout", "detail": "Executor timed out." + suffix}
    if failure in {"rate_limit", "transport"}:
        return {"code": failure, "detail": (
            "Final attempt ended at a rate limit." if failure == "rate_limit"
            else "Final attempt ended with a transport disconnect.")}
    if attempt.get("error"):
        return {"code": "setup_error" if failure == "setup" or "returncode" not in attempt else "executor_error",
                "detail": str(attempt["error"])}
    if status not in {None, "ok"}:
        return {"code": "incomplete_execution", "detail": (
            f"Final attempt status={status}, returncode={attempt.get('returncode')}; "
            "no clean selection or completed nonselection endpoint.")}
    if type(run.get("triggered")) is not bool or type(attempt.get("triggered")) is not bool:
        return {"code": "missing_measurement", "detail": "No boolean trigger measurement was recorded."}
    if run["triggered"] != attempt["triggered"] or ("status" in run and status != run["status"]):
        return {"code": "inconsistent_measurement", "detail": "Final attempt and run summary disagree."}
    if "triggered" in detection and (type(detection["triggered"]) is not bool
                                      or detection["triggered"] != attempt["triggered"]):
        return {"code": "inconsistent_measurement", "detail": "Detection evidence and attempt summary disagree."}
    boundary = attempt.get("selection_boundary")
    selected_endpoint = (attempt.get("measurement_protocol") == "first-selection-v1"
                         and isinstance(boundary, dict) and type(boundary.get("event")) is int
                         and boundary["event"] > 0 and attempt["triggered"])
    if failure or (attempt.get("returncode") not in {None, 0} and not selected_endpoint):
        return {"code": "incomplete_execution", "detail": "Recorded executor failure contradicts the claimed clean endpoint."}
    return None
