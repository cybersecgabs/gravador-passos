import ctypes
from ctypes import wintypes
from typing import List, Optional, Tuple

from PIL import Image, ImageDraw, ImageGrab, ImageFont

_user32 = ctypes.windll.user32
SM_XVIRTUALSCREEN = 76
SM_YVIRTUALSCREEN = 77
SM_CXVIRTUALSCREEN = 78
SM_CYVIRTUALSCREEN = 79

_user32.GetSystemMetrics.restype = ctypes.c_int
_user32.GetSystemMetrics.argtypes = [ctypes.c_int]

_user32.WindowFromPoint.restype = wintypes.HWND
_user32.WindowFromPoint.argtypes = [wintypes.POINT]

_user32.GetParent.restype = wintypes.HWND
_user32.GetParent.argtypes = [wintypes.HWND]

_user32.GetWindowRect.restype = wintypes.BOOL
_user32.GetWindowRect.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.RECT)]

_user32.GetWindowTextW.restype = ctypes.c_int
_user32.GetWindowTextW.argtypes = [wintypes.HWND, wintypes.LPWSTR, ctypes.c_int]

_user32.IsWindowVisible.restype = wintypes.BOOL
_user32.IsWindowVisible.argtypes = [wintypes.HWND]

_user32.IsIconic.restype = wintypes.BOOL
_user32.IsIconic.argtypes = [wintypes.HWND]

WNDENUMPROC = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
_user32.EnumWindows.restype = wintypes.BOOL
_user32.EnumWindows.argtypes = [WNDENUMPROC, wintypes.LPARAM]


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


def get_window_title(hwnd: int) -> str:
    buf = ctypes.create_unicode_buffer(256)
    _user32.GetWindowTextW(hwnd, buf, 256)
    return buf.value


def _get_top_level(hwnd: int) -> int:
    while True:
        parent = _user32.GetParent(hwnd)
        if not parent:
            break
        hwnd = parent
    return hwnd


def get_window_under_cursor(x: int, y: int) -> Optional[int]:
    point = wintypes.POINT(x, y)
    hwnd = _user32.WindowFromPoint(point)
    if not hwnd:
        return None
    return _get_top_level(hwnd)


def capture_window(hwnd: int) -> Optional[Tuple[Image.Image, Tuple[int, int]]]:
    if _user32.IsIconic(hwnd):
        return None
    rect = wintypes.RECT()
    if not _user32.GetWindowRect(hwnd, ctypes.byref(rect)):
        return None
    if rect.right <= rect.left or rect.bottom <= rect.top:
        return None

    vs_x, vs_y, vs_w, vs_h = get_virtual_screen_rect()
    left = max(rect.left, vs_x)
    top = max(rect.top, vs_y)
    right = min(rect.right, vs_x + vs_w)
    bottom = min(rect.bottom, vs_y + vs_h)
    if right <= left or bottom <= top:
        return None

    img = ImageGrab.grab(bbox=(left, top, right, bottom))
    return img, (left, top)


def enumerate_windows() -> List[Tuple[int, str]]:
    results: List[Tuple[int, str]] = []

    @WNDENUMPROC
    def callback(hwnd, _lparam):
        if _user32.IsWindowVisible(hwnd) and not _user32.IsIconic(hwnd):
            title = get_window_title(hwnd)
            if title:
                results.append((hwnd, title))
        return True

    _user32.EnumWindows(callback, 0)
    return results


def capture_for_mode(mode: str,
                     click_pos: Optional[Tuple[int, int]] = None,
                     target_hwnd: Optional[int] = None
                     ) -> Tuple[Image.Image, Tuple[int, int]]:
    if mode == "window_under_cursor" and click_pos:
        hwnd = get_window_under_cursor(*click_pos)
        if hwnd:
            result = capture_window(hwnd)
            if result:
                return result
    elif mode == "window_specific" and target_hwnd:
        result = capture_window(target_hwnd)
        if result:
            return result
    return capture()


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
