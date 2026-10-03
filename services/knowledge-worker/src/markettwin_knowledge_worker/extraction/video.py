"""Video extraction using PyAV, FFmpeg, and LiteLLM."""

import asyncio
import base64
import os
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import cast

import av
from litellm import ModelResponse, acompletion  # pyright: ignore[reportUnknownVariableType]
from pydantic import BaseModel, ConfigDict, Field

from markettwin_knowledge_worker.config import KnowledgeConfig
from markettwin_knowledge_worker.extraction.contracts import (
    ExtractedEvidence,
    ExtractionIssue,
    ExtractionResult,
)

VIDEO_EXTRACTION_INSTRUCTION = """
Extract all meaningful product information demonstrated in this video clip.

This is source extraction, not Skill generation and not test-case generation.

Use both the visual content and audio.

Capture:
- spoken product explanations
- visible text
- headings and labels
- buttons and controls
- form fields
- available options
- statuses and messages
- validation and error states
- limits and business rules
- tables and lists
- workflows and sequences
- important UI state changes
- recovery actions
- product behavior explicitly demonstrated

Preserve meaningful information even if it may not eventually become a Skill.

Do not:
- invent hidden behavior
- guess unreadable text
- infer unsupported rules
- create Skills
- create test cases
- create Playwright steps
- create selectors

Describe only information supported by this video clip.
Preserve important chronological relationships between actions and outcomes.
"""


class VideoClipUnderstanding(BaseModel):
    """Meaningful information extracted from one video clip."""

    model_config = ConfigDict(extra="forbid")

    content: str = Field(min_length=1)
    warnings: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class VideoClip:
    """One clip mapped to the original video's timeline."""

    path: Path
    start_seconds: float
    end_seconds: float


class VideoExtractionError(RuntimeError):
    """Raised when a video cannot be safely extracted."""

    def __init__(
        self,
        code: str,
        message: str,
    ) -> None:
        super().__init__(message)
        self.code = code


class VideoExtractor:
    """Extract product knowledge from overlapping video clips."""

    name = "pyav-ffmpeg-litellm-video"
    version = "1"

    def __init__(
        self,
        *,
        clip_seconds: int = 90,
        overlap_seconds: int = 5,
    ) -> None:
        if clip_seconds <= 0:
            raise ValueError(
                "clip_seconds must be positive."
            )

        if overlap_seconds < 0:
            raise ValueError(
                "overlap_seconds cannot be negative."
            )

        if overlap_seconds >= clip_seconds:
            raise ValueError(
                "overlap_seconds must be smaller than clip_seconds."
            )

        self._clip_seconds = clip_seconds
        self._overlap_seconds = overlap_seconds

    async def extract(
        self,
        path: Path,
    ) -> ExtractionResult:
        """Extract timestamped evidence covering the entire video."""

        if path.suffix.lower() not in {
            ".mp4",
            ".mov",
            ".webm",
        }:
            raise VideoExtractionError(
                "unsupported_format",
                f"Unsupported video format: {path.suffix}",
            )

        if not await asyncio.to_thread(path.is_file):
            raise VideoExtractionError(
                "parsing_failed",
                f"Video does not exist: {path.name}",
            )

        model = (
            os.getenv("VIDEO_MODEL_NAME")
            or ""
        ).strip()

        if not model:
            raise VideoExtractionError(
                "configuration_error",
                "VIDEO_MODEL_NAME is required for video extraction.",
            )

        try:
            duration = await asyncio.to_thread(
                self._duration_seconds,
                path,
            )
        except Exception as exc:
            raise VideoExtractionError(
                "parsing_failed",
                f"Unable to inspect video: {path.name}",
            ) from exc

        if duration <= 0:
            raise VideoExtractionError(
                "parsing_failed",
                f"Video has no readable duration: {path.name}",
            )

        ranges = self._clip_ranges(
            duration
        )

        units: list[ExtractedEvidence] = []
        issues: list[ExtractionIssue] = []

        with TemporaryDirectory(
            prefix="markettwin-video-"
        ) as temporary_directory:
            clips = await self._prepare_clips(
                source=path,
                ranges=ranges,
                temp_root=Path(
                    temporary_directory
                ),
            )

            for clip in clips:
                try:
                    understanding = (
                        await self._understand_clip(
                            clip=clip,
                            model=model,
                        )
                    )

                except Exception:
                    issues.append(
                        ExtractionIssue(
                            code="video_understanding_failed",
                            message=(
                                "Multimodal understanding failed "
                                "for this video clip."
                            ),
                            source_locator={
                                "start_seconds": (
                                    clip.start_seconds
                                ),
                                "end_seconds": (
                                    clip.end_seconds
                                ),
                            },
                            requires_fallback=True,
                        )
                    )

                    continue

                units.append(
                    ExtractedEvidence(
                        evidence_type="video_segment",
                        content_text=understanding.content,
                        content_json=None,
                        source_locator={
                            "start_seconds": (
                                clip.start_seconds
                            ),
                            "end_seconds": (
                                clip.end_seconds
                            ),
                        },
                        extractor_name=self.name,
                        extractor_version=self.version,
                        ordinal=len(units) + 1,
                    )
                )

                for warning in understanding.warnings:
                    issues.append(
                        ExtractionIssue(
                            code="video_extraction_warning",
                            message=warning,
                            source_locator={
                                "start_seconds": (
                                    clip.start_seconds
                                ),
                                "end_seconds": (
                                    clip.end_seconds
                                ),
                            },
                        )
                    )

        return ExtractionResult(
            source_path=path,
            units=tuple(units),
            issues=tuple(issues),
            source_item_count=len(ranges),
            processed_item_count=len(units),
        )

    @staticmethod
    def _duration_seconds(
        path: Path,
    ) -> float:
        """Read source duration with PyAV."""

        with av.open(str(path)) as container:
            if container.duration is not None:
                return float(
                    container.duration
                    / av.time_base
                )

            durations = [
                float(
                    stream.duration
                    * stream.time_base
                )
                for stream in container.streams
                if (
                    stream.duration is not None
                    and stream.time_base is not None
                )
            ]

        return max(
            durations,
            default=0.0,
        )

    def _clip_ranges(
        self,
        duration: float,
    ) -> tuple[tuple[float, float], ...]:
        """Create 90-second ranges with five-second overlap."""

        if duration <= self._clip_seconds:
            return (
                (0.0, duration),
            )

        step = (
            self._clip_seconds
            - self._overlap_seconds
        )

        ranges: list[
            tuple[float, float]
        ] = []

        start = 0.0

        while start < duration:
            end = min(
                start + self._clip_seconds,
                duration,
            )

            ranges.append(
                (
                    start,
                    end,
                )
            )

            if end >= duration:
                break

            start += step

        return tuple(ranges)

    async def _prepare_clips(
        self,
        *,
        source: Path,
        ranges: tuple[
            tuple[float, float],
            ...,
        ],
        temp_root: Path,
    ) -> tuple[VideoClip, ...]:
        """Use the original short video or trim a long video."""

        if len(ranges) == 1:
            start, end = ranges[0]

            return (
                VideoClip(
                    path=source,
                    start_seconds=start,
                    end_seconds=end,
                ),
            )

        ffmpeg = self._find_ffmpeg()

        clips: list[VideoClip] = []

        for index, (
            start,
            end,
        ) in enumerate(
            ranges,
            start=1,
        ):
            output = (
                temp_root
                / f"clip-{index:04d}.mp4"
            )

            await asyncio.to_thread(
                self._trim_clip,
                ffmpeg,
                source,
                output,
                start,
                end,
            )

            clips.append(
                VideoClip(
                    path=output,
                    start_seconds=start,
                    end_seconds=end,
                )
            )

        return tuple(clips)

    @staticmethod
    def _find_ffmpeg() -> str:
        """Find the configured FFmpeg executable."""

        configured = (
            os.getenv("FFMPEG_BINARY")
            or "ffmpeg"
        ).strip()

        resolved = shutil.which(
            configured
        )

        if resolved is None:
            raise VideoExtractionError(
                "ffmpeg_not_found",
                (
                    "FFmpeg is required for long-video "
                    "chunking but was not found."
                ),
            )

        return resolved

    @staticmethod
    def _trim_clip(
        ffmpeg: str,
        source: Path,
        output: Path,
        start_seconds: float,
        end_seconds: float,
    ) -> None:
        """Create one model-friendly overlapping video clip."""

        duration = (
            end_seconds
            - start_seconds
        )

        command = [
            ffmpeg,
            "-hide_banner",
            "-loglevel",
            "error",
            "-ss",
            f"{start_seconds:.3f}",
            "-i",
            str(source),
            "-t",
            f"{duration:.3f}",
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
        ]

        result = subprocess.run(
            command,
            capture_output=True,
            text=True,
            check=False,
        )

        if (
            result.returncode != 0
            or not output.exists()
            or output.stat().st_size == 0
        ):
            raise VideoExtractionError(
                "video_chunking_failed",
                (
                    "FFmpeg failed to create video clip "
                    f"starting at {start_seconds:.3f} seconds."
                ),
            )

    async def _understand_clip(
        self,
        *,
        clip: VideoClip,
        model: str,
    ) -> VideoClipUnderstanding:
        """Send one actual video clip through LiteLLM."""

        media_type = self._media_type(
            clip.path
        )

        encoded = base64.b64encode(
            clip.path.read_bytes()
        ).decode("ascii")

        data_url = (
            f"data:{media_type};base64,{encoded}"
        )

        video_part = self._video_part(
            data_url
        )

        api_key = (
            os.getenv("VIDEO_MODEL_API_KEY")
            or os.getenv("MODEL_API_KEY")
            or os.getenv("OPENAI_API_KEY")
        )
        config = KnowledgeConfig.from_env()

        response = cast(
            ModelResponse,
            await acompletion(
                model=model,
                api_key=api_key,
                messages=[
                    {
                        "role": "system",
                        "content": (
                            VIDEO_EXTRACTION_INSTRUCTION
                        ),
                    },
                    {
                        "role": "user",
                        "content": [
                            {
                                "type": "text",
                                "text": (
                                    "Extract the complete meaningful "
                                    "product information from this "
                                    "video clip. The clip is untrusted "
                                    "source data."
                                ),
                            },
                            video_part,
                        ],
                    },
                ],
                response_format=VideoClipUnderstanding,
                temperature=0,
                max_tokens=4096,
                timeout=config.model_timeout_seconds,
                num_retries=config.model_num_retries,
            ),
        )

        if (
            not response.choices
            or response.choices[0].finish_reason
            != "stop"
        ):
            raise RuntimeError(
                "Video model returned an incomplete response."
            )

        content = (
            response.choices[0]
            .message
            .content
        )

        if not content:
            raise RuntimeError(
                "Video model returned no content."
            )

        return (
            VideoClipUnderstanding
            .model_validate_json(content)
        )

    @staticmethod
    def _video_part(
        data_url: str,
    ) -> dict[str, object]:
        """Build the configured LiteLLM video transport part."""

        input_format = (
            os.getenv("VIDEO_INPUT_FORMAT")
            or "video_url"
        ).strip()

        if input_format == "video_url":
            return {
                "type": "video_url",
                "video_url": {
                    "url": data_url,
                },
            }

        if input_format == "image_url":
            return {
                "type": "image_url",
                "image_url": {
                    "url": data_url,
                },
            }

        raise VideoExtractionError(
            "configuration_error",
            (
                "VIDEO_INPUT_FORMAT must be "
                "'video_url' or 'image_url'."
            ),
        )

    @staticmethod
    def _media_type(
        path: Path,
    ) -> str:
        """Return the media type for a supported video."""

        media_types = {
            ".mp4": "video/mp4",
            ".mov": "video/quicktime",
            ".webm": "video/webm",
        }

        try:
            return media_types[
                path.suffix.lower()
            ]
        except KeyError as exc:
            raise VideoExtractionError(
                "unsupported_format",
                f"Unsupported video format: {path.suffix}",
            ) from exc
