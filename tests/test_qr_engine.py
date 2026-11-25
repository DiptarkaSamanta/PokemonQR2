from __future__ import annotations

import io
from PIL import Image, ImageDraw

from app.qr_engine import (
    QrStyleOptions,
    compute_contrast_ratio,
    render_pokemon_qr,
    render_qr_svg,
)


def _make_sample_sprite_bytes() -> bytes:
    img = Image.new("RGBA", (64, 64), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    # Yellow body with dark outline & eyes (mimicking a pixel sprite)
    draw.rectangle([10, 10, 54, 54], fill=(250, 204, 21, 255), outline=(15, 23, 42, 255), width=4)
    draw.rectangle([20, 22, 26, 28], fill=(15, 23, 42, 255))
    draw.rectangle([38, 22, 44, 28], fill=(15, 23, 42, 255))
    draw.rectangle([16, 36, 22, 42], fill=(239, 68, 68, 255))
    draw.rectangle([42, 36, 48, 42], fill=(239, 68, 68, 255))
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


def test_contrast_ratio():
    assert compute_contrast_ratio("#000000", "#ffffff") == 21.0
    assert compute_contrast_ratio("#ffffff", "#ffffff") == 1.0


def test_pixel_art_qr_renders_and_verifies_with_opencv():
    sprite = _make_sample_sprite_bytes()
    payload = "http://10.90.47.124:3001/s/pixel-pika"
    style = QrStyleOptions(
        mode="pixelart",
        fg_color="#0f172a",
        bg_color="#ffffff",
        eye_color="#0f172a",
        pixel_sprite_scale=0.38,
        pixel_safe_dots=True,
    )
    img, verification = render_pokemon_qr(
        payload,
        style,
        {"id": 25, "displayName": "Pikachu", "types": ["electric"]},
        sprite_bytes=sprite,
        output_size=640,
    )
    assert img.size == (640, 640)
    assert verification["verified"] is True
    assert verification["decodedText"] == payload


def test_neon_scene_qr_renders_and_verifies_inverted_with_opencv():
    sprite = _make_sample_sprite_bytes()
    payload = "http://10.90.47.124:3001/s/neon-mew"
    style = QrStyleOptions(
        mode="neonscene",
        neon_theme="synthwave",
        neon_inverted=True,
        neon_glow_strength=0.75,
    )
    img, verification = render_pokemon_qr(
        payload,
        style,
        {"id": 151, "displayName": "Mew", "types": ["psychic"]},
        sprite_bytes=sprite,
        output_size=720,
    )
    assert img.size == (720, 720)
    assert verification["verified"] is True
    assert verification["inverted"] is True
    assert verification["decodedText"] == payload


def test_badge_halftone_backdrop_and_card_frame():
    sprite = _make_sample_sprite_bytes()
    payload = "https://pokeapi.co/api/v2/pokemon/25"
    pokemon = {"id": 25, "displayName": "Pikachu", "types": ["electric"]}

    for mode in ("badge", "halftone", "backdrop", "classic"):
        style = QrStyleOptions(mode=mode, fg_color="#1e1b4b", bg_color="#fefce8", eye_color="#d97706")
        img, verification = render_pokemon_qr(payload, style, pokemon, sprite_bytes=sprite, output_size=640)
        assert img.size == (640, 640)
        assert verification["moduleCount"] >= 21

    card_style = QrStyleOptions(mode="badge", include_card_frame=True, card_headline="Scan Test", card_subtitle="PokéQR2")
    card_img, card_ver = render_pokemon_qr(payload, card_style, pokemon, sprite_bytes=sprite, output_size=600)
    assert card_img.size == (600, round(600 * 1.24))
    assert card_ver["verified"] is True

    svg = render_qr_svg(payload, QrStyleOptions(mode="badge"), pokemon, sprite_bytes=sprite, size=600)
    assert "<svg" in svg and "data:image/png;base64," in svg
