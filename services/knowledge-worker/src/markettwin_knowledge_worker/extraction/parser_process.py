"""Private document parser entry point; never invoked as a network service."""

import json
import os
import subprocess
import sys
from dataclasses import asdict
from pathlib import Path
from zipfile import ZipFile


def _limit_windows_resources(*, memory_bytes: int = 2 * 1024**3, cpu_seconds: float = 45) -> int:
    """Assign this child to a bounded job before importing native document parsers.

    The returned handle must remain open until process exit. Job setup failure
    aborts parsing, including when a host job prohibits nested assignment.
    """
    import ctypes
    from ctypes import wintypes

    class BasicLimits(ctypes.Structure):
        _fields_ = [
            ("process_time", ctypes.c_longlong), ("job_time", ctypes.c_longlong),
            ("flags", wintypes.DWORD), ("minimum_working_set", ctypes.c_size_t),
            ("maximum_working_set", ctypes.c_size_t), ("active_processes", wintypes.DWORD),
            ("affinity", ctypes.c_size_t), ("priority", wintypes.DWORD),
            ("scheduling", wintypes.DWORD),
        ]

    class IoCounters(ctypes.Structure):
        _fields_ = [
            (name, ctypes.c_ulonglong) for name in (
                "read_operations", "write_operations", "other_operations",
                "read_bytes", "write_bytes", "other_bytes",
            )
        ]

    class ExtendedLimits(ctypes.Structure):
        _fields_ = [
            ("basic", BasicLimits), ("io", IoCounters),
            ("process_memory", ctypes.c_size_t), ("job_memory", ctypes.c_size_t),
            ("peak_process_memory", ctypes.c_size_t), ("peak_job_memory", ctypes.c_size_t),
        ]

    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel.CreateJobObjectW.argtypes = [ctypes.c_void_p, wintypes.LPCWSTR]
    kernel.CreateJobObjectW.restype = wintypes.HANDLE
    kernel.SetInformationJobObject.argtypes = [
        wintypes.HANDLE, ctypes.c_int, ctypes.c_void_p, wintypes.DWORD,
    ]
    kernel.SetInformationJobObject.restype = wintypes.BOOL
    kernel.GetCurrentProcess.argtypes = []
    kernel.GetCurrentProcess.restype = wintypes.HANDLE
    kernel.AssignProcessToJobObject.argtypes = [wintypes.HANDLE, wintypes.HANDLE]
    kernel.AssignProcessToJobObject.restype = wintypes.BOOL
    kernel.CloseHandle.argtypes = [wintypes.HANDLE]
    kernel.CloseHandle.restype = wintypes.BOOL
    job = kernel.CreateJobObjectW(None, None)
    if not job:
        raise ctypes.WinError(ctypes.get_last_error())
    limits = ExtendedLimits()
    # PROCESS_TIME | PROCESS_MEMORY | KILL_ON_JOB_CLOSE.
    limits.basic.flags = 0x00000002 | 0x00000100 | 0x00002000
    limits.basic.process_time = int(cpu_seconds * 10_000_000)
    limits.process_memory = memory_bytes
    if not kernel.SetInformationJobObject(job, 9, ctypes.byref(limits), ctypes.sizeof(limits)):
        error = ctypes.get_last_error()
        kernel.CloseHandle(job)
        raise ctypes.WinError(error)
    if not kernel.AssignProcessToJobObject(job, kernel.GetCurrentProcess()):
        error = ctypes.get_last_error()
        kernel.CloseHandle(job)
        raise ctypes.WinError(error)
    return int(job)


def main() -> None:
    # A file entry point otherwise shadows python-docx with our own docx.py.
    sys.path.pop(0)
    source, destination = map(Path, sys.argv[1:3])
    operation = sys.argv[3] if len(sys.argv) > 3 else "document"
    # Keep a Windows job handle open for the entire child lifetime. Both
    # platforms fail closed if hard limits cannot be installed.
    if os.name == "nt":
        _job_handle = _limit_windows_resources()
    elif os.name == "posix":
        import resource

        resource.setrlimit(resource.RLIMIT_AS, (2 * 1024**3, 2 * 1024**3))
        resource.setrlimit(resource.RLIMIT_CPU, (45, 45))
        file_limit = (128 if operation == "clip" else 16) * 1024**2
        resource.setrlimit(resource.RLIMIT_FSIZE, (file_limit, file_limit))

    if operation == "duration":
        import av

        with av.open(str(source)) as container:
            if container.duration is not None:
                duration = float(container.duration / av.time_base)
            else:
                duration = max((
                    float(stream.duration * stream.time_base)
                    for stream in container.streams
                    if stream.duration is not None and stream.time_base is not None
                ), default=0.0)
        destination.write_text(json.dumps(duration), encoding="utf-8")
        return
    if operation == "clip":
        ffmpeg, start, end = sys.argv[4:]
        result = subprocess.run(
            [
                ffmpeg, "-hide_banner", "-loglevel", "error", "-nostdin",
                "-ss", f"{float(start):.3f}", "-i", str(source),
                "-t", f"{float(end) - float(start):.3f}",
                "-map", "0:v:0?", "-map", "0:a:0?", "-c:v", "libx264",
                "-preset", "veryfast", "-crf", "23", "-c:a", "aac", "-b:a", "96k",
                "-movflags", "+faststart", "-fs", str(128 * 1024**2), "-y", str(destination),
            ],
            stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            check=False, timeout=110,
        )
        if result.returncode != 0 or not destination.is_file() or destination.stat().st_size == 0:
            raise ValueError("Video clipping failed.")
        if destination.stat().st_size >= 127 * 1024**2:
            raise ValueError("Video clip reached its output limit.")
        return
    if operation != "document":
        raise ValueError("Unsupported parser operation.")
    if source.suffix.lower() in {".docx", ".pptx", ".xlsx"}:
        with ZipFile(source) as archive:
            entries = archive.infolist()
            if len(entries) > 10000 or sum(item.file_size for item in entries) > 100 * 1024**2:
                raise ValueError("Document archive expands beyond its extraction limit.")

    from markettwin_knowledge_worker.extraction.csv_file import CsvExtractor
    from markettwin_knowledge_worker.extraction.docx import DocxExtractor
    from markettwin_knowledge_worker.extraction.json_file import JsonExtractor
    from markettwin_knowledge_worker.extraction.pdf import PdfExtractor
    from markettwin_knowledge_worker.extraction.pptx import PptxExtractor
    from markettwin_knowledge_worker.extraction.text import TextExtractor
    from markettwin_knowledge_worker.extraction.xlsx import XlsxExtractor

    extractors = {
        ".csv": CsvExtractor, ".docx": DocxExtractor, ".json": JsonExtractor,
        ".pdf": PdfExtractor, ".pptx": PptxExtractor, ".txt": TextExtractor,
        ".md": TextExtractor, ".xlsx": XlsxExtractor,
    }
    result = extractors[source.suffix.lower()]().extract(source)
    payload = asdict(result)
    del payload["source_path"], payload["cleanup_paths"]
    encoded = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    if len(encoded) > 16 * 1024**2:
        raise ValueError("Document extraction result is too large.")
    destination.write_bytes(encoded)


if __name__ == "__main__":
    main()
