import ctypes
from typing import Tuple

from PIL import Image, ImageDraw, ImageGrab, ImageFont

_user32 = ctypes.windll.user32
SM_XVIRTUALSCREEN = 76
SM_YVIRTUALSCREEN = 77
SM_CXVIRTUALSCREEN = 78
SM_CYVIRTUALSCREEN = 79


def get_virtual_screen_rect() -> Tuple[int, int, int, int]:
    x = _user32.GetSystemMetrics(SM_XVIRTUALSCREEN)
    y = _user32.GetSystemMetrics(SM_YVIRTUALSCREEN)
    w = _user32.GetSystemMetrics(SM_CXVIRTUALSCREEN)
    h = _user32.GetSystemMetrics(SM_CYVIRTUALSCREEN)
    return x, y, w, h


def capture() -> Tuple[Image.Image, Tuple[int, int]]:
    x, y, w, h = get_virtual_screen_rect()
    if w <= 0 or h <= 0:
        return ImageGrab.grab(), (0, 0)
    img = ImageGrab.grab(bbox=(x, y, x + w, y + h))
    return img, (x, y)


def mark_click(image: Image.Image, screen_pos: Tuple[int, int],
               origin: Tuple[int, int], step_num: int) -> Image.Image:
    img = image.convert("RGBA")
    lx = screen_pos[0] - origin[0]
    ly = screen_pos[1] - origin[1]

    overlay = Image.new("RGBA", img.size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(overlay)

    radius = 28
    draw.ellipse(
        [lx - radius, ly - radius, lx + radius, ly + radius],
        fill=(255, 0, 0, 110),
        outline=(255, 0, 0, 255),
        width=3,
    )

    try:
        font = ImageFont.truetype("arial.ttf", 22)
    except Exception:
        font = ImageFont.load_default()

    draw.text(
        (lx, ly),
        str(step_num),
        fill=(255, 255, 255, 255),
        font=font,
        anchor="mm",
    )

    return Image.alpha_composite(img, overlay).convert("RGB")
