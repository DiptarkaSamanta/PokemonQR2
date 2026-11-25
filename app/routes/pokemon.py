from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query, Response

from ..pokemon_catalog import FALLBACK_POKEMON, PokemonCatalog


def create_pokemon_router(catalog: PokemonCatalog) -> APIRouter:
    router = APIRouter(prefix="/api/pokemon", tags=["pokemon"])

    @router.get("")
    @router.get("/")
    def search_pokemon(
        q: str = Query(default=""),
        offset: int = Query(default=0, ge=0),
        limit: int = Query(default=48, ge=1, le=100),
    ) -> dict:
        return catalog.search(query=q, offset=offset, limit=limit)

    @router.get("/featured")
    def featured_pokemon() -> dict:
        return {"results": FALLBACK_POKEMON}

    @router.get("/{pokemon_id}/sprite")
    def get_sprite(
        pokemon_id: int,
        style: str = Query(default="official"),
        shiny: str = Query(default="0"),
        type: str | None = Query(default=None),
    ) -> Response:
        if pokemon_id <= 0 or pokemon_id > 5000:
            raise HTTPException(status_code=400, detail="Invalid Pokémon ID")
        is_shiny = shiny in ("1", "true", "True")
        data, content_type = catalog.get_sprite_bytes(
            pokemon_id=pokemon_id,
            style=style,
            shiny=is_shiny,
            type_hint=type,
        )
        max_age = "300" if "svg" in content_type else "604800"
        return Response(
            content=data,
            media_type=content_type,
            headers={"Cache-Control": f"public, max-age={max_age}"},
        )

    @router.get("/{id_or_name}")
    def get_detail(id_or_name: str) -> dict:
        detail = catalog.get_detail(id_or_name)
        if not detail:
            raise HTTPException(status_code=404, detail="Pokémon not found")
        return detail

    return router
