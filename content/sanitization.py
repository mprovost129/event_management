import re

import bleach

ALLOWED_TAGS = [
    "p",
    "br",
    "strong",
    "em",
    "u",
    "ul",
    "ol",
    "li",
    "a",
    "h2",
    "h3",
    "blockquote",
]

ALLOWED_ATTRIBUTES = {
    "a": ["href", "title", "target", "rel"],
}

ALLOWED_PROTOCOLS = ["http", "https", "mailto"]

SCRIPT_STYLE_BLOCK = re.compile(
    r"<(script|style)[^>]*>.*?</\1>",
    re.IGNORECASE | re.DOTALL,
)


def sanitize_rich_text(value):
    raw = SCRIPT_STYLE_BLOCK.sub("", value or "")
    cleaned = bleach.clean(
        raw,
        tags=ALLOWED_TAGS,
        attributes=ALLOWED_ATTRIBUTES,
        protocols=ALLOWED_PROTOCOLS,
        strip=True,
    )
    return bleach.linkify(cleaned)
