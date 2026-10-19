"""Native video operations are bounded and leave no running helper after cancellation."""

import asyncio
import os
import sys
from pathlib import Path

import av
import pytest
from markettwin_knowledge_worker.extraction import isolated
from markettwin_knowledge_worker.extraction.video import VideoExtractionError, VideoExtractor


@pytest.mark.asyncio
async def test_video_duration_uses_real_bounded_pyav_child(tmp_path: Path) -> None:
    source = tmp_path / "short.mp4"
    with av.open(str(source), "w") as container:
        stream = container.add_stream("mpeg4", rate=5)  # pyright: ignore[reportUnknownMemberType]
        stream.width = stream.height = 16
        stream.pix_fmt = "yuv420p"
        for _ in range(5):
            for packet in stream.encode(av.VideoFrame(16, 16, "yuv420p")):
                container.mux(packet)
        for packet in stream.encode():
            container.mux(packet)
    extraction = await VideoExtractor().extract(source)
    assert extraction.source_item_count == 1
    assert extraction.units[0].media_path == source
    end_seconds = extraction.units[0].source_locator["end_seconds"]
    assert isinstance(end_seconds, (int, float))
    assert 0.9 <= end_seconds <= 1.1
    assert extraction.cleanup_paths == ()


def test_video_duration_cannot_expand_into_unbounded_clip_ranges() -> None:
    with pytest.raises(VideoExtractionError, match="too many clips"):
        VideoExtractor()._clip_ranges(1e100)  # pyright: ignore[reportPrivateUsage]


@pytest.mark.skipif(os.name != "nt", reason="Windows nested Job Object descendant cleanup")
@pytest.mark.asyncio
@pytest.mark.parametrize("cancel", [False, True])
async def test_ffmpeg_timeout_and_cancellation_stop_native_descendants(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, cancel: bool,
) -> None:
    import ctypes
    from ctypes import wintypes

    marker = tmp_path / "native-pid.txt"
    helper = tmp_path / "fake_native.py"
    helper.write_text(
        "import os, pathlib, time\n"
        f"pathlib.Path({str(marker)!r}).write_text(str(os.getpid()))\n"
        "time.sleep(120)\n", encoding="utf-8",
    )
    ffmpeg = tmp_path / "fake_ffmpeg.cmd"
    ffmpeg.write_text(f'@"{sys.executable}" "{helper}"\n', encoding="utf-8")
    processes: list[asyncio.subprocess.Process] = []
    create_process = asyncio.create_subprocess_exec

    async def tracked_process(*args: object, **kwargs: object) -> asyncio.subprocess.Process:
        process = await create_process(*args, **kwargs)  # type: ignore[arg-type]
        processes.append(process)
        return process

    monkeypatch.setattr(asyncio, "create_subprocess_exec", tracked_process)
    monkeypatch.setattr(isolated, "VIDEO_CLIP_TIMEOUT_SECONDS", 10 if cancel else 3)
    task = asyncio.create_task(isolated.trim_video(
        str(ffmpeg), tmp_path / "source.mp4", tmp_path / "output.mp4", 0.0, 90.0,
    ))
    if cancel:
        async with asyncio.timeout(8):
            while not marker.exists():  # noqa: ASYNC110 - external native helper marker
                await asyncio.sleep(0.01)
        task.cancel()
    with pytest.raises(asyncio.CancelledError if cancel else TimeoutError):
        await task
    assert len(processes) == 1
    assert processes[0].returncode is not None
    assert marker.exists(), "Native helper must actually start before timeout/cancellation."

    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
    kernel.OpenProcess.restype = wintypes.HANDLE
    kernel.WaitForSingleObject.argtypes = [wintypes.HANDLE, wintypes.DWORD]
    kernel.WaitForSingleObject.restype = wintypes.DWORD
    kernel.CloseHandle.argtypes = [wintypes.HANDLE]
    kernel.CloseHandle.restype = wintypes.BOOL
    handle = kernel.OpenProcess(0x00100000, False, int(marker.read_text()))
    if handle:
        try:
            assert kernel.WaitForSingleObject(handle, 3000) == 0
        finally:
            kernel.CloseHandle(handle)
    else:
        assert ctypes.get_last_error() == 87  # PID already removed, ERROR_INVALID_PARAMETER.
