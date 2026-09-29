# -*- coding: utf-8 -*-
"""
make_icon.py —— 纯 Python 生成应用图标 app.ico

设计：圆角方形蓝色底 + 白色鼠标指针 + 三条菜单线，直观表达"右键菜单"。
不依赖 PIL，手写 ICO(多尺寸) 与 BMP 数据。
"""

import os
import struct

SIZES = [16, 24, 32, 48, 64, 128, 256]

# 配色
BG_TOP = (63, 132, 245)      # 蓝色上
BG_BOT = (37, 89, 196)       # 蓝色下
WHITE = (255, 255, 255)
SHADOW = (22, 55, 130)


def _blend(c1, c2, t):
    return tuple(int(c1[i] + (c2[i] - c1[i]) * t) for i in range(3))


def _rounded_mask(size: int, radius_ratio: float = 0.22):
    """返回 rounded 矩形的覆盖率函数（0~1），用于抗锯齿。"""
    r = size * radius_ratio

    def cov(x: float, y: float) -> float:
        # 到圆角矩形的距离，简化用 4 个角做圆形裁剪
        cx = min(max(x, r), size - r)
        cy = min(max(y, r), size - r)
        d = ((x - cx) ** 2 + (y - cy) ** 2) ** 0.5
        # 1px 过渡做抗锯齿
        return max(0.0, min(1.0, r - d + 0.5))

    return cov


def _draw_size(size: int) -> list[tuple[int, int, int, int]]:
    """
    画一个尺寸，返回 BGRA 像素列表（用于 32bit ICO）。
    采用超采样 3x3 抗锯齿。
    """
    SS = 3
    cov = _rounded_mask(size)
    px = [[(0, 0, 0, 0) for _ in range(size)] for _ in range(size)]

    # 指针形状与菜单线，用归一化坐标定义（0~1）
    # 鼠标指针多边形
    cursor_poly = [
        (0.26, 0.20), (0.26, 0.72), (0.38, 0.60),
        (0.47, 0.82), (0.57, 0.77), (0.48, 0.56),
        (0.64, 0.54),
    ]
    # 菜单三条线: (x1, x2, y)，等长排布更像菜单列表
    menu_lines = [(0.58, 0.88, 0.22), (0.58, 0.88, 0.35), (0.58, 0.88, 0.48)]

    def point_in_poly(x, y, poly):
        inside = False
        n = len(poly)
        j = n - 1
        for i in range(n):
            xi, yi = poly[i]
            xj, yj = poly[j]
            if ((yi > y) != (yj > y)) and \
               (x < (xj - xi) * (y - yi) / (yj - yi + 1e-12) + xi):
                inside = not inside
            j = i
        return inside

    for py in range(size):
        for pxx in range(size):
            alpha_acc = 0
            r_acc = g_acc = b_acc = 0
            for sy in range(SS):
                for sx in range(SS):
                    fx = (pxx + (sx + 0.5) / SS) / size
                    fy = (py + (sy + 0.5) / SS) / size
                    # 背景
                    a = cov(fx * size, fy * size)
                    if a <= 0:
                        continue
                    col = _blend(BG_TOP, BG_BOT, fy)
                    # 菜单线（白色）
                    on_menu = False
                    for (x1, x2, yy) in menu_lines:
                        ly = yy
                        lh = 0.045
                        if x1 <= fx <= x2 and abs(fy - ly) < lh:
                            on_menu = True
                    # 指针（白色 + 深色描边）
                    on_cur = point_in_poly(fx, fy, cursor_poly)
                    if on_menu or on_cur:
                        col = WHITE
                    r_acc += col[0]
                    g_acc += col[1]
                    b_acc += col[2]
                    alpha_acc += 1
            total = SS * SS
            if alpha_acc == 0:
                px[py][pxx] = (0, 0, 0, 0)
            else:
                # 覆盖率决定整体 alpha
                a = int(255 * alpha_acc / total * cov(pxx + 0.5, py + 0.5))
                px[py][pxx] = (
                    b_acc // alpha_acc, g_acc // alpha_acc, r_acc // alpha_acc, a
                )
    return px


def _bmp_bytes(px, size: int) -> bytes:
    """把像素转成 ICO 内的 BMP 数据（BITMAPINFOHEADER + BGRA，含 AND 掩码）。"""
    out = bytearray()
    # BITMAPINFOHEADER: 高度写两倍
    out += struct.pack("<IiiHHIIiiII", 40, size, size * 2, 1, 32, 0,
                       size * size * 4, 0, 0, 0, 0)
    # 像素自下而上
    for y in range(size - 1, -1, -1):
        for x in range(size):
            b, g, r, a = px[y][x]
            out += bytes((b, g, r, a))
    # AND 掩码（每行 4 字节对齐），全透明处为 1
    row_bytes = ((size + 31) // 32) * 4
    for y in range(size - 1, -1, -1):
        bits = bytearray(row_bytes)
        for x in range(size):
            if px[y][x][3] < 128:
                bits[x // 8] |= (0x80 >> (x % 8))
        out += bits
    return bytes(out)


def build_ico(path: str) -> None:
    images = []
    for s in SIZES:
        px = _draw_size(s)
        images.append((s, _bmp_bytes(px, s)))

    n = len(images)
    header = struct.pack("<HHH", 0, 1, n)
    offset = 6 + 16 * n
    entries = bytearray()
    data = bytearray()
    for s, blob in images:
        w = 0 if s >= 256 else s
        h = 0 if s >= 256 else s
        entries += struct.pack("<BBBBHHII", w, h, 0, 0, 1, 32,
                               len(blob), offset)
        data += blob
        offset += len(blob)

    with open(path, "wb") as f:
        f.write(header)
        f.write(entries)
        f.write(data)


if __name__ == "__main__":
    here = os.path.dirname(os.path.abspath(__file__))
    out = os.path.join(here, "app.ico")
    build_ico(out)
    print(f"图标已生成：{out} （{os.path.getsize(out)} bytes，{len(SIZES)} 种尺寸）")
