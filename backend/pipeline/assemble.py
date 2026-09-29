"""Stage 3/4 assembly: sequential concatenation, loudness normalization, SRT.

Audio is concatenated back-to-back (each clip starts exactly where the previous
one ends) — NOT placed at original video timestamps — so there is never any
overlap. The combined track is peak-normalized to TARGET_PEAK_DB. SRT timings
come from the REAL per-clip durations on this sequential timeline.
"""
from __future__ import annotations

from pathlib import Path
from typing import List, Tuple

from .. import config
from ..models import Job, Segment
from .translate import active_seconds


def _pydub():
    from pydub import AudioSegment
    AudioSegment.converter = config.FFMPEG_CMD
    AudioSegment.ffprobe = config.FFPROBE_CMD
    return AudioSegment


def build_sequential(job: Job, audio_dir: Path, out_dir: Path) -> Tuple[Path, Path]:
    """Concatenate all segment clips in order, set seq_start on each, peak-normalize
    to TARGET_PEAK_DB, export wav+mp3. Returns (wav, mp3)."""
    AudioSegment = _pydub()
    out_dir.mkdir(parents=True, exist_ok=True)

    combined = AudioSegment.empty()
    cursor_ms = 0
    for seg in job.segments:
        if not seg.audio_file:
            seg.seq_start = round(cursor_ms / 1000.0, 3)
            continue
        clip_path = audio_dir / seg.audio_file
        if not clip_path.exists():
            seg.seq_start = round(cursor_ms / 1000.0, 3)
            continue
        clip = AudioSegment.from_file(clip_path)
        seg.seq_start = round(cursor_ms / 1000.0, 3)
        seg.audio_duration = round(len(clip) / 1000.0, 3)
        combined += clip
        cursor_ms += len(clip)

    if len(combined) > 0 and combined.max_dBFS != float("-inf"):
        combined = combined.apply_gain(config.TARGET_PEAK_DB - combined.max_dBFS)

    # Record actual vs target length so drift is visible (A4). The target is the
    # narration span Stage 2 aimed for (job.active_seconds), set from the source
    # segments before they were rebuilt into Japanese.
    job.audio_seconds = round(cursor_ms / 1000.0, 3)
    job.target_seconds = round(job.active_seconds or active_seconds(job.segments), 3)

    wav_path = out_dir / "combined.wav"
    mp3_path = out_dir / "combined.mp3"
    (combined if len(combined) else AudioSegment.silent(duration=200)).export(wav_path, format="wav")
    (combined if len(combined) else AudioSegment.silent(duration=200)).export(mp3_path, format="mp3", bitrate="192k")
    return wav_path, mp3_path


def _srt_time(seconds: float) -> str:
    ms = int(round(seconds * 1000))
    h, ms = divmod(ms, 3_600_000)
    m, ms = divmod(ms, 60_000)
    s, ms = divmod(ms, 1000)
    return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"


def build_srt(job: Job, out_dir: Path) -> Tuple[Path, Path]:
    """Write Japanese + Korean-back-translation SRTs on the sequential timeline.
    Returns (ja_path, kr_path)."""
    out_dir.mkdir(parents=True, exist_ok=True)

    def blocks(pick):
        lines, n = [], 0
        for seg in job.segments:
            text = pick(seg)
            if not text:
                continue
            n += 1
            start = seg.seq_start
            end = round(start + (seg.audio_duration or 0.0), 3)
            lines.append(f"{n}\n{_srt_time(start)} --> {_srt_time(end)}\n{text}\n")
        return "\n".join(lines)

    ja_path = out_dir / "subtitle_ja.srt"
    kr_path = out_dir / "subtitle_kr.srt"
    ja_path.write_text(blocks(lambda s: s.text_ja), encoding="utf-8")
    kr_path.write_text(blocks(lambda s: s.text_ja_back or s.text_kr), encoding="utf-8")
    return ja_path, kr_path


def zip_outputs(job: Job, audio_dir: Path, out_dir: Path) -> Path:
    import zipfile
    out_dir.mkdir(parents=True, exist_ok=True)
    zip_path = out_dir / f"{job.id}_dub.zip"
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
        for seg in job.segments:
            if seg.audio_file:
                p = audio_dir / seg.audio_file
                if p.exists():
                    zf.write(p, f"segments/{seg.audio_file}")
        for name in ("combined.wav", "combined.mp3", "subtitle_ja.srt", "subtitle_kr.srt"):
            p = out_dir / name
            if p.exists():
                zf.write(p, name)
        zf.writestr("script.txt", _script_text(job.segments))
    return zip_path


def _script_text(segments: List[Segment]) -> str:
    lines = []
    for s in segments:
        lines.append(
            f"#{s.index}  seq {s.seq_start:.1f}s (+{(s.audio_duration or 0):.1f}s)\n"
            f"  JA: {s.text_ja}\n"
            f"  KR: {s.text_ja_back or s.text_kr}\n"
        )
    return "\n".join(lines)
