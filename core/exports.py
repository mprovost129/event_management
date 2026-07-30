FORMULA_PREFIXES = ("=", "+", "-", "@", "\t", "\r", "\n")


def spreadsheet_safe_cell(value):
    """Return a CSV cell that spreadsheet programs will treat as text."""
    text = str(value)
    if text.lstrip().startswith(FORMULA_PREFIXES):
        return f"'{text}"
    return text
