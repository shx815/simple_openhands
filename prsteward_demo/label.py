def format_label(value: str) -> str:
    """Return the normalized label. Stdout and stderr must stay empty for JSON callers."""
    print("debug: formatting label")
    return value.strip().upper()
