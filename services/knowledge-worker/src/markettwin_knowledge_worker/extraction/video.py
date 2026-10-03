"""Deterministic video clipping and timestamp provenance for direct multimodal generation."""

import asyncio
import os
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path
from tempfile import mkdtemp

import av

from markettwin_knowledge_worker.extraction.contracts import (
    ExtractedEvidence,
    ExtractionResult,
)


@dataclass(frozen=True, slots=True)
class VideoClip:
    """One actual media clip mapped to the original source timeline."""

    path: Path
    start_seconds: float
    end_seconds: float


class VideoExtractionError(RuntimeError):
    """Raised when a video cannot be prepared as source evidence."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


class VideoExtractor:
    """Prepare whole short videos or deterministic long-video clips."""

    name = "pyav-ffmpeg-video-source-adapter"
    version = "1"

    def __init__(self, *, clip_seconds: int = 90, overlap_seconds: int = 5) -> None:
        if clip_seconds <= 0:
            raise ValueError("clip_seconds must be positive.")
        if overlap_seconds < 0 or overlap_seconds >= clip_seconds:
            raise ValueError("overlap_seconds must be nonnegative and smaller than clip_seconds.")
        self._clip_seconds = clip_seconds
        self._overlap_seconds = overlap_seconds

    async def extract(self, path: Path) -> ExtractionResult:
        """Return timestamped direct-media evidence; the Knowledge Builder owns semantic work."""
        self._media_type(path)
        if not await asyncio.to_thread(path.is_file):
            raise VideoExtractionError("parsing_failed", f"Video does not exist: {path.name}")
        try:
            duration = await asyncio.to_thread(self._duration_seconds, path)
        except Exception as exc:
            raise VideoExtractionError(
                "parsing_failed", f"Unable to inspect video: {path.name}"
            ) from exc
        if duration <= 0:
            raise VideoExtractionError(
                "parsing_failed", f"Video has no readable duration: {path.name}"
            )

        ranges = self._clip_ranges(duration)
        cleanup_paths: tuple[Path, ...] = ()
        if len(ranges) == 1:
            start, end = ranges[0]
            clips = (VideoClip(path, start, end),)
        else:
            temporary_directory = Path(mkdtemp(prefix="markettwin-video-"))
            try:
                clips = await self._prepare_clips(
                    source=path,
                    ranges=ranges,
                    temp_root=temporary_directory,
                )
            except BaseException:
                shutil.rmtree(temporary_directory, ignore_errors=True)
                raise
            cleanup_paths = (temporary_directory,)

        units = tuple(
            ExtractedEvidence(
                evidence_type="video_segment",
                content_text=None,
                content_json={"media_type": self._media_type(clip.path)},
                source_locator={
                    "start_seconds": clip.start_seconds,
                    "end_seconds": clip.end_seconds,
                },
                extractor_name=self.name,
                extractor_version=self.version,
                ordinal=ordinal,
                media_path=clip.path,
            )
            for ordinal, clip in enumerate(clips, start=1)
        )
        return ExtractionResult(
            source_path=path,
            units=units,
            issues=(),
            source_item_count=len(ranges),
            processed_item_count=len(units),
            cleanup_paths=cleanup_paths,
        )

    @staticmethod
    def _duration_seconds(path: Path) -> float:
        with av.open(str(path)) as container:
            if container.duration is not None:
                return float(container.duration / av.time_base)
            durations = [
                float(stream.duration * stream.time_base)
                for stream in container.streams
                if stream.duration is not None and stream.time_base is not None
            ]
        return max(durations, default=0.0)

    def _clip_ranges(self, duration: float) -> tuple[tuple[float, float], ...]:
        if duration <= self._clip_seconds:
            return ((0.0, duration),)
        step = self._clip_seconds - self._overlap_seconds
        ranges: list[tuple[float, float]] = []
        start = 0.0
        while start < duration:
            end = min(start + self._clip_seconds, duration)
            ranges.append((start, end))
            if end >= duration:
                break
            start += step
        return tuple(ranges)

    async def _prepare_clips(
        self,
        *,
        source: Path,
        ranges: tuple[tuple[float, float], ...],
        temp_root: Path,
    ) -> tuple[VideoClip, ...]:
        ffmpeg = self._find_ffmpeg()
        clips: list[VideoClip] = []
        for index, (start, end) in enumerate(ranges, start=1):
            output = temp_root / f"clip-{index:04d}.mp4"
            await asyncio.to_thread(self._trim_clip, ffmpeg, source, output, start, end)
            clips.append(VideoClip(output, start, end))
        return tuple(clips)

    @staticmethod
    def _find_ffmpeg() -> str:
        configured = (os.getenv("FFMPEG_BINARY") or "ffmpeg").strip()
        resolved = shutil.which(configured)
        if resolved is None:
            raise VideoExtractionError(
                "ffmpeg_not_found", "FFmpeg is required for long-video chunking."
            )
        return resolved

    @staticmethod
    def _trim_clip(
        ffmpeg: str, source: Path, output: Path, start_seconds: float, end_seconds: float
    ) -> None:
        result = subprocess.run(
            [
                ffmpeg,
                "-hide_banner",
                "-loglevel",
                "error",
                "-ss",
                f"{start_seconds:.3f}",
                "-i",
                str(source),
                "-t",
                f"{end_seconds - start_seconds:.3f}",
                "-map",
                "0:v:0?",
                "-map",
                "0:a:0?",
                "-c:v",
                "libx264",
                "-preset",
                "veryfast",
                "-crf",
                "23",
                "-c:a",
                "aac",
                "-b:a",
                "96k",
                "-movflags",
                "+faststart",
                "-y",
                str(output),
            ],
            capture_output=True,
            text=True,
            check=False,
        )
        if result.returncode != 0 or not output.exists() or output.stat().st_size == 0:
            raise VideoExtractionError(
                "video_chunking_failed",
                f"FFmpeg failed to create video clip starting at {start_seconds:.3f} seconds.",
            )

    @staticmethod
    def _media_type(path: Path) -> str:
        media_type = {
            ".mp4": "video/mp4",
            ".mov": "video/quicktime",
            ".webm": "video/webm",
        }.get(path.suffix.lower())
        if media_type is None:
            raise VideoExtractionError(
                "unsupported_format", f"Unsupported video format: {path.suffix}"
            )
        return media_type
