from __future__ import annotations


def filter_citation_labels(token: str, citation_count: int, pending: str = "") -> tuple[str, str, bool]:
    """Keep only citation labels assigned to retrieved chunks by the server.

    ``pending`` permits labels split across streaming tokens to be handled without
    trusting the model to finish a valid label.
    """
    safe_token = ""
    citation_seen = False
    for character in token:
        if not pending:
            if character == "[":
                pending = character
            else:
                safe_token += character
        elif character.isdigit():
            pending += character
        elif character == "]" and len(pending) > 1:
            citation_number = int(pending[1:])
            if 1 <= citation_number <= citation_count:
                safe_token += f"[{citation_number}]"
                citation_seen = True
            else:
                safe_token += "[unsupported citation removed]"
            pending = ""
        else:
            safe_token += pending + character
            pending = ""
    return safe_token, pending, citation_seen


def finish_citation_filter(pending: str) -> str:
    """Return safe text for an unfinished numeric citation at stream completion."""
    return "[unsupported citation removed]" if pending else ""
