def column_index(columns: list[str], *keyword_groups: str) -> int:
    """Case-insensitive substring match against column names, checked in the
    given keyword priority order. Returns the index of the first column
    matching a keyword, or -1 if nothing matches."""
    lower = [c.lower() for c in columns]
    for keyword in keyword_groups:
        for i, c in enumerate(lower):
            if keyword in c:
                return i
    return -1
