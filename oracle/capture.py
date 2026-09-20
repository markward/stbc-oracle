"""Screenshot the running BC window.

``Graphics.CopyFromScreen`` / BitBlt of the desktop shows the game's 3D scene
as solid black (the 16-bit D3D8 surface under the DWM8And16BitMitigation
layer is not part of the desktop composition it copies).  ``PrintWindow``
with ``PW_RENDERFULLCONTENT`` asks DWM for the composited window and does
capture the scene, the HUD and the menus alike.
"""
from __future__ import annotations

import ctypes
import ctypes.wintypes as wt
import struct
import zlib
from pathlib import Path

WINDOW_TITLE = "Bridge Commander"
PW_RENDERFULLCONTENT = 2


class _BITMAPINFOHEADER(ctypes.Structure):
    _fields_ = [("biSize", wt.DWORD), ("biWidth", wt.LONG), ("biHeight", wt.LONG),
                ("biPlanes", wt.WORD), ("biBitCount", wt.WORD), ("biCompression", wt.DWORD),
                ("biSizeImage", wt.DWORD), ("biXPelsPerMeter", wt.LONG),
                ("biYPelsPerMeter", wt.LONG), ("biClrUsed", wt.DWORD), ("biClrImportant", wt.DWORD)]


def _png(w: int, h: int, bgra: bytes) -> bytes:
    rows = bytearray()
    stride = w * 4
    for y in range(h):
        rows.append(0)
        row = bgra[y * stride:(y + 1) * stride]
        rows.extend(bytes(v for px in range(0, stride, 4) for v in (row[px + 2], row[px + 1], row[px])))

    def chunk(tag: bytes, data: bytes) -> bytes:
        return struct.pack(">I", len(data)) + tag + data + struct.pack(">I", zlib.crc32(tag + data) & 0xffffffff)
    return (b"\x89PNG\r\n\x1a\n"
            + chunk(b"IHDR", struct.pack(">IIBBBBB", w, h, 8, 2, 0, 0, 0))
            + chunk(b"IDAT", zlib.compress(bytes(rows), 6))
            + chunk(b"IEND", b""))


def capture(out: Path, title: str = WINDOW_TITLE) -> bool:
    """Write a PNG of the game window's client area; False if no window."""
    u, g = ctypes.windll.user32, ctypes.windll.gdi32
    hwnd = u.FindWindowW(None, title)
    if not hwnd:
        return False
    r = wt.RECT()
    u.GetClientRect(hwnd, ctypes.byref(r))
    w, h = r.right, r.bottom
    if w <= 0 or h <= 0:
        return False
    hdc = u.GetDC(0)
    mdc = g.CreateCompatibleDC(hdc)
    bmp = g.CreateCompatibleBitmap(hdc, w, h)
    old = g.SelectObject(mdc, bmp)
    try:
        u.PrintWindow(hwnd, mdc, PW_RENDERFULLCONTENT)
        bi = _BITMAPINFOHEADER()
        bi.biSize = ctypes.sizeof(bi)
        bi.biWidth, bi.biHeight, bi.biPlanes, bi.biBitCount = w, -h, 1, 32
        buf = ctypes.create_string_buffer(w * h * 4)
        g.GetDIBits(mdc, bmp, 0, h, buf, ctypes.byref(bi), 0)
        out.write_bytes(_png(w, h, buf.raw))
        return True
    finally:
        g.SelectObject(mdc, old)
        g.DeleteObject(bmp)
        g.DeleteDC(mdc)
        u.ReleaseDC(0, hdc)


if __name__ == "__main__":
    import sys
    dest = Path(sys.argv[1] if len(sys.argv) > 1 else "bc_capture.png")
    print("captured" if capture(dest) else "no window", dest)
