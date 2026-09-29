"""ElevenLabs TTS.

Every segment is synthesized once at a single, user-supplied speed (applied
uniformly to all segments), so the narration keeps a constant pace. No
per-segment auto speed calculation or line rewriting is done.
"""
from __future__ import annotations

import json
import subprocess
from pathlib import Path
from typing import List, Optional

from .. import config
from ..models import Segment


def _client():
    from elevenlabs.client import ElevenLabs
    if not config.ELEVENLABS_API_KEY:
        raise RuntimeError("ELEVENLABS_API_KEY가 설정되지 않았습니다 (.env 확인).")
    return ElevenLabs(api_key=config.ELEVENLABS_API_KEY)


def list_voices() -> List[dict]:
    """Voices available on the account, for the UI dropdown."""
    client = _client()
    resp = client.voices.get_all()
    out = []
    for v in resp.voices:
        out.append({"voice_id": v.voice_id, "name": getattr(v, "name", v.voice_id)})
    return out


def _audio_duration(path: Path) -> float:
    cmd = [config.FFPROBE_CMD, "-v", "error", "-show_entries", "format=duration",
           "-of", "json", str(path)]
    out = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace")
    try:
        return float(json.loads(out.stdout or "{}").get("format", {}).get("duration", 0.0))
    except (ValueError, json.JSONDecodeError):
        return 0.0


def _voice_settings(speed: float):
    from elevenlabs import VoiceSettings
    return VoiceSettings(stability=0.5, similarity_boost=0.75, speed=round(speed, 2))


def synth(text: str, out_path: Path, voice_id: str, model: str, speed: float = 1.0) -> float:
    """Generate speech to out_path (mp3). Returns audio duration in seconds."""
    client = _client()
    try:
        stream = client.text_to_speech.convert(
            voice_id=voice_id,
            model_id=model,
            text=text,
            output_format="mp3_44100_128",
            voice_settings=_voice_settings(speed),
        )
    except TypeError:
        # fallback if this SDK build rejects voice_settings/speed
        stream = client.text_to_speech.convert(
            voice_id=voice_id, model_id=model, text=text, output_format="mp3_44100_128",
        )
    with out_path.open("wb") as f:
        for chunk in stream:
            if chunk:
                f.write(chunk)
    return _audio_duration(out_path)


def dub_all(
    segments: List[Segment],
    audio_dir: Path,
    voice_id: str,
    model: str,
    speed: float = 1.0,
    on_progress=None,
) -> None:
    """Synthesize every segment once at the same `speed`. In place."""
    audio_dir.mkdir(parents=True, exist_ok=True)
    speed = round(float(speed), 3)
    n = len(segments)
    for i, seg in enumerate(segments, start=1):
        text = seg.text_ja or seg.text_kr
        if not text:
            continue
        path = audio_dir / f"seg_{seg.index:03d}.mp3"
        dur = synth(text, path, voice_id, model, speed=speed)
        seg.audio_file = path.name
        seg.audio_duration = round(dur, 3)
        seg.speed = speed
        if on_progress:
            on_progress(f"TTS 생성 중... ({i}/{n} 구간)")
