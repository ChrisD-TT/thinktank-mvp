"""
ThinkTank — Gate decision engine.
Pure function: takes score + critique dicts, returns a gate verdict dict.
All thresholds are read from config so they can be tuned without code changes.
"""

from thinktank import config as cfg


def compute_gate(score: dict, critique: dict) -> dict:
    impact  = int(score.get("impact",  0))
    effort  = int(score.get("effort",  0))
    risk    = int(score.get("risk",    0))
    novelty = int(score.get("novelty", 0))

    failure_modes       = critique.get("failure_modes", [])
    missing_assumptions = critique.get("missing_assumptions", [])

    rationale          = []
    recommended_action = ""

    # ── Decision tree ─────────────────────────────────────────────────────────
    if risk >= cfg.GATE_ABORT_RISK_AT_OR_ABOVE:
        verdict, signal, signal_emoji = "DO NOT PROCEED", "STOP", "❌"
        rationale.append(f"Risk is too high ({risk} >= {cfg.GATE_ABORT_RISK_AT_OR_ABOVE}).")
        if failure_modes:
            rationale.append(
                "Top failure modes: " + "; ".join(failure_modes[:2])
                + ("…" if len(failure_modes) > 2 else "")
            )
        recommended_action = "Reduce risk: narrow scope, add controls, then re-score."

    elif impact <= cfg.GATE_STOP_MAX_IMPACT:
        verdict, signal, signal_emoji = "DO NOT PROCEED", "STOP", "❌"
        rationale.append(f"Impact too low ({impact} <= {cfg.GATE_STOP_MAX_IMPACT}).")
        recommended_action = "Park this idea or reframe to increase operational impact."

    elif (
        impact >= cfg.GATE_PROCEED_MIN_IMPACT
        and effort <= cfg.GATE_PROCEED_MAX_EFFORT
        and risk   <= cfg.GATE_PROCEED_MAX_RISK
    ):
        verdict, signal, signal_emoji = "PROCEED", "OK", "✅"
        rationale.append("High impact with manageable effort and risk.")
        recommended_action = "Proceed with a small pilot; track metrics for one week."

    else:
        verdict, signal, signal_emoji = "PROCEED WITH CAUTION", "CAUTION", "⚠️"
        if risk >= cfg.GATE_CAUTION_RISK_AT_OR_ABOVE:
            rationale.append(f"Risk is elevated ({risk} >= {cfg.GATE_CAUTION_RISK_AT_OR_ABOVE}).")
        if effort >= cfg.GATE_CAUTION_EFFORT_AT_OR_ABOVE:
            rationale.append(f"Effort is high ({effort} >= {cfg.GATE_CAUTION_EFFORT_AT_OR_ABOVE}).")
        if missing_assumptions:
            rationale.append(
                "Missing assumptions: " + "; ".join(missing_assumptions[:2])
                + ("…" if len(missing_assumptions) > 2 else "")
            )
        if not rationale:
            rationale.append("Trade-offs are mixed; proceed in a controlled way.")
        recommended_action = "Run a limited pilot, validate assumptions, then re-score."

    return {
        "verdict":       verdict,
        "signal":        signal,
        "signal_emoji":  signal_emoji,
        "score":         {"impact": impact, "effort": effort, "risk": risk, "novelty": novelty},
        "key_risks": {
            "failure_modes":       failure_modes[:5],
            "missing_assumptions": missing_assumptions[:5],
        },
        "thresholds": {
            "abort_risk_at_or_above":     cfg.GATE_ABORT_RISK_AT_OR_ABOVE,
            "proceed_min_impact":         cfg.GATE_PROCEED_MIN_IMPACT,
            "proceed_max_effort":         cfg.GATE_PROCEED_MAX_EFFORT,
            "proceed_max_risk":           cfg.GATE_PROCEED_MAX_RISK,
            "caution_risk_at_or_above":   cfg.GATE_CAUTION_RISK_AT_OR_ABOVE,
            "caution_effort_at_or_above": cfg.GATE_CAUTION_EFFORT_AT_OR_ABOVE,
            "stop_max_impact":            cfg.GATE_STOP_MAX_IMPACT,
        },
        "rationale":          rationale,
        "recommended_action": recommended_action,
    }
