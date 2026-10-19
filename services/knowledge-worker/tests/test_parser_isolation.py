"""Untrusted documents cannot keep an unbounded parser alive after a request ends."""

import asyncio
import os
import sys
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile

import pytest
from markettwin_knowledge_worker.extraction import extract_source, isolated


@pytest.mark.asyncio
async def test_document_subprocess_preserves_evidence(tmp_path: Path) -> None:
    source = tmp_path / "requirements.md"
    source.write_text("# Upload\nOnly PDF files are supported.", encoding="utf-8")
    result = await extract_source(source)
    assert result.source_path == source
    assert "Only PDF" in "".join(unit.content_text or "" for unit in result.units)
    assert result.coverage_complete


@pytest.mark.asyncio
@pytest.mark.parametrize("cancel", [False, True])
async def test_hung_parser_is_killed_and_reaped(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, cancel: bool,
) -> None:
    script = tmp_path / "hung_parser.py"
    marker = tmp_path / "started"
    script.write_text(
        "import pathlib, time\n"
        f"pathlib.Path({str(marker)!r}).touch()\n"
        "time.sleep(120)\n", encoding="utf-8",
    )
    processes: list[asyncio.subprocess.Process] = []
    create_process = asyncio.create_subprocess_exec

    async def tracked_process(*args: object, **kwargs: object) -> asyncio.subprocess.Process:
        process = await create_process(*args, **kwargs)  # type: ignore[arg-type]
        processes.append(process)
        return process

    monkeypatch.setattr(isolated, "_PARSER_SCRIPT", script)
    monkeypatch.setattr(isolated, "PARSER_TIMEOUT_SECONDS", 2)
    monkeypatch.setattr(asyncio, "create_subprocess_exec", tracked_process)
    task = asyncio.create_task(isolated.extract_document(tmp_path / "source.txt"))
    if cancel:
        async with asyncio.timeout(5):
            while not marker.exists():  # noqa: ASYNC110 - external subprocess marker
                await asyncio.sleep(0.01)
        task.cancel()
    with pytest.raises(asyncio.CancelledError if cancel else TimeoutError):
        await task
    assert len(processes) == 1
    assert processes[0].returncode is not None


@pytest.mark.asyncio
async def test_compressed_document_expansion_is_rejected(tmp_path: Path) -> None:
    source = tmp_path / "bomb.docx"
    with ZipFile(source, "w", compression=ZIP_DEFLATED) as archive:
        archive.writestr("large.xml", b"x" * (101 * 1024**2))
    with pytest.raises(ValueError, match="resource limit"):
        await extract_source(source)


@pytest.mark.skipif(os.name != "nt", reason="Windows Job Object enforcement")
@pytest.mark.asyncio
async def test_windows_job_refuses_memory_above_limit() -> None:
    script = (
        "import runpy\n"
        f"scope = runpy.run_path({str(Path(isolated.__file__).with_name('parser_process.py'))!r})\n"
        "job = scope['_limit_windows_resources'](memory_bytes=64 * 1024**2)\n"
        "try:\n"
        "    allocation = bytearray(128 * 1024**2)\n"
        "except MemoryError:\n"
        "    print('memory-limited')\n"
        "else:\n"
        "    raise SystemExit('memory limit did not apply')\n"
    )
    process = await asyncio.create_subprocess_exec(
        sys.executable, "-c", script, stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    try:
        output, errors = await asyncio.wait_for(process.communicate(), timeout=10)
        assert process.returncode == 0, errors.decode(errors="replace")
        assert b"memory-limited" in output
    finally:
        if process.returncode is None:
            process.kill()
        await process.wait()


@pytest.mark.skipif(os.name != "nt", reason="Windows Job Object enforcement")
@pytest.mark.asyncio
async def test_windows_job_terminates_cpu_bound_parser() -> None:
    script = (
        "import runpy\n"
        f"scope = runpy.run_path({str(Path(isolated.__file__).with_name('parser_process.py'))!r})\n"
        "job = scope['_limit_windows_resources'](cpu_seconds=0.25)\n"
        "print('job-installed', flush=True)\n"
        "while True:\n"
        "    pass\n"
    )
    process = await asyncio.create_subprocess_exec(
        sys.executable, "-c", script, stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    try:
        output, errors = await asyncio.wait_for(process.communicate(), timeout=10)
        assert b"job-installed" in output, errors.decode(errors="replace")
        assert process.returncode != 0
    finally:
        if process.returncode is None:
            process.kill()
        await process.wait()
