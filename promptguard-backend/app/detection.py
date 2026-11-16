"""Transparent lexical indicators, NOT a comprehensive injection detector."""
import re
PATTERNS = [
    ("instruction_override", r"\bignore\b.{0,100}\b(instructions?|task|summary)\b", "Task integrity"),
    ("secret_request", r"\b(reveal|print|show|disclose)\b.{0,100}\b(secret|token|password)\b", "Confidentiality"),
    ("tool_redirection", r"\b(send a message|send_message|forward.{0,30}email)\b", "Unauthorized action"),
    ("resource_loop", r"\b(forever|never finish|endless|repeat the search)\b", "Resource exhaustion"),
    ("unknown_tool", r"\b(unknown_tool|unexpected_admin)\b", "Invalid proposal"),
]

def analyze(text: str) -> dict:
    matches = []
    for name, pattern, concern in PATTERNS:
        for match in re.finditer(pattern, text, re.I | re.S):
            matches.append({"indicator": name, "concern": concern, "start": match.start(), "end": match.end(), "excerpt": match.group(0)})
    quote_hint = bool(re.search(r"\b(classify|quoted|classroom)\b", text, re.I))
    return {
        "method": "lexical_patterns_v1",
        "status": "indicators_found" if matches else "no_known_indicators",
        "matches": matches,
        "may_be_benign_security_discussion": quote_hint,
        "is_security_verdict": False,
        "limitation": "Patterns can miss attacks and flag benign quotations. No match does not mean safe. This result never grants tool permissions.",
    }

def demo_kind(text: str) -> str:
    """Select a teaching script for custom input. Never used for authorization."""
    a = analyze(text)
    if a["may_be_benign_security_discussion"] and a["matches"]:
        return "benign"
    names = {x["indicator"] for x in a["matches"]}
    for indicator, kind in [("unknown_tool", "schema"), ("resource_loop", "loop"), ("tool_redirection", "tool"), ("secret_request", "secret"), ("instruction_override", "override")]:
        if indicator in names:
            return kind
    return "unsupported"
