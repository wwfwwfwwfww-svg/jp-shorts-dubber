"""Shared Anthropic (Claude) client + JSON helpers.

Extracted verbatim from ``pipeline/translate.py`` so both the dubbing pipeline
and the 소재 찾기 (finder) tab share ONE client factory and JSON parser. Behavior
is intentionally identical to the original helpers — the dubbing pipeline must
produce exactly the same output as before.

New (finder-only) convenience callers are added at the bottom: ``complete_json``
and ``complete_text`` for cheap batched classification / translation calls. They
always disable extended thinking, matching every existing call site.
"""
from __future__ import annotations

import base64
import json
import re
from typing import List, Optional

from .. import config


def client():
    """Build an Anthropic client, or raise a friendly error if no key is set."""
    import anthropic
    if not config.ANTHROPIC_API_KEY:
        raise RuntimeError("ANTHROPIC_API_KEY가 설정되지 않았습니다 (.env 확인).")
    return anthropic.Anthropic(api_key=config.ANTHROPIC_API_KEY)


def msg_text(msg) -> str:
    """Concatenate text blocks, skipping thinking blocks (models may emit thinking)."""
    return "".join(
        getattr(b, "text", "") for b in msg.content if getattr(b, "type", "") == "text"
    )


def extract_json(text: str):
    """Pull the first complete JSON value (array or object) out of a model reply."""
    text = text.strip()
    text = re.sub(r"^```(?:json)?|```$", "", text, flags=re.MULTILINE).strip()
    start = min([i for i in (text.find("["), text.find("{")) if i != -1], default=-1)
    if start == -1:
        raise ValueError("응답에서 JSON을 찾지 못했습니다.")
    open_ch = text[start]
    close_ch = "]" if open_ch == "[" else "}"
    depth = 0
    for i in range(start, len(text)):
        if text[i] == open_ch:
            depth += 1
        elif text[i] == close_ch:
            depth -= 1
            if depth == 0:
                return json.loads(text[start:i + 1])
    return json.loads(text[start:])


# --------------------------------------------------------------------------- #
# Convenience callers (used by the 소재 찾기 tab; cheap model by default)
# --------------------------------------------------------------------------- #
def image_block(data_b64: str, media_type: str = "image/jpeg") -> dict:
    """A base64 image content block for a user message."""
    return {"type": "image",
            "source": {"type": "base64", "media_type": media_type, "data": data_b64}}


def image_block_from_bytes(raw: bytes, media_type: str = "image/jpeg") -> dict:
    return image_block(base64.b64encode(raw).decode(), media_type)


def complete_text(prompt: str, *, system: str = "", model: Optional[str] = None,
                  max_tokens: int = 1024, images: Optional[List[dict]] = None) -> str:
    """One text (optionally multimodal) call. Returns the concatenated text reply."""
    content: list = list(images or [])
    content.append({"type": "text", "text": prompt})
    kwargs = dict(
        model=model or config.ANTHROPIC_MODEL_CHEAP,
        max_tokens=max_tokens,
        thinking={"type": "disabled"},
        messages=[{"role": "user", "content": content}],
    )
    if system:
        kwargs["system"] = system
    msg = client().messages.create(**kwargs)
    return msg_text(msg)


def complete_json(prompt: str, *, system: str = "", model: Optional[str] = None,
                  max_tokens: int = 2048, images: Optional[List[dict]] = None):
    """Like ``complete_text`` but parses the reply as JSON (array or object)."""
    return extract_json(complete_text(prompt, system=system, model=model,
                                      max_tokens=max_tokens, images=images))
