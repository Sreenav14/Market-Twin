"""Annotate volatile viewer frames without changing the page or saved evidence."""

from dataclasses import dataclass
from io import BytesIO
from time import monotonic

from PIL import Image, ImageDraw

ACTION_LABEL_SECONDS = 3


@dataclass(frozen=True)
class LiveClickTarget:
    x: float
    y: float
    width: int
    height: int
    url: str
    observed_at: float


def annotate_live_target(frame: bytes, target: LiveClickTarget | None, page_url: str) -> bytes:
    """Draw the agent's last pointer position; label it only right after an action."""
    if (target is None or target.width <= 0 or target.height <= 0
            or not (0 <= target.x < target.width and 0 <= target.y < target.height)):
        return frame
    with Image.open(BytesIO(frame)) as source:
        image = source.convert("RGB")
    x = round(target.x * image.width / target.width)
    y = round(target.y * image.height / target.height)
    draw = ImageDraw.Draw(image)
    draw.polygon([(x, y), (x + 7, y + 26), (x + 12, y + 18), (x + 22, y + 19)],
                 fill="#e11d48", outline="white", width=2)
    if target.url == page_url and monotonic() - target.observed_at <= ACTION_LABEL_SECONDS:
        left = max(0, min(x + 24, image.width - 100))
        top = max(0, min(y + 20, image.height - 24))
        draw.rounded_rectangle((left, top, left + 96, top + 22), radius=3, fill="#171717")
        draw.text((left + 6, top + 4), "Agent action", fill="white")
    output = BytesIO()
    image.save(output, format="JPEG", quality=80)
    return output.getvalue()
