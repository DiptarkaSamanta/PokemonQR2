from __future__ import annotations

import base64
import re
from typing import Any

from fastapi import APIRouter, HTTPException, Response
from pydantic import BaseModel, Field

from ..pokemon_catalog import POKEMON_TYPE_PALETTES, PokemonCatalog
from ..qr_engine import (
    QrStyleOptions,
    estimate_inline_byte_capacity,
    image_to_png_bytes,
    render_pokemon_qr,
    render_qr_svg,
)

DATA_URL_RE = re.compile(r"^data:image/[a-zA-Z0-9+.-]+;base64,(.+)$")


class QrStylePayload(BaseModel):
    mode: str = "pixelart"
    moduleShape: str = "rounded"
    eyeShape: str = "pokeball"
    ecLevel: str = "H"
    fgColor: str = "#1e1b4b"
    fgSecondaryColor: str = "#b45309"
    useGradient: bool = True
    bgColor: str = "#fefce8"
    eyeColor: str = "#d97706"
    badgeSizeRatio: float = Field(default=0.22, ge=0.14, le=0.30)
    badgeShape: str = "pokeball"
    halftoneIntensity: float = Field(default=0.65, ge=0.15, le=1.0)
    backdropOpacity: float = Field(default=0.30, ge=0.1, le=0.65)
    pixelSpriteScale: float = Field(default=0.38, ge=0.24, le=0.52)
    pixelSafeDots: bool = True
    neonTheme: str = "synthwave"
    neonGlowStrength: float = Field(default=0.75, ge=0.15, le=1.0)
    neonInverted: bool = True
    quietZoneModules: int = Field(default=3, ge=1, le=6)
    includeCardFrame: bool = False
    cardHeadline: str = "Scan to Open PokéDrop"
    cardSubtitle: str = "Shared via PokéQR2 (Python)"


class QrPokemonPayload(BaseModel):
    id: int = 25
    name: str = "pikachu"
    displayName: str = "Pikachu"
    types: list[str] = Field(default_factory=lambda: ["electric"])
    shiny: bool = False
    artworkStyle: str = "official"
    customImageDataUrl: str | None = None


class QrRenderRequest(BaseModel):
    payload: str = "https://pokeapi.co"
    style: QrStylePayload = Field(default_factory=QrStylePayload)
    pokemon: QrPokemonPayload = Field(default_factory=QrPokemonPayload)
    outputSize: int = Field(default=900, ge=256, le=2048)
    format: str = "preview"  # preview | png | svg


def _to_style_options(s: QrStylePayload) -> QrStyleOptions:
    return QrStyleOptions(
        mode=s.mode,
        module_shape=s.moduleShape,
        eye_shape=s.eyeShape,
        ec_level=s.ecLevel,
        fg_color=s.fgColor,
        fg_secondary_color=s.fgSecondaryColor,
        use_gradient=s.useGradient,
        bg_color=s.bgColor,
        eye_color=s.eyeColor,
        badge_size_ratio=s.badgeSizeRatio,
        badge_shape=s.badgeShape,
        halftone_intensity=s.halftoneIntensity,
        backdrop_opacity=s.backdropOpacity,
        pixel_sprite_scale=s.pixelSpriteScale,
        pixel_safe_dots=s.pixelSafeDots,
        neon_theme=s.neonTheme,
        neon_glow_strength=s.neonGlowStrength,
        neon_inverted=s.neonInverted,
        quiet_zone_modules=s.quietZoneModules,
        include_card_frame=s.includeCardFrame,
        card_headline=s.cardHeadline,
        card_subtitle=s.cardSubtitle,
    )


def _resolve_sprite_bytes(catalog: PokemonCatalog, req: QrRenderRequest) -> bytes | None:
    if req.pokemon.artworkStyle == "custom" and req.pokemon.customImageDataUrl:
        m = DATA_URL_RE.match(req.pokemon.customImageDataUrl.strip())
        if m:
            try:
                return base64.b64decode(m.group(1), validate=True)
            except Exception:
                return None
    art_style = "pixel" if req.style.mode == "pixelart" and req.pokemon.artworkStyle != "custom" else req.pokemon.artworkStyle
    if req.pokemon.id <= 0:
        return None
    data, _ = catalog.get_sprite_bytes(
        pokemon_id=req.pokemon.id,
        style=art_style,
        shiny=req.pokemon.shiny,
        type_hint=req.pokemon.types[0] if req.pokemon.types else None,
    )
    return data


def create_qr_router(catalog: PokemonCatalog) -> APIRouter:
    router = APIRouter(prefix="/api/qr", tags=["qr"])

    @router.get("/palettes")
    def get_palettes() -> dict[str, Any]:
        return {"palettes": POKEMON_TYPE_PALETTES}

    @router.post("/render")
    def render_qr(req: QrRenderRequest) -> Response:
        effective_payload = req.payload.strip() or "https://pokeapi.co"
        if len(effective_payload.encode("utf-8")) > 2950:
            raise HTTPException(status_code=400, detail="Payload exceeds maximum QR capacity")

        style_opts = _to_style_options(req.style)
        poke_dict = req.pokemon.model_dump()
        sprite_bytes = _resolve_sprite_bytes(catalog, req)

        img, verification = render_pokemon_qr(
            payload=effective_payload,
            style=style_opts,
            pokemon=poke_dict,
            sprite_bytes=sprite_bytes,
            output_size=req.outputSize,
        )

        if req.format == "png":
            png_bytes = image_to_png_bytes(img)
            filename = f"pokeqr2-{req.pokemon.name}-{req.outputSize}px.png"
            return Response(
                content=png_bytes,
                media_type="image/png",
                headers={
                    "Content-Disposition": f'attachment; filename="{filename}"',
                    "X-QR-Verified": str(verification["verified"]).lower(),
                },
            )

        if req.format == "svg":
            svg_text = render_qr_svg(
                payload=effective_payload,
                style=style_opts,
                pokemon=poke_dict,
                sprite_bytes=sprite_bytes,
                raster_fallback_img=img,
                size=req.outputSize,
            )
            filename = f"pokeqr2-{req.pokemon.name}.svg"
            return Response(
                content=svg_text.encode("utf-8"),
                media_type="image/svg+xml; charset=utf-8",
                headers={"Content-Disposition": f'attachment; filename="{filename}"'},
            )

        png_b64 = base64.b64encode(image_to_png_bytes(img)).decode("ascii")
        import json as _json

        return Response(
            content=_json.dumps(
                {
                    "imageDataUrl": f"data:image/png;base64,{png_b64}",
                    "verification": verification,
                    "inlineBytes": len(effective_payload.encode("utf-8")),
                    "inlineCapacity": estimate_inline_byte_capacity(req.style.ecLevel),
                }
            ),
            media_type="application/json",
        )

    return router
