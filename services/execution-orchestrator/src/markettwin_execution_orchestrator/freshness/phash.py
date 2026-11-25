"""screenshot_phash: ahash-64 over the tier-2 capture's PNG bytes.

Doc 23 section 4.1: an 8x8 average hash — decode the PNG, reduce to
an 8x8 grayscale grid, mark each cell 1 when it is brighter than the
grid's mean, and read the 64 bits as 16 hex digits. Stored
algorithm-prefixed (``"ahash:<hex>"``) so a true DCT pHash can drop
in behind the prefix later (decision D4). The value is a similarity
signal only — never a change verdict; ``visual_distance`` (the
Hamming distance between two ahash-64 values) is reported in outcome
detail for exactly that reason.

PNG decoding uses Pillow when the orchestrator's environment carries
it and falls back to a minimal stdlib decoder (8-bit, non-interlaced,
colour types 0/2/3/4/6 — the shapes Playwright emits) so the sweep
never depends on an imaging stack being present.
"""

from __future__ import annotations

import io
import struct
import zlib

AHASH_ALGORITHM = "ahash"
_GRID = 8


def _gray_grid(pixels: list[list[int]]) -> list[int]:
    """64 cell means of an 8x8 grid over a grayscale pixel matrix."""

    height = len(pixels)
    width = len(pixels[0]) if height else 0
    if not height or not width:
        return []
    cells: list[int] = []
    for gy in range(_GRID):
        y0 = gy * height // _GRID
        y1 = max(y0 + 1, (gy + 1) * height // _GRID)
        for gx in range(_GRID):
            x0 = gx * width // _GRID
            x1 = max(x0 + 1, (gx + 1) * width // _GRID)
            total = 0
            count = 0
            for y in range(y0, min(y1, height)):
                row = pixels[y]
                for x in range(x0, min(x1, width)):
                    total += row[x]
                    count += 1
            cells.append(total // count if count else 0)
    return cells


def ahash64_from_gray(pixels: list[list[int]]) -> str | None:
    """The ``ahash:<hex>`` value for a grayscale pixel matrix."""

    cells = _gray_grid(pixels)
    if len(cells) != _GRID * _GRID:
        return None
    mean = sum(cells) / len(cells)
    bits = 0
    for cell in cells:
        bits = (bits << 1) | (1 if cell > mean else 0)
    return f"{AHASH_ALGORITHM}:{bits:016x}"


def _decode_png_gray_pillow(data: bytes) -> list[list[int]] | None:
    try:
        from PIL import Image
    except ImportError:
        return None
    try:
        with Image.open(io.BytesIO(data)) as image:
            gray = image.convert("L")
            width, height = gray.size
            raw = gray.tobytes()
    except (OSError, ValueError):
        return None
    return [list(raw[y * width:(y + 1) * width]) for y in range(height)]


def _decode_png_gray_stdlib(data: bytes) -> list[list[int]] | None:
    """Minimal PNG decoder: 8-bit, non-interlaced, colour types 0/2/3/4/6."""

    if not data.startswith(b"\x89PNG\r\n\x1a\n"):
        return None
    pos = 8
    idat = bytearray()
    palette: list[tuple[int, int, int]] = []
    transparency: bytes = b""
    width = height = bit_depth = colour_type = interlace = None
    while pos + 8 <= len(data):
        length = struct.unpack(">I", data[pos:pos + 4])[0]
        kind = data[pos + 4:pos + 8]
        chunk = data[pos + 8:pos + 8 + length]
        pos += 12 + length
        if kind == b"IHDR":
            (width, height, bit_depth, colour_type, _comp, _filt,
             interlace) = struct.unpack(">IIBBBBB", chunk)
        elif kind == b"PLTE":
            palette = [tuple(chunk[i:i + 3]) for i in range(0, len(chunk), 3)]
        elif kind == b"tRNS":
            transparency = chunk
        elif kind == b"IDAT":
            idat.extend(chunk)
        elif kind == b"IEND":
            break
    if width is None or bit_depth != 8 or interlace != 0:
        return None
    channels = {0: 1, 2: 3, 3: 1, 4: 2, 6: 4}.get(colour_type or -1)
    if channels is None:
        return None
    try:
        raw = zlib.decompress(bytes(idat))
    except zlib.error:
        return None
    stride = width * channels
    rows: list[list[int]] = []
    prev = bytearray(stride)
    offset = 0
    for _y in range(height or 0):
        if offset + 1 + stride > len(raw):
            return None
        filter_type = raw[offset]
        line = bytearray(raw[offset + 1:offset + 1 + stride])
        offset += 1 + stride
        for i in range(stride):
            left = line[i - channels] if i >= channels else 0
            up = prev[i]
            up_left = prev[i - channels] if i >= channels else 0
            if filter_type == 1:
                line[i] = (line[i] + left) & 0xFF
            elif filter_type == 2:
                line[i] = (line[i] + up) & 0xFF
            elif filter_type == 3:
                line[i] = (line[i] + (left + up) // 2) & 0xFF
            elif filter_type == 4:
                p = left + up - up_left
                pa, pb, pc = abs(p - left), abs(p - up), abs(p - up_left)
                predictor = left if (pa <= pb and pa <= pc) else (up if pb <= pc else up_left)
                line[i] = (line[i] + predictor) & 0xFF
            elif filter_type != 0:
                return None
        prev = line
        gray_row: list[int] = []
        for x in range(width or 0):
            base = x * channels
            if colour_type == 0:
                gray_row.append(line[base])
            elif colour_type == 3:
                index = line[base]
                if index >= len(palette):
                    return None
                r, g, b = palette[index]
                gray_row.append((r * 299 + g * 587 + b * 114) // 1000)
            elif colour_type in (2, 6):
                r, g, b = line[base], line[base + 1], line[base + 2]
                gray_row.append((r * 299 + g * 587 + b * 114) // 1000)
            else:  # colour_type == 4: gray + alpha
                gray_row.append(line[base])
        rows.append(gray_row)
    return rows


def screenshot_phash(png_bytes: bytes) -> str | None:
    """The stored ``screenshot_phash`` value for one capture's PNG.

    ``None`` when the bytes cannot be decoded — an unreadable
    screenshot is "no comparable hash", never a job failure.
    """

    if not png_bytes:
        return None
    pixels = _decode_png_gray_pillow(png_bytes)
    if pixels is None:
        try:
            pixels = _decode_png_gray_stdlib(png_bytes)
        except (struct.error, IndexError, OverflowError, ValueError):
            # A malformed chunk layout is "cannot decode" (ORC1-03),
            # never a job failure: the contract above stands.
            pixels = None
    if pixels is None:
        return None
    return ahash64_from_gray(pixels)


def visual_distance(recorded: object, live: object) -> int | None:
    """Hamming distance between two stored phash values (doc 23 §4.1).

    ``None`` when either side is missing, malformed, a different
    algorithm, or a different bit length — incomparable, not zero.
    """

    from markettwin_shared.app_map_common import parse_screenshot_phash

    left = parse_screenshot_phash(recorded)
    right = parse_screenshot_phash(live)
    if left is None or right is None:
        return None
    if left[0] != right[0] or len(left[1]) != len(right[1]):
        return None
    try:
        differing = int(left[1], 16) ^ int(right[1], 16)
    except ValueError:
        return None
    return bin(differing).count("1")
