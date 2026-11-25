from __future__ import annotations

import base64
import io
import math
import xml.sax.saxutils as xml_escape
from dataclasses import dataclass
from typing import Any

import cv2
import numpy as np
import segno
from PIL import Image, ImageDraw, ImageFilter, ImageFont

from .pokemon_catalog import get_palette_for_types

NEON_PALETTES: dict[str, dict[str, Any]] = {
    "synthwave": {
        "skyStops": ("#060214", "#260846", "#6b1263"),
        "sunStops": ("#fef08a", "#fb7185", "#c026d3"),
        "floorStops": ("#2b0848", "#060212"),
        "gridColor": "#e879f9",
        "mountainColor": "#090318",
        "tileColor": "#f5a3e0",
        "tileGlow": "#ec4899",
        "eyeBright": "#f472b6",
        "eyeDark": "#080316",
    },
    "cyber": {
        "skyStops": ("#020617", "#0f172a", "#164e63"),
        "sunStops": ("#cffafe", "#38bdf8", "#6366f1"),
        "floorStops": ("#0f2942", "#020617"),
        "gridColor": "#22d3ee",
        "mountainColor": "#030b1a",
        "tileColor": "#a5f3fc",
        "tileGlow": "#06b6d4",
        "eyeBright": "#38bdf8",
        "eyeDark": "#020617",
    },
    "inferno": {
        "skyStops": ("#090205", "#3b0712", "#7c2d12"),
        "sunStops": ("#fef08a", "#fb923c", "#dc2626"),
        "floorStops": ("#450a0a", "#090205"),
        "gridColor": "#fb923c",
        "mountainColor": "#120307",
        "tileColor": "#fed7aa",
        "tileGlow": "#ea580c",
        "eyeBright": "#fb923c",
        "eyeDark": "#090205",
    },
    "aurora": {
        "skyStops": ("#030212", "#171544", "#2e1065"),
        "sunStops": ("#a7f3d0", "#38bdf8", "#a855f7"),
        "floorStops": ("#1e1b4b", "#030212"),
        "gridColor": "#a78bfa",
        "mountainColor": "#07051c",
        "tileColor": "#ddd6fe",
        "tileGlow": "#8b5cf6",
        "eyeBright": "#c4b5fd",
        "eyeDark": "#040314",
    },
    "ocean": {
        "skyStops": ("#020817", "#0c2444", "#0e4d64"),
        "sunStops": ("#e0f2fe", "#38bdf8", "#0284c7"),
        "floorStops": ("#082f49", "#020817"),
        "gridColor": "#38bdf8",
        "mountainColor": "#031224",
        "tileColor": "#bae6fd",
        "tileGlow": "#0ea5e9",
        "eyeBright": "#7dd3fc",
        "eyeDark": "#020817",
    },
}

ALIGNMENT_COORDS: dict[int, list[int]] = {
    2: [6, 18],
    3: [6, 22],
    4: [6, 26],
    5: [6, 30],
    6: [6, 34],
    7: [6, 22, 38],
    8: [6, 24, 42],
    9: [6, 26, 46],
    10: [6, 28, 50],
    11: [6, 30, 54],
    12: [6, 32, 58],
    13: [6, 34, 62],
    14: [6, 26, 46, 66],
    15: [6, 26, 48, 70],
}


@dataclass
class QrStyleOptions:
    mode: str = "pixelart"
    module_shape: str = "rounded"
    eye_shape: str = "pokeball"
    ec_level: str = "H"
    fg_color: str = "#1e1b4b"
    fg_secondary_color: str = "#b45309"
    use_gradient: bool = True
    bg_color: str = "#fefce8"
    eye_color: str = "#d97706"
    badge_size_ratio: float = 0.22
    badge_shape: str = "pokeball"
    halftone_intensity: float = 0.65
    backdrop_opacity: float = 0.30
    pixel_sprite_scale: float = 0.38
    pixel_safe_dots: bool = True
    neon_theme: str = "synthwave"
    neon_glow_strength: float = 0.75
    neon_inverted: bool = True
    quiet_zone_modules: int = 3
    include_card_frame: bool = False
    card_headline: str = "Scan to Open PokéDrop"
    card_subtitle: str = "Shared via PokéQR2 (Python)"


def hex_to_rgb(hex_color: str) -> tuple[int, int, int]:
    clean = hex_color.strip().lstrip("#")
    if len(clean) == 3:
        clean = "".join(c * 2 for c in clean)
    clean = (clean + "000000")[:6]
    try:
        return int(clean[0:2], 16), int(clean[2:4], 16), int(clean[4:6], 16)
    except ValueError:
        return (0, 0, 0)


def hex_to_rgba(hex_color: str, alpha: int = 255) -> tuple[int, int, int, int]:
    r, g, b = hex_to_rgb(hex_color)
    return (r, g, b, alpha)


def _relative_luminance(rgb: tuple[int, int, int]) -> float:
    def linear(c: int) -> float:
        s = c / 255.0
        return s / 12.92 if s <= 0.03928 else ((s + 0.055) / 1.055) ** 2.4

    return 0.2126 * linear(rgb[0]) + 0.7152 * linear(rgb[1]) + 0.0722 * linear(rgb[2])


def compute_contrast_ratio(hex_a: str, hex_b: str) -> float:
    la = _relative_luminance(hex_to_rgb(hex_a))
    lb = _relative_luminance(hex_to_rgb(hex_b))
    bright, dark = max(la, lb), min(la, lb)
    return round((bright + 0.05) / (dark + 0.05), 2)


def get_neon_palette(theme: str, pokemon_types: list[str] | None) -> dict[str, Any]:
    if theme in NEON_PALETTES:
        return NEON_PALETTES[theme]
    tp = get_palette_for_types(pokemon_types)
    return {
        "skyStops": ("#060314", tp["fg"], tp["fgSecondary"]),
        "sunStops": ("#fef9c3", tp["badgeBg"], tp["accent"]),
        "floorStops": (tp["fg"], "#05020e"),
        "gridColor": tp["accent"],
        "mountainColor": "#070414",
        "tileColor": tp["badgeBg"],
        "tileGlow": tp["accent"],
        "eyeBright": tp["badgeBg"],
        "eyeDark": "#070414",
    }


def build_qr_matrix(payload: str, ec_level: str = "H", mask: int | None = None) -> list[list[int]]:
    ec = ec_level.lower() if ec_level.upper() in ("L", "M", "Q", "H") else "h"
    qr = segno.make(payload or "https://pokeapi.co", error=ec, mask=mask)
    return [[int(cell) for cell in row] for row in qr.matrix]


def estimate_inline_byte_capacity(ec_level: str) -> int:
    return {"L": 2953, "M": 2331, "Q": 1663, "H": 1273}.get(ec_level.upper(), 1273)


def _is_finder_module(r: int, c: int, size: int) -> bool:
    return (r < 8 and c < 8) or (r < 8 and c >= size - 8) or (r >= size - 8 and c < 8)


def _is_timing_module(r: int, c: int, size: int) -> bool:
    return (r == 6 and 8 <= c < size - 8) or (c == 6 and 8 <= r < size - 8)


def _get_alignment_centers(size: int) -> list[tuple[int, int]]:
    version = round((size - 17) / 4)
    coords = ALIGNMENT_COORDS.get(version)
    if not coords:
        return []
    centers: list[tuple[int, int]] = []
    for r in coords:
        for c in coords:
            if (r < 9 and c < 9) or (r < 9 and c >= size - 9) or (r >= size - 9 and c < 9):
                continue
            centers.append((r, c))
    return centers


def _is_alignment_module(r: int, c: int, centers: list[tuple[int, int]]) -> bool:
    return any(abs(r - cr) <= 2 and abs(c - cc) <= 2 for cr, cc in centers)


def _load_font(size: int, bold: bool = False) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    candidates = (
        ["C:/Windows/Fonts/segoeuib.ttf", "C:/Windows/Fonts/arialbd.ttf", "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"]
        if bold
        else ["C:/Windows/Fonts/segoeui.ttf", "C:/Windows/Fonts/arial.ttf", "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"]
    )
    for path in candidates:
        try:
            return ImageFont.truetype(path, size=size)
        except OSError:
            continue
    return ImageFont.load_default()


def _make_linear_gradient(width: int, height: int, c1: tuple[int, int, int], c2: tuple[int, int, int], vertical: bool = False) -> Image.Image:
    if vertical:
        t = np.linspace(0.0, 1.0, height, dtype=np.float32)[:, None, None]
        arr = (1.0 - t) * np.array(c1, dtype=np.float32) + t * np.array(c2, dtype=np.float32)
        arr = np.repeat(arr, width, axis=1)
    else:
        gx = np.linspace(0.0, 1.0, width, dtype=np.float32)[None, :]
        gy = np.linspace(0.0, 1.0, height, dtype=np.float32)[:, None]
        t = ((gx + gy) * 0.5)[..., None]
        arr = (1.0 - t) * np.array(c1, dtype=np.float32) + t * np.array(c2, dtype=np.float32)
    return Image.fromarray(np.clip(arr, 0, 255).astype(np.uint8), mode="RGB").convert("RGBA")


def _extract_tight_pixel_grid(sprite_img: Image.Image, target_w: int, target_h: int) -> np.ndarray:
    rgba = sprite_img.convert("RGBA")
    arr = np.array(rgba)
    alpha = arr[:, :, 3]
    ys, xs = np.where(alpha > 40)
    if len(xs) > 0 and len(ys) > 0:
        rgba = rgba.crop((int(xs.min()), int(ys.min()), int(xs.max()) + 1, int(ys.max()) + 1))

    cw, ch = rgba.size
    scale = min(target_w / max(1, cw), target_h / max(1, ch))
    dw = max(1, round(cw * scale))
    dh = max(1, round(ch * scale))
    resized = rgba.resize((dw, dh), resample=Image.Resampling.NEAREST)

    canvas = Image.new("RGBA", (target_w, target_h), (0, 0, 0, 0))
    canvas.paste(resized, ((target_w - dw) // 2, (target_h - dh) // 2), resized)
    return np.array(canvas)


def _select_best_mask_for_sprite(
    payload: str,
    sprite_grid: np.ndarray | None,
    box_size: int,
    start_row: int,
    start_col: int,
) -> list[list[int]]:
    if sprite_grid is None:
        return build_qr_matrix(payload, "H")

    best_matrix = build_qr_matrix(payload, "H")
    best_score = -1

    for m in range(8):
        try:
            cand = build_qr_matrix(payload, "H", mask=m)
            n = len(cand)
            score = 0
            for sr in range(box_size):
                mr = start_row + sr
                if not (0 <= mr < n):
                    continue
                for sc in range(box_size):
                    mc = start_col + sc
                    if not (0 <= mc < n) or _is_finder_module(mr, mc, n):
                        continue
                    r, g, b, a = sprite_grid[sr, sc]
                    if a <= 64:
                        continue
                    luma = 0.299 * r + 0.587 * g + 0.114 * b
                    bit = cand[mr][mc]
                    if (bit == 1 and luma < 120) or (bit == 0 and luma >= 120):
                        score += 1
            if score > best_score:
                best_score = score
                best_matrix = cand
        except Exception:
            continue

    return best_matrix


def _draw_finder_eye(
    img: Image.Image,
    x: float,
    y: float,
    mod: float,
    eye_shape: str,
    eye_color: str,
    bg_color: str,
) -> None:
    draw = ImageDraw.Draw(img)
    eye_px = mod * 7.0
    bg_rgba = hex_to_rgba(bg_color)
    eye_rgba = hex_to_rgba(eye_color)
    draw.rectangle([x, y, x + eye_px, y + eye_px], fill=bg_rgba)

    if eye_shape == "square":
        draw.rectangle([x, y, x + eye_px, y + eye_px], fill=eye_rgba)
        draw.rectangle([x + mod, y + mod, x + mod * 6, y + mod * 6], fill=bg_rgba)
        draw.rectangle([x + mod * 2, y + mod * 2, x + mod * 5, y + mod * 5], fill=eye_rgba)
        return

    if eye_shape == "rounded":
        draw.rounded_rectangle([x, y, x + eye_px, y + eye_px], radius=mod * 1.0, fill=eye_rgba)
        draw.rounded_rectangle([x + mod, y + mod, x + mod * 6, y + mod * 6], radius=mod * 0.7, fill=bg_rgba)
        draw.rounded_rectangle([x + mod * 2, y + mod * 2, x + mod * 5, y + mod * 5], radius=mod * 0.45, fill=eye_rgba)
        return

    ball_colors = {
        "pokeball": (hex_to_rgba("#dc2626"), None),
        "greatball": (hex_to_rgba("#2563eb"), hex_to_rgba("#ef4444")),
        "ultraball": (hex_to_rgba("#18181b"), hex_to_rgba("#eab308")),
        "masterball": (hex_to_rgba("#7e22ce"), hex_to_rgba("#ec4899")),
    }
    top_col, accent_col = ball_colors.get(eye_shape, (eye_rgba, None))
    dark_shell = eye_rgba if _relative_luminance(hex_to_rgb(eye_color)) < 0.14 else (15, 23, 42, 255)

    eye_w = max(14, round(eye_px))
    patch = Image.new("RGBA", (eye_w, eye_w), (0, 0, 0, 0))
    pdraw = ImageDraw.Draw(patch)
    mask = Image.new("L", (eye_w, eye_w), 0)
    mdraw = ImageDraw.Draw(mask)
    mdraw.rounded_rectangle([0, 0, eye_w - 1, eye_w - 1], radius=mod * 1.05, fill=255)

    pdraw.rectangle([0, 0, eye_w, eye_w], fill=dark_shell)
    pdraw.rectangle([0, 0, eye_w, eye_w // 2], fill=top_col)
    if accent_col:
        pdraw.rectangle([mod * 1.4, 0, mod * 2.5, mod * 1.3], fill=accent_col)
        pdraw.rectangle([eye_w - mod * 2.5, 0, eye_w - mod * 1.4, mod * 1.3], fill=accent_col)
    band_h = max(2, round(mod * 0.72))
    pdraw.rectangle([0, eye_w // 2 - band_h // 2, eye_w, eye_w // 2 + band_h // 2], fill=(15, 23, 42, 255))

    patch.putalpha(mask)
    img.alpha_composite(patch, (round(x), round(y)))

    draw.rounded_rectangle([x + mod, y + mod, x + mod * 6, y + mod * 6], radius=mod * 0.72, fill=bg_rgba)
    cx, cy = x + eye_px / 2.0, y + eye_px / 2.0
    r_outer = mod * 1.5
    r_inner = mod * 0.82
    draw.ellipse([cx - r_outer, cy - r_outer, cx + r_outer, cy + r_outer], fill=(15, 23, 42, 255))
    draw.ellipse([cx - r_inner, cy - r_inner, cx + r_inner, cy + r_inner], fill=eye_rgba)


def _decode_qr_opencv(pil_qr_box: Image.Image, allow_inverted: bool = True) -> tuple[str | None, bool]:
    rgb = np.array(pil_qr_box.convert("RGB"))
    gray = cv2.cvtColor(rgb, cv2.COLOR_RGB2GRAY)
    detectors = [cv2.QRCodeDetector()]
    if hasattr(cv2, "QRCodeDetectorAruco"):
        detectors.append(cv2.QRCodeDetectorAruco())

    for det in detectors:
        data, _, _ = det.detectAndDecode(gray)
        if data:
            return data, False

    if allow_inverted:
        inv_gray = 255 - gray
        for det in detectors:
            data_inv, _, _ = det.detectAndDecode(inv_gray)
            if data_inv:
                return data_inv, True

    return None, False


def _render_pixel_art_qr(
    payload: str,
    style: QrStyleOptions,
    sprite_img: Image.Image | None,
    box_size: int,
) -> tuple[Image.Image, int]:
    base_matrix = build_qr_matrix(payload, "H")
    n = len(base_matrix)
    sprite_mods = max(7, min(n - 12, round(n * style.pixel_sprite_scale)))
    start_r = (n - sprite_mods) // 2
    start_c = (n - sprite_mods) // 2

    sprite_grid = _extract_tight_pixel_grid(sprite_img, sprite_mods, sprite_mods) if sprite_img else None
    matrix = _select_best_mask_for_sprite(payload, sprite_grid, sprite_mods, start_r, start_c)

    quiet = style.quiet_zone_modules
    total_mods = n + quiet * 2
    mod = box_size / total_mods
    origin = quiet * mod

    bg_rgba = hex_to_rgba(style.bg_color)
    fg_rgba = hex_to_rgba(style.fg_color)

    def paint(with_safe_dots: bool) -> Image.Image:
        canvas = Image.new("RGBA", (box_size, box_size), bg_rgba)
        draw = ImageDraw.Draw(canvas)

        for r in range(n):
            for c in range(n):
                if _is_finder_module(r, c, n) or matrix[r][c] != 1:
                    continue
                x = origin + c * mod
                y = origin + r * mod
                draw.rectangle([x, y, math.ceil(x + mod), math.ceil(y + mod)], fill=fg_rgba)

        _draw_finder_eye(canvas, origin, origin, mod, "square", style.eye_color, style.bg_color)
        _draw_finder_eye(canvas, origin + (n - 7) * mod, origin, mod, "square", style.eye_color, style.bg_color)
        _draw_finder_eye(canvas, origin, origin + (n - 7) * mod, mod, "square", style.eye_color, style.bg_color)

        if sprite_grid is None:
            return canvas

        center = (n - 1) / 2.0
        core_safe = n * 0.19

        for sr in range(sprite_mods):
            mr = start_r + sr
            if not (0 <= mr < n):
                continue
            for sc in range(sprite_mods):
                mc = start_c + sc
                if not (0 <= mc < n) or _is_finder_module(mr, mc, n):
                    continue
                r_ch, g_ch, b_ch, a_ch = [int(v) for v in sprite_grid[sr, sc]]
                if a_ch <= 70:
                    continue
                x = origin + mc * mod
                y = origin + mr * mod
                draw.rectangle([x, y, math.ceil(x + mod), math.ceil(y + mod)], fill=(r_ch, g_ch, b_ch, 255))

                if with_safe_dots and max(abs(mr - center), abs(mc - center)) > core_safe:
                    bit = matrix[mr][mc]
                    luma = 0.299 * r_ch + 0.587 * g_ch + 0.114 * b_ch
                    agrees = (bit == 1 and luma < 115) or (bit == 0 and luma >= 135)
                    if not agrees:
                        dot = mod * 0.36
                        off = (mod - dot) / 2.0
                        draw.rectangle(
                            [x + off, y + off, x + off + dot, y + off + dot],
                            fill=fg_rgba if bit == 1 else bg_rgba,
                        )
        return canvas

    img = paint(False)
    if sprite_grid is not None and style.pixel_safe_dots:
        decoded, _ = _decode_qr_opencv(img, allow_inverted=False)
        if decoded != payload:
            img = paint(True)
    return img, n


def _draw_palm_silhouette(draw: ImageDraw.ImageDraw, base_x: float, base_y: float, height: float, lean: float, color: tuple[int, int, int, int]) -> None:
    top_x = base_x + lean * height * 0.28
    top_y = base_y - height
    steps = 12
    pts = []
    ctrl_x = base_x + lean * height * 0.08
    ctrl_y = base_y - height * 0.5
    for i in range(steps + 1):
        t = i / steps
        px = (1 - t) ** 2 * base_x + 2 * (1 - t) * t * ctrl_x + t**2 * top_x
        py = (1 - t) ** 2 * base_y + 2 * (1 - t) * t * ctrl_y + t**2 * top_y
        pts.append((px, py))
    draw.line(pts, fill=color, width=max(4, round(height * 0.055)))

    for ang in (-2.6, -2.0, -1.2, -0.4, 0.35, 1.0):
        length = height * 0.42
        ex = top_x + math.cos(ang) * length
        ey = top_y + math.sin(ang) * length * 0.72 + length * 0.2
        c1x = top_x + math.cos(ang) * length * 0.55
        c1y = top_y + math.sin(ang) * length * 0.25 - length * 0.08
        draw.polygon([(top_x, top_y), (c1x, c1y), (ex, ey)], fill=color)


def _render_neon_scene_qr(
    payload: str,
    style: QrStyleOptions,
    pokemon_types: list[str] | None,
    sprite_img: Image.Image | None,
    box_size: int,
) -> tuple[Image.Image, int]:
    matrix = build_qr_matrix(payload, "H")
    n = len(matrix)
    pal = get_neon_palette(style.neon_theme, pokemon_types)
    align_centers = _get_alignment_centers(n)

    quiet = style.quiet_zone_modules
    total_mods = n + quiet * 2
    mod = box_size / total_mods
    origin = quiet * mod

    cx = box_size / 2.0
    horizon_y = round(box_size * 0.58)
    sun_y = round(box_size * 0.44)
    sun_r = box_size * 0.205

    canvas = Image.new("RGBA", (box_size, box_size), hex_to_rgba(pal["eyeDark"]))

    # Sky gradient (top + mid + horizon)
    top_h = round(horizon_y * 0.62)
    sky_top = _make_linear_gradient(box_size, max(1, top_h), hex_to_rgb(pal["skyStops"][0]), hex_to_rgb(pal["skyStops"][1]), vertical=True)
    sky_bot = _make_linear_gradient(box_size, max(1, horizon_y - top_h), hex_to_rgb(pal["skyStops"][1]), hex_to_rgb(pal["skyStops"][2]), vertical=True)
    canvas.alpha_composite(sky_top, (0, 0))
    canvas.alpha_composite(sky_bot, (0, top_h))

    # Stars
    star_layer = Image.new("RGBA", (box_size, box_size), (0, 0, 0, 0))
    sdraw = ImageDraw.Draw(star_layer)
    tile_rgb = hex_to_rgb(pal["tileColor"])
    for i in range(65):
        sx = (((math.sin(i * 12.9898) * 43758.5453) % 1.0) + 1.0) % 1.0 * box_size
        sy = (((math.sin(i * 78.233) * 19341.123) % 1.0) + 1.0) % 1.0 * (horizon_y * 0.85)
        sr = (2.1 if i % 3 == 0 else 1.2) * (box_size / 1024.0)
        alpha = round((0.35 + (i % 5) * 0.12) * 255)
        col = (*tile_rgb, alpha) if i % 4 == 0 else (255, 255, 255, alpha)
        sdraw.ellipse([sx - sr, sy - sr, sx + sr, sy + sr], fill=col)
    canvas.alpha_composite(star_layer)

    # Sun halo bloom + sun disc with synthwave slices
    halo_layer = Image.new("RGBA", (box_size, box_size), (0, 0, 0, 0))
    hdraw = ImageDraw.Draw(halo_layer)
    glow_rgb = hex_to_rgb(pal["tileGlow"])
    hdraw.ellipse([cx - sun_r * 1.45, sun_y - sun_r * 1.45, cx + sun_r * 1.45, sun_y + sun_r * 1.45], fill=(*glow_rgb, 130))
    halo_layer = halo_layer.filter(ImageFilter.GaussianBlur(radius=max(6, sun_r * 0.35)))
    canvas.alpha_composite(halo_layer)

    sun_d = max(10, round(sun_r * 2))
    sun_grad = _make_linear_gradient(sun_d, sun_d, hex_to_rgb(pal["sunStops"][0]), hex_to_rgb(pal["sunStops"][2]), vertical=True)
    sun_mask = Image.new("L", (sun_d, sun_d), 0)
    ImageDraw.Draw(sun_mask).ellipse([0, 0, sun_d - 1, sun_d - 1], fill=255)
    sun_draw = ImageDraw.Draw(sun_grad)
    stripe_col = hex_to_rgba(pal["skyStops"][1])
    for band in range(6):
        by = sun_d * (0.54 + band * 0.075)
        bh = sun_d * (0.01 + band * 0.006)
        sun_draw.rectangle([0, by, sun_d, by + bh], fill=stripe_col)
    sun_grad.putalpha(sun_mask)
    canvas.alpha_composite(sun_grad, (round(cx - sun_r), round(sun_y - sun_r)))

    # Mountains
    mdraw = ImageDraw.Draw(canvas)
    mountain_pts = [
        (0.0, 0.0), (0.09, -0.055), (0.18, -0.025), (0.29, -0.07),
        (0.41, -0.015), (0.50, -0.032), (0.62, -0.015), (0.73, -0.068),
        (0.84, -0.024), (0.93, -0.052), (1.0, 0.0),
    ]
    poly = [(0, horizon_y)] + [(px * box_size, horizon_y + py * box_size) for px, py in mountain_pts] + [(box_size, horizon_y)]
    mdraw.polygon(poly, fill=hex_to_rgba(pal["mountainColor"]))

    # Floor gradient + perspective grid
    floor_h = max(1, box_size - horizon_y)
    floor = _make_linear_gradient(box_size, floor_h, hex_to_rgb(pal["floorStops"][0]), hex_to_rgb(pal["floorStops"][1]), vertical=True)
    canvas.alpha_composite(floor, (0, horizon_y))

    grid_layer = Image.new("RGBA", (box_size, box_size), (0, 0, 0, 0))
    gdraw = ImageDraw.Draw(grid_layer)
    grid_rgb = hex_to_rgb(pal["gridColor"])
    lw = max(1, round(box_size * 0.0022))
    gdraw.line([(0, horizon_y + 1), (box_size, horizon_y + 1)], fill=(*grid_rgb, 230), width=lw + 1)
    for i in range(1, 11):
        t = (i / 10.0) ** 1.85
        ly = horizon_y + t * floor_h
        gdraw.line([(0, ly), (box_size, ly)], fill=(*grid_rgb, round((0.28 + 0.52 * t) * 255)), width=lw)
    for i in range(-10, 11):
        bx = cx + i * (box_size * 0.14)
        gdraw.line([(cx + i * (box_size * 0.015), horizon_y), (bx, box_size)], fill=(*grid_rgb, 145), width=lw)
    canvas.alpha_composite(grid_layer)

    # Palm silhouettes
    palm_col = hex_to_rgba(pal["mountainColor"])
    _draw_palm_silhouette(mdraw, box_size * 0.055, horizon_y + box_size * 0.02, box_size * 0.24, 0.55, palm_col)
    _draw_palm_silhouette(mdraw, box_size * 0.945, horizon_y + box_size * 0.02, box_size * 0.24, -0.55, palm_col)

    # Centered Pokémon artwork inside sun orb
    if sprite_img is not None:
        poke_box = round(sun_r * 1.62)
        rgba_poke = sprite_img.convert("RGBA")
        iw, ih = rgba_poke.size
        scale = min(poke_box / max(1, iw), poke_box / max(1, ih))
        dw, dh = max(1, round(iw * scale)), max(1, round(ih * scale))
        resized = rgba_poke.resize((dw, dh), resample=Image.Resampling.LANCZOS)
        canvas.alpha_composite(resized, (round(cx - dw / 2), round(sun_y - dh / 2)))

    # Glow + Crisp QR Layer
    glow_layer = Image.new("RGBA", (box_size, box_size), (0, 0, 0, 0))
    glow_draw = ImageDraw.Draw(glow_layer)
    tile_layer = Image.new("RGBA", (box_size, box_size), (0, 0, 0, 0))
    tile_draw = ImageDraw.Draw(tile_layer)

    eye_bright = hex_to_rgba(pal["eyeBright"])
    eye_dark = hex_to_rgba(pal["eyeDark"])
    tile_rgba = (*hex_to_rgb(pal["tileColor"]), 238)
    glow_rgba = (*hex_to_rgb(pal["tileGlow"]), round(180 * style.neon_glow_strength))

    center_idx = (n - 1) / 2.0
    sun_center_row = (sun_y - origin) / mod - 0.5
    sun_safe_mods = min(n * 0.165, (sun_r * 0.74) / mod)

    for r in range(n):
        for c in range(n):
            if _is_finder_module(r, c, n) or _is_alignment_module(r, c, align_centers):
                continue
            dr = r - sun_center_row
            dc = c - center_idx
            if math.hypot(dr, dc) <= sun_safe_mods:
                continue

            x = origin + c * mod
            y = origin + r * mod
            bit = matrix[r][c] == 1

            if style.neon_inverted:
                if bit:
                    pad = mod * 0.08
                    rect = [x + pad, y + pad, x + mod - pad, y + mod - pad]
                    glow_draw.rectangle(rect, fill=glow_rgba)
                    tile_draw.rectangle(rect, fill=tile_rgba)
                else:
                    near_sun = math.hypot(dr, dc) <= sun_safe_mods + 3.2
                    near_horizon = abs((y + mod / 2.0) - horizon_y) < mod * 2.2
                    if near_sun or near_horizon:
                        p = mod * 0.08
                        tile_draw.rectangle([x + p, y + p, x + mod - p, y + mod - p], fill=(*hex_to_rgb(pal["eyeDark"]), 185))
            else:
                if bit:
                    pad = mod * 0.08
                    tile_draw.rectangle([x + pad, y + pad, x + mod - pad, y + mod - pad], fill=(*hex_to_rgb(pal["eyeDark"]), 235))
                else:
                    p = mod * 0.14
                    tile_draw.rectangle([x + p, y + p, x + mod - p, y + mod - p], fill=(*hex_to_rgb(pal["tileColor"]), 200))

    def draw_neon_eye(ex: float, ey: float, mods: int) -> None:
        s = mod * mods
        dm = mod * 0.55
        tile_draw.rectangle([ex - dm, ey - dm, ex + s + dm, ey + s + dm], fill=(*hex_to_rgb(pal["eyeDark"]), 200))
        if style.neon_inverted:
            glow_draw.rectangle([ex, ey, ex + s, ey + s], fill=glow_rgba)
            tile_draw.rectangle([ex, ey, ex + s, ey + s], fill=eye_bright)
            tile_draw.rectangle([ex + mod, ey + mod, ex + mod * (mods - 1), ey + mod * (mods - 1)], fill=eye_dark)
            glow_draw.rectangle([ex + mod * 2, ey + mod * 2, ex + mod * (mods - 2), ey + mod * (mods - 2)], fill=glow_rgba)
            tile_draw.rectangle([ex + mod * 2, ey + mod * 2, ex + mod * (mods - 2), ey + mod * (mods - 2)], fill=eye_bright)
        else:
            tile_draw.rectangle([ex, ey, ex + s, ey + s], fill=eye_dark)
            tile_draw.rectangle([ex + mod, ey + mod, ex + mod * (mods - 1), ey + mod * (mods - 1)], fill=eye_bright)
            tile_draw.rectangle([ex + mod * 2, ey + mod * 2, ex + mod * (mods - 2), ey + mod * (mods - 2)], fill=eye_dark)

    draw_neon_eye(origin, origin, 7)
    draw_neon_eye(origin + (n - 7) * mod, origin, 7)
    draw_neon_eye(origin, origin + (n - 7) * mod, 7)
    for ar, ac in align_centers:
        draw_neon_eye(origin + (ac - 2) * mod, origin + (ar - 2) * mod, 5)

    glow_blur = glow_layer.filter(ImageFilter.GaussianBlur(radius=max(2.0, mod * 0.45 * style.neon_glow_strength)))
    canvas.alpha_composite(glow_blur)
    canvas.alpha_composite(tile_layer)
    return canvas, n


def _draw_standard_qr(
    payload: str,
    style: QrStyleOptions,
    pokemon_types: list[str] | None,
    sprite_img: Image.Image | None,
    box_size: int,
) -> tuple[Image.Image, int]:
    ec = style.ec_level if style.mode == "classic" else "H"
    matrix = build_qr_matrix(payload, ec)
    n = len(matrix)
    palette = get_palette_for_types(pokemon_types)

    quiet = style.quiet_zone_modules
    total_mods = n + quiet * 2
    mod = box_size / total_mods
    origin = quiet * mod
    matrix_px = n * mod

    canvas = Image.new("RGBA", (box_size, box_size), hex_to_rgba(style.bg_color))

    if style.mode == "backdrop" and sprite_img is not None:
        rgba = sprite_img.convert("RGBA")
        iw, ih = rgba.size
        scale = min((matrix_px * 0.9) / max(1, iw), (matrix_px * 0.9) / max(1, ih))
        dw, dh = max(1, round(iw * scale)), max(1, round(ih * scale))
        resized = rgba.resize((dw, dh), resample=Image.Resampling.LANCZOS)
        r_ch, g_ch, b_ch, a_ch = resized.split()
        a_ch = a_ch.point(lambda v: round(v * style.backdrop_opacity))
        resized.putalpha(a_ch)
        canvas.alpha_composite(resized, (round(origin + (matrix_px - dw) / 2), round(origin + (matrix_px - dh) / 2)))

    sampled_grid: np.ndarray | None = None
    if style.mode == "halftone" and sprite_img is not None:
        rgba = sprite_img.convert("RGBA")
        iw, ih = rgba.size
        scale = min(n / max(1, iw), n / max(1, ih))
        dw, dh = max(1, round(iw * scale)), max(1, round(ih * scale))
        resized = rgba.resize((dw, dh), resample=Image.Resampling.LANCZOS)
        grid_img = Image.new("RGBA", (n, n), (0, 0, 0, 0))
        grid_img.paste(resized, ((n - dw) // 2, (n - dh) // 2), resized)
        sampled_grid = np.array(grid_img)

    badge_px = box_size * style.badge_size_ratio
    badge_radius_mods = (badge_px / mod) * 0.52 if style.mode == "badge" else -1.0
    center = (n - 1) / 2.0

    # Prepare gradient or solid foreground layer for modules
    if style.use_gradient:
        fg_layer = _make_linear_gradient(box_size, box_size, hex_to_rgb(style.fg_color), hex_to_rgb(style.fg_secondary_color))
    else:
        fg_layer = Image.new("RGBA", (box_size, box_size), hex_to_rgba(style.fg_color))

    fg_mask = Image.new("L", (box_size, box_size), 0)
    mdraw = ImageDraw.Draw(fg_mask)
    overlay = Image.new("RGBA", (box_size, box_size), (0, 0, 0, 0))
    odraw = ImageDraw.Draw(overlay)
    bg_rgba = hex_to_rgba(style.bg_color)

    for r in range(n):
        for c in range(n):
            if _is_finder_module(r, c, n):
                continue
            if badge_radius_mods > 0 and max(abs(c - center), abs(r - center)) <= badge_radius_mods:
                continue

            x = origin + c * mod
            y = origin + r * mod
            bit = matrix[r][c] == 1

            if style.mode == "halftone" and sampled_grid is not None and not _is_timing_module(r, c, n):
                sr, sg, sb, sa = [int(v) for v in sampled_grid[r, c]]
                if sa > 36:
                    blend_a = round(style.halftone_intensity * sa)
                    odraw.rectangle([x, y, math.ceil(x + mod), math.ceil(y + mod)], fill=(sr, sg, sb, blend_a))
                    core = mod * 0.5
                    off = (mod - core) / 2.0
                    if bit:
                        if style.module_shape == "dots":
                            mdraw.ellipse([x + mod / 2 - core * 0.56, y + mod / 2 - core * 0.56, x + mod / 2 + core * 0.56, y + mod / 2 + core * 0.56], fill=255)
                        else:
                            mdraw.rectangle([x + off, y + off, x + off + core, y + off + core], fill=255)
                    else:
                        if style.module_shape == "dots":
                            odraw.ellipse([x + mod / 2 - core * 0.56, y + mod / 2 - core * 0.56, x + mod / 2 + core * 0.56, y + mod / 2 + core * 0.56], fill=bg_rgba)
                        else:
                            odraw.rectangle([x + off, y + off, x + off + core, y + off + core], fill=bg_rgba)
                    continue

            if style.mode == "backdrop" and sprite_img is not None and not bit:
                odraw.rectangle([x + mod * 0.18, y + mod * 0.18, x + mod * 0.82, y + mod * 0.82], fill=(*hex_to_rgb(style.bg_color), 140))
                continue

            if not bit:
                continue

            if style.module_shape == "square":
                mdraw.rectangle([x, y, math.ceil(x + mod), math.ceil(y + mod)], fill=255)
            elif style.module_shape == "pixel":
                p = mod * 0.06
                mdraw.rectangle([x + p, y + p, x + mod - p, y + mod - p], fill=255)
            elif style.module_shape == "dots":
                rad = mod * 0.43
                mx, my = x + mod / 2.0, y + mod / 2.0
                mdraw.ellipse([mx - rad, my - rad, mx + rad, my + rad], fill=255)
            elif style.module_shape == "liquid":
                p = mod * 0.02
                mdraw.rounded_rectangle([x - p, y - p, x + mod + p, y + mod + p], radius=mod * 0.34, fill=255)
            else:  # rounded
                p = mod * 0.07
                mdraw.rounded_rectangle([x + p, y + p, x + mod - p, y + mod - p], radius=mod * 0.3, fill=255)

    canvas.alpha_composite(overlay)
    fg_layer.putalpha(fg_mask)
    canvas.alpha_composite(fg_layer)

    _draw_finder_eye(canvas, origin, origin, mod, style.eye_shape, style.eye_color, style.bg_color)
    _draw_finder_eye(canvas, origin + (n - 7) * mod, origin, mod, style.eye_shape, style.eye_color, style.bg_color)
    _draw_finder_eye(canvas, origin, origin + (n - 7) * mod, mod, style.eye_shape, style.eye_color, style.bg_color)

    if style.mode == "badge":
        cx = cy = box_size / 2.0
        half = badge_px / 2.0
        bdraw = ImageDraw.Draw(canvas)
        if style.badge_shape == "squircle":
            bdraw.rounded_rectangle([cx - half, cy - half, cx + half, cy + half], radius=badge_px * 0.24, fill=bg_rgba)
        else:
            bdraw.ellipse([cx - half, cy - half, cx + half, cy + half], fill=bg_rgba)

        inner_pad = badge_px * 0.08
        inner_size = badge_px - inner_pad * 2
        inner_half = inner_size / 2.0
        badge_tint = hex_to_rgba(palette["badgeBg"])
        eye_rgba = hex_to_rgba(style.eye_color)
        stroke_w = max(2, round(badge_px * 0.03))

        if style.badge_shape == "pokeball":
            bdraw.pieslice([cx - inner_half, cy - inner_half, cx + inner_half, cy + inner_half], 180, 360, fill=badge_tint)
            bdraw.pieslice([cx - inner_half, cy - inner_half, cx + inner_half, cy + inner_half], 0, 180, fill=(255, 255, 255, 255))
            band_h = max(3, round(inner_size * 0.08))
            bdraw.rectangle([cx - inner_half, cy - band_h / 2, cx + inner_half, cy + band_h / 2], fill=(30, 41, 59, 255))
            bdraw.ellipse([cx - inner_half, cy - inner_half, cx + inner_half, cy + inner_half], outline=(30, 41, 59, 255), width=stroke_w)
        elif style.badge_shape == "squircle":
            bdraw.rounded_rectangle([cx - inner_half, cy - inner_half, cx + inner_half, cy + inner_half], radius=inner_size * 0.22, fill=badge_tint, outline=eye_rgba, width=stroke_w)
        else:
            bdraw.ellipse([cx - inner_half, cy - inner_half, cx + inner_half, cy + inner_half], fill=badge_tint, outline=eye_rgba, width=stroke_w)

        if sprite_img is not None:
            img_box = round(inner_size * 0.88)
            rgba = sprite_img.convert("RGBA")
            iw, ih = rgba.size
            scale = min(img_box / max(1, iw), img_box / max(1, ih))
            dw, dh = max(1, round(iw * scale)), max(1, round(ih * scale))
            resized = rgba.resize((dw, dh), resample=Image.Resampling.LANCZOS)
            canvas.alpha_composite(resized, (round(cx - dw / 2), round(cy - dh / 2)))

    return canvas, n


def render_pokemon_qr(
    payload: str,
    style: QrStyleOptions,
    pokemon: dict[str, Any] | None = None,
    sprite_bytes: bytes | None = None,
    output_size: int = 1024,
) -> tuple[Image.Image, dict[str, Any]]:
    sprite_img: Image.Image | None = None
    if sprite_bytes:
        try:
            sprite_img = Image.open(io.BytesIO(sprite_bytes)).convert("RGBA")
        except Exception:
            sprite_img = None

    pokemon_types = pokemon.get("types", []) if pokemon else []
    palette = get_palette_for_types(pokemon_types)

    qr_box_size = round(output_size * 0.82) if style.include_card_frame else output_size

    if style.mode == "pixelart":
        qr_img, module_count = _render_pixel_art_qr(payload, style, sprite_img, qr_box_size)
    elif style.mode == "neonscene":
        qr_img, module_count = _render_neon_scene_qr(payload, style, pokemon_types, sprite_img, qr_box_size)
    else:
        qr_img, module_count = _draw_standard_qr(payload, style, pokemon_types, sprite_img, qr_box_size)

    # Verify scannability on the QR region with OpenCV
    if style.mode == "neonscene":
        neon_pal = get_neon_palette(style.neon_theme, pokemon_types)
        contrast = compute_contrast_ratio(neon_pal["tileColor"], neon_pal["eyeDark"])
    else:
        contrast = compute_contrast_ratio(style.fg_color, style.bg_color)

    decoded_text, used_inverted = _decode_qr_opencv(qr_img, allow_inverted=(style.mode == "neonscene"))
    matches_target = decoded_text == payload
    warning = None
    if contrast < 3.0:
        warning = f"Low contrast ({contrast}:1). Increase dark/light separation for reliable scanning."
    elif decoded_text is None:
        warning = "OpenCV check could not decode this exact frame yet — try slightly smaller center art or classic contrast."
    elif not matches_target:
        warning = "Decoded payload differs from target URL."

    verification = {
        "verified": bool(matches_target and contrast >= 2.5),
        "decodedText": decoded_text,
        "matchesTarget": matches_target,
        "contrastRatio": contrast,
        "moduleCount": module_count,
        "inverted": used_inverted,
        "warning": warning,
    }

    if not style.include_card_frame:
        return qr_img, verification

    card_w = output_size
    card_h = round(output_size * 1.24)
    card = _make_linear_gradient(card_w, card_h, hex_to_rgb(palette["accent"]), hex_to_rgb(palette["fgSecondary"]))
    card_mask = Image.new("L", (card_w, card_h), 0)
    ImageDraw.Draw(card_mask).rounded_rectangle([0, 0, card_w - 1, card_h - 1], radius=round(card_w * 0.045), fill=255)
    card.putalpha(card_mask)

    draw = ImageDraw.Draw(card)
    margin = round(card_w * 0.032)
    draw.rounded_rectangle([margin, margin, card_w - margin, card_h - margin], radius=round(card_w * 0.03), fill=(255, 255, 255, 255))

    header_h = round(card_w * 0.13)
    draw.rounded_rectangle([margin, margin, card_w - margin, margin + header_h], radius=round(card_w * 0.03), fill=hex_to_rgba(palette["badgeBg"]))
    draw.rectangle([margin, margin + header_h // 2, card_w - margin, margin + header_h], fill=hex_to_rgba(palette["badgeBg"]))

    dex_label = f"#{int(pokemon['id']):03d}" if pokemon and pokemon.get("id") else "POKÉQR2"
    poke_name = pokemon.get("displayName", "Custom QR") if pokemon else "Custom QR"
    text_left = margin + round(card_w * 0.04)
    title_font = _load_font(round(card_w * 0.044), bold=True)
    meta_font = _load_font(round(card_w * 0.028), bold=True)

    draw.text((text_left, margin + header_h * 0.5), poke_name, fill=hex_to_rgba(palette["fg"]), font=title_font, anchor="lm")
    type_text = f"{dex_label} · {' / '.join(t.upper() for t in pokemon_types)}" if pokemon_types else dex_label
    draw.text((card_w - margin - round(card_w * 0.04), margin + header_h * 0.5), type_text, fill=hex_to_rgba(palette["eye"]), font=meta_font, anchor="rm")

    qr_x = (card_w - qr_box_size) // 2
    qr_y = margin + header_h + round(card_w * 0.035)
    qr_mask = Image.new("L", (qr_box_size, qr_box_size), 0)
    ImageDraw.Draw(qr_mask).rounded_rectangle([0, 0, qr_box_size - 1, qr_box_size - 1], radius=round(qr_box_size * 0.03), fill=255)
    qr_rounded = qr_img.copy()
    qr_rounded.putalpha(qr_mask)
    card.alpha_composite(qr_rounded, (qr_x, qr_y))

    footer_top = qr_y + qr_box_size + round(card_w * 0.028)
    head_font = _load_font(round(card_w * 0.036), bold=True)
    sub_font = _load_font(round(card_w * 0.024), bold=False)
    headline = (style.card_headline.strip() or "Scan to Open PokéDrop")[:42]
    subtitle = (style.card_subtitle.strip() or "Shared via PokéQR2 (Python)")[:62]
    draw.text((card_w // 2, footer_top), headline, fill=(15, 23, 42, 255), font=head_font, anchor="ma")
    draw.text((card_w // 2, footer_top + round(card_w * 0.048)), subtitle, fill=(71, 85, 105, 255), font=sub_font, anchor="ma")
    draw.rounded_rectangle([qr_x, qr_y, qr_x + qr_box_size, qr_y + qr_box_size], radius=round(qr_box_size * 0.03), outline=hex_to_rgba(palette["badgeBg"]), width=max(2, round(card_w * 0.004)))

    return card, verification


def image_to_png_bytes(img: Image.Image) -> bytes:
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


def render_qr_svg(
    payload: str,
    style: QrStyleOptions,
    pokemon: dict[str, Any] | None = None,
    sprite_bytes: bytes | None = None,
    raster_fallback_img: Image.Image | None = None,
    size: int = 900,
) -> str:
    if style.include_card_frame or style.mode not in ("classic", "badge"):
        if raster_fallback_img is None:
            raster_fallback_img, _ = render_pokemon_qr(payload, style, pokemon, sprite_bytes, output_size=size)
        b64 = base64.b64encode(image_to_png_bytes(raster_fallback_img)).decode("ascii")
        w, h = raster_fallback_img.size
        label = xml_escape.escape(f"{pokemon.get('displayName', 'Pokémon') if pokemon else 'Pokémon'} QR")
        return (
            f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {w} {h}" width="{w}" height="{h}" role="img" aria-label="{label}">'
            f'<title>{label}</title><image href="data:image/png;base64,{b64}" width="{w}" height="{h}"/></svg>'
        )

    ec = style.ec_level if style.mode == "classic" else "H"
    matrix = build_qr_matrix(payload, ec)
    n = len(matrix)
    quiet = style.quiet_zone_modules
    mod = size / (n + quiet * 2)
    origin = quiet * mod
    badge_px = size * style.badge_size_ratio
    badge_rad = (badge_px / mod) * 0.52 if style.mode == "badge" else -1.0
    center = (n - 1) / 2.0
    palette = get_palette_for_types(pokemon.get("types", []) if pokemon else [])

    shapes: list[str] = []
    for r in range(n):
        for c in range(n):
            if _is_finder_module(r, c, n):
                continue
            if badge_rad > 0 and max(abs(c - center), abs(r - center)) <= badge_rad:
                continue
            if matrix[r][c] != 1:
                continue
            x = origin + c * mod
            y = origin + r * mod
            if style.module_shape == "dots":
                shapes.append(f'<circle cx="{x + mod / 2:.2f}" cy="{y + mod / 2:.2f}" r="{mod * 0.43:.2f}"/>')
            elif style.module_shape in ("rounded", "liquid"):
                p = mod * 0.06
                shapes.append(f'<rect x="{x + p:.2f}" y="{y + p:.2f}" width="{mod - p * 2:.2f}" height="{mod - p * 2:.2f}" rx="{mod * 0.28:.2f}"/>')
            else:
                shapes.append(f'<rect x="{x:.2f}" y="{y:.2f}" width="{mod + 0.15:.2f}" height="{mod + 0.15:.2f}"/>')

    def eye_svg(ex: float, ey: float) -> str:
        s = mod * 7
        rxo = 0 if style.eye_shape == "square" else mod * 1.8
        rxi = 0 if style.eye_shape == "square" else mod * 1.2
        rxc = 0 if style.eye_shape == "square" else mod * 0.8
        ec_esc = xml_escape.escape(style.eye_color)
        bg_esc = xml_escape.escape(style.bg_color)
        return (
            f'<rect x="{ex:.2f}" y="{ey:.2f}" width="{s:.2f}" height="{s:.2f}" rx="{rxo:.2f}" fill="{ec_esc}"/>'
            f'<rect x="{ex + mod:.2f}" y="{ey + mod:.2f}" width="{mod * 5:.2f}" height="{mod * 5:.2f}" rx="{rxi:.2f}" fill="{bg_esc}"/>'
            f'<rect x="{ex + mod * 2:.2f}" y="{ey + mod * 2:.2f}" width="{mod * 3:.2f}" height="{mod * 3:.2f}" rx="{rxc:.2f}" fill="{ec_esc}"/>'
        )

    center_svg = ""
    if style.mode == "badge":
        half = badge_px / 2.0
        inner_r = half * 0.84
        cx = cy = size / 2.0
        img_tag = ""
        if sprite_bytes:
            mime = "image/svg+xml" if sprite_bytes.lstrip().startswith(b"<svg") else "image/png"
            b64 = base64.b64encode(sprite_bytes).decode("ascii")
            img_tag = f'<image href="data:{mime};base64,{b64}" x="{cx - inner_r * 0.88:.2f}" y="{cy - inner_r * 0.88:.2f}" width="{inner_r * 1.76:.2f}" height="{inner_r * 1.76:.2f}"/>'
        center_svg = (
            f'<circle cx="{cx}" cy="{cy}" r="{half:.2f}" fill="{xml_escape.escape(style.bg_color)}"/>'
            f'<circle cx="{cx}" cy="{cy}" r="{inner_r:.2f}" fill="{xml_escape.escape(palette["badgeBg"])}" stroke="{xml_escape.escape(style.eye_color)}" stroke-width="{max(2, badge_px * 0.025):.2f}"/>'
            f"{img_tag}"
        )

    fill_ref = "url(#pokeQrGrad)" if style.use_gradient else xml_escape.escape(style.fg_color)
    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {size} {size}" width="{size}" height="{size}">'
        f'<defs><linearGradient id="pokeQrGrad" x1="0" y1="0" x2="1" y2="1">'
        f'<stop offset="0%" stop-color="{xml_escape.escape(style.fg_color)}"/>'
        f'<stop offset="100%" stop-color="{xml_escape.escape(style.fg_secondary_color)}"/></linearGradient></defs>'
        f'<rect width="{size}" height="{size}" fill="{xml_escape.escape(style.bg_color)}"/>'
        f'<g fill="{fill_ref}">{"".join(shapes)}</g>'
        f"{eye_svg(origin, origin)}{eye_svg(origin + (n - 7) * mod, origin)}{eye_svg(origin, origin + (n - 7) * mod)}"
        f"{center_svg}</svg>"
    )
