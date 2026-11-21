def format_label(value: str) -> str:
    """Return the normalized label. Stdout and stderr must stay empty for JSON callers."""
    return value.strip().upper()
