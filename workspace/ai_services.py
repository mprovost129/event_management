import json
import urllib.error
import urllib.request

from django.conf import settings

SYSTEM_INSTRUCTION = """You are the writing assistant inside Gather HQs, an organization management platform.
Create polished, accurate content using only the facts supplied by the user. Do not invent dates, prices,
locations, promises, contact details, or policies. Return only the requested content, without analysis or
prefatory remarks. Use clear headings when they improve usability."""


def _fallback(draft):
    heading = draft.title.strip()
    body = draft.instructions.strip()
    context = draft.context.strip()
    parts = [heading, "", body]
    if context:
        parts.extend(["", "Details to incorporate:", context])
    parts.extend(
        [
            "",
            "Review this draft for final dates, links, pricing, and contact information before publishing.",
        ]
    )
    return "\n".join(parts)


def generate_content(draft):
    api_key = getattr(settings, "OPENAI_API_KEY", "")
    model = getattr(settings, "OPENAI_MODEL", "gpt-4.1-mini")
    if not api_key:
        return _fallback(draft), "template", "local-template"

    prompt = (
        f"Content type: {draft.get_content_type_display()}\n"
        f"Working title: {draft.title}\n"
        f"Instructions:\n{draft.instructions}\n\n"
        f"Source context:\n{draft.context or 'No additional context supplied.'}"
    )
    payload = json.dumps(
        {
            "model": model,
            "instructions": SYSTEM_INSTRUCTION,
            "input": prompt,
        }
    ).encode("utf-8")
    request = urllib.request.Request(
        "https://api.openai.com/v1/responses",
        data=payload,
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=45) as response:
            data = json.loads(response.read().decode("utf-8"))
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as exc:
        raise RuntimeError(f"AI provider request failed: {exc}") from exc

    text = data.get("output_text", "").strip()
    if not text:
        chunks = []
        for item in data.get("output", []):
            for content in item.get("content", []):
                if content.get("type") == "output_text" and content.get("text"):
                    chunks.append(content["text"])
        text = "\n".join(chunks).strip()
    if not text:
        raise RuntimeError("The AI provider returned no usable content.")
    return text, "openai", model
