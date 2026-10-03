"""Representative source formats preserve content, provenance, and coverage."""

import json
from pathlib import Path
from unittest.mock import AsyncMock

import pytest
from litellm.types.utils import ModelResponse  # pyright: ignore[reportMissingTypeStubs]
from markettwin_knowledge_worker.extraction import extract_source
from markettwin_knowledge_worker.extraction.csv_file import CsvExtractor
from markettwin_knowledge_worker.extraction.image import ImageExtractor
from markettwin_knowledge_worker.extraction.json_file import JsonExtractor
from markettwin_knowledge_worker.extraction.pptx import PptxExtractor
from markettwin_knowledge_worker.extraction.text import TextExtractor
from markettwin_knowledge_worker.extraction.video import (
    VideoClip,
    VideoClipUnderstanding,
    VideoExtractor,
)
from markettwin_knowledge_worker.extraction.xlsx import XlsxExtractor
from openpyxl import Workbook
from pptx import Presentation


def _small_chunks(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("KNOWLEDGE_SOURCE_CHUNK_MAX_CHARS", "80")
    monkeypatch.setenv("KNOWLEDGE_SKILL_BATCH_MAX_CHARS", "200")


def test_text_csv_and_json_use_bounded_model_ready_units(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _small_chunks(monkeypatch)
    text_path = tmp_path / "rules.md"
    text_path.write_text(
        "# Upload\nPDF and DOCX are supported.\nMaximum size is 10 MB.\n",
        encoding="utf-8",
    )
    csv_path = tmp_path / "limits.csv"
    csv_path.write_text("format,limit\nPDF,10 MB\nDOCX,10 MB\n", encoding="utf-8")
    json_path = tmp_path / "rules.json"
    json_path.write_text(
        json.dumps({"formats": ["PDF", "DOCX"], "rules": "x" * 180}), encoding="utf-8"
    )

    text_result = TextExtractor().extract(text_path)
    csv_result = CsvExtractor().extract(csv_path)
    json_result = JsonExtractor().extract(json_path)

    assert "10 MB" in "".join(unit.content_text or "" for unit in text_result.units)
    assert all(len(unit.content_text or "") <= 80 for unit in csv_result.units)
    assert all(unit.source_locator.get("row_start") for unit in csv_result.units)
    assert len(json_result.units) > 1
    assert all(unit.content_json is not None for unit in json_result.units)
    assert all(
        len(json.dumps(unit.content_json, separators=(",", ":"))) <= 80
        for unit in json_result.units
    )


def test_pptx_and_xlsx_chunk_without_losing_source_order(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _small_chunks(monkeypatch)
    pptx_path = tmp_path / "journey.pptx"
    presentation = Presentation()
    for title in ("Upload resume", "Download report"):
        slide = presentation.slides.add_slide(presentation.slide_layouts[5])
        title_shape = slide.shapes.title
        assert title_shape is not None
        title_shape.text = title
    presentation.save(str(pptx_path))

    xlsx_path = tmp_path / "rules.xlsx"
    workbook = Workbook()
    sheet = workbook.active
    assert sheet is not None
    sheet.title = "Upload rules"
    for row in (("Format", "Limit"), ("PDF", "10 MB"), ("DOCX", "10 MB")):
        sheet.append(row)
    workbook.save(xlsx_path)

    presentation_result = PptxExtractor().extract(pptx_path)
    workbook_result = XlsxExtractor().extract(xlsx_path)

    slide_text = "\n".join(unit.content_text or "" for unit in presentation_result.units)
    assert slide_text.index("Upload resume") < slide_text.index("Download report")
    assert presentation_result.coverage_complete
    assert all("Upload rules" in (unit.content_text or "") for unit in workbook_result.units)
    assert "10 MB" in "".join(unit.content_text or "" for unit in workbook_result.units)


async def test_dispatcher_and_image_model_configuration(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    text_path = tmp_path / "source.TXT"
    text_path.write_text("Users can upload a resume.", encoding="utf-8")
    assert (await extract_source(text_path)).units

    image_path = tmp_path / "screen.png"
    image_path.write_bytes(b"image bytes")
    response = ModelResponse(
        choices=[
            {
                "finish_reason": "stop",
                "message": {
                    "role": "assistant",
                    "content": json.dumps({"content": "Upload button", "warnings": []}),
                },
            }
        ]
    )
    completion = AsyncMock(return_value=response)
    monkeypatch.setattr("markettwin_knowledge_worker.extraction.image.acompletion", completion)
    monkeypatch.setenv("KNOWLEDGE_MODEL_TIMEOUT_SECONDS", "123")
    monkeypatch.setenv("KNOWLEDGE_MODEL_NUM_RETRIES", "2")

    result = await ImageExtractor().extract(image_path)

    assert result.units[0].content_text == "Upload button"
    assert completion.call_args.kwargs["timeout"] == 123
    assert completion.call_args.kwargs["num_retries"] == 2


async def test_video_coverage_counts_only_successful_clips(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    path = tmp_path / "demo.mp4"
    path.write_bytes(b"video")
    extractor = VideoExtractor()
    clips = (
        VideoClip(path, 0.0, 90.0),
        VideoClip(path, 85.0, 120.0),
    )
    monkeypatch.setenv("VIDEO_MODEL_NAME", "openai/test")

    def duration_seconds(_path: Path) -> float:
        return 120.0

    monkeypatch.setattr(extractor, "_duration_seconds", duration_seconds)
    monkeypatch.setattr(extractor, "_prepare_clips", AsyncMock(return_value=clips))
    monkeypatch.setattr(
        extractor,
        "_understand_clip",
        AsyncMock(
            side_effect=[
                VideoClipUnderstanding(content="User uploads a PDF."),
                RuntimeError("model failed"),
            ]
        ),
    )

    result = await extractor.extract(path)

    assert result.source_item_count == 2
    assert result.processed_item_count == 1
    assert not result.coverage_complete
    assert result.issues[-1].code == "video_understanding_failed"
