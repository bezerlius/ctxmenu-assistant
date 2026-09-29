# -*- coding: utf-8 -*-
"""纯 ctypes 截屏（不依赖 PIL / .NET），截取整屏或指定区域。"""
import ctypes
import ctypes.wintypes as wt
import struct
import zlib
import sys

user32 = ctypes.windll.user32
gdi32 = ctypes.windll.gdi32


def grab(x, y, w, h, out_path):
    hwnd = user32.GetDesktopWindow()
    hdc = user32.GetWindowDC(hwnd)
    memdc = gdi32.CreateCompatibleDC(hdc)
    bmp = gdi32.CreateCompatibleBitmap(hdc, w, h)
    gdi32.SelectObject(memdc, bmp)

    # SRCCOPY | CAPTUREBLT
    gdi32.BitBlt(memdc, 0, 0, w, h, hdc, x, y, 0x00CC0020 | 0x40000000)

    class BITMAPINFOHEADER(ctypes.Structure):
        _fields_ = [("biSize", wt.DWORD), ("biWidth", wt.LONG),
                    ("biHeight", wt.LONG), ("biPlanes", wt.WORD),
                    ("biBitCount", wt.WORD), ("biCompression", wt.DWORD),
                    ("biSizeImage", wt.DWORD), ("biXPelsPerMeter", wt.LONG),
                    ("biYPelsPerMeter", wt.LONG), ("biClrUsed", wt.DWORD),
                    ("biClrImportant", wt.DWORD)]

    bi = BITMAPINFOHEADER()
    bi.biSize = ctypes.sizeof(BITMAPINFOHEADER)
    bi.biWidth = w
    bi.biHeight = -h          # 负数 = 自上而下
    bi.biPlanes = 1
    bi.biBitCount = 32
    bi.biCompression = 0      # BI_RGB

    bufsize = w * h * 4
    buf = ctypes.create_string_buffer(bufsize)
    gdi32.GetDIBits(memdc, bmp, 0, h, buf, ctypes.byref(bi), 0)

    gdi32.DeleteObject(bmp)
    gdi32.DeleteDC(memdc)
    user32.ReleaseDC(hwnd, hdc)

    # BGRA -> PNG RGBA
    rows = []
    data = buf.raw
    for yy in range(h):
        row = bytearray([0])
        base = yy * w * 4
        for xx in range(w):
            p = base + xx * 4
            row += bytes((data[p + 2], data[p + 1], data[p], 255))
        rows.append(bytes(row))
    raw = b"".join(rows)

    def chunk(t, d):
        return (struct.pack(">I", len(d)) + t + d
                + struct.pack(">I", zlib.crc32(t + d) & 0xffffffff))

    png = (b"\x89PNG\r\n\x1a\n"
           + chunk(b"IHDR", struct.pack(">IIBBBBB", w, h, 8, 6, 0, 0, 0))
           + chunk(b"IDAT", zlib.compress(raw, 6))
           + chunk(b"IEND", b""))
    with open(out_path, "wb") as f:
        f.write(png)
    return out_path


if __name__ == "__main__":
    x, y, w, h = (int(a) for a in sys.argv[1:5])
    out = sys.argv[5]
    print(grab(x, y, w, h, out))
