"""用标准库生成应用图标 assets/app.ico（多尺寸 32bpp DIB，无第三方依赖）。

图案：深色圆角底 + 2x2 插件方块，其中一块用强调色 —— 表达"宿主 + 可插拔模块"。
"""
from __future__ import annotations

import struct
from pathlib import Path

SIZES = (16, 24, 32, 48, 64, 128, 256)
SS = 4  # 超采样倍数，用于抗锯齿

BG_TOP = (34, 48, 68)
BG_BOTTOM = (18, 26, 38)
TILE_LIGHT = (232, 238, 248)
TILE_ACCENT = (232, 131, 58)


def _inside_round_rect(x: float, y: float, x0: float, y0: float, x1: float, y1: float, r: float) -> bool:
    if x < x0 or x > x1 or y < y0 or y > y1:
        return False
    cx = min(max(x, x0 + r), x1 - r)
    cy = min(max(y, y0 + r), y1 - r)
    return (x - cx) ** 2 + (y - cy) ** 2 <= r * r


def _render(size: int) -> list[list[tuple[int, int, int, int]]]:
    """返回 size x size 的 RGBA 像素（自上而下）。"""
    big = size * SS
    canvas = [[(0, 0, 0, 0)] * big for _ in range(big)]

    radius = big * 0.22
    for y in range(big):
        ratio = y / max(1, big - 1)
        bg = tuple(
            int(BG_TOP[i] + (BG_BOTTOM[i] - BG_TOP[i]) * ratio) for i in range(3)
        )
        for x in range(big):
            if _inside_round_rect(x + 0.5, y + 0.5, 0, 0, big, big, radius):
                canvas[y][x] = (*bg, 255)

    margin = big * 0.20
    gap = big * 0.06
    tile = (big - margin * 2 - gap) / 2
    tile_radius = tile * 0.24
    tiles = [
        (margin, margin, TILE_ACCENT),
        (margin + tile + gap, margin, TILE_LIGHT),
        (margin, margin + tile + gap, TILE_LIGHT),
        (margin + tile + gap, margin + tile + gap, TILE_LIGHT),
    ]
    for origin_x, origin_y, color in tiles:
        for y in range(int(origin_y), int(origin_y + tile) + 1):
            for x in range(int(origin_x), int(origin_x + tile) + 1):
                if y >= big or x >= big:
                    continue
                if _inside_round_rect(
                    x + 0.5, y + 0.5,
                    origin_x, origin_y, origin_x + tile, origin_y + tile, tile_radius,
                ):
                    canvas[y][x] = (*color, 255)

    # 盒式下采样
    result: list[list[tuple[int, int, int, int]]] = []
    for y in range(size):
        row: list[tuple[int, int, int, int]] = []
        for x in range(size):
            r = g = b = a = 0
            for dy in range(SS):
                for dx in range(SS):
                    pr, pg, pb, pa = canvas[y * SS + dy][x * SS + dx]
                    r += pr * pa
                    g += pg * pa
                    b += pb * pa
                    a += pa
            if a == 0:
                row.append((0, 0, 0, 0))
            else:
                row.append((r // a, g // a, b // a, a // (SS * SS)))
        result.append(row)
    return result


def _dib(pixels: list[list[tuple[int, int, int, int]]]) -> bytes:
    size = len(pixels)
    header = struct.pack(
        "<IiiHHIIiiII",
        40, size, size * 2, 1, 32, 0, 0, 0, 0, 0, 0,
    )
    body = bytearray()
    for y in range(size - 1, -1, -1):  # DIB 自下而上
        for x in range(size):
            r, g, b, a = pixels[y][x]
            body += bytes((b, g, r, a))
    mask_row = ((size + 31) // 32) * 4
    body += b"\x00" * (mask_row * size)
    return header + bytes(body)


def build(destination: Path) -> Path:
    images = [(size, _dib(_render(size))) for size in SIZES]
    offset = 6 + 16 * len(images)
    directory = bytearray(struct.pack("<HHH", 0, 1, len(images)))
    payload = bytearray()
    for size, data in images:
        directory += struct.pack(
            "<BBBBHHII",
            size if size < 256 else 0,
            size if size < 256 else 0,
            0, 0, 1, 32, len(data), offset,
        )
        payload += data
        offset += len(data)
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_bytes(bytes(directory) + bytes(payload))
    return destination


if __name__ == "__main__":
    root = Path(__file__).resolve().parents[1]
    path = build(root / "assets" / "app.ico")
    print(f"ICON {path} ({path.stat().st_size} bytes, sizes={SIZES})")
