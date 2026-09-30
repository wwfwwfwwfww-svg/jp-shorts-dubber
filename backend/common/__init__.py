"""Shared modules used by more than one feature (dubbing pipeline + 소재 찾기).

Only pieces that are genuinely reused live here. Right now that is the Anthropic
client wrapper (``llm``). More shared pieces (TTS, loudness, audio QA, metadata,
Japanese-script rules) will move here when Stage 2 (production flow) is built.
"""
