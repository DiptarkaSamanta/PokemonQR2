from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from .config import AppConfig, create_config, get_lan_addresses
from .db import ShareStore
from .pokemon_catalog import PokemonCatalog
from .routes.network import create_network_router
from .routes.pokemon import create_pokemon_router
from .routes.qr import create_qr_router
from .routes.shares import create_shares_router


def create_app(data_dir_override: str | Path | None = None) -> FastAPI:
    config: AppConfig = create_config(data_dir_override)
    store = ShareStore(config)
    catalog = PokemonCatalog(config)

    app = FastAPI(title="PokéQR2 — Python Pokémon QR & File Sharing Studio")
    app.state.config = config
    app.state.store = store
    app.state.catalog = catalog

    base_dir = Path(__file__).resolve().parent
    templates = Jinja2Templates(directory=str(base_dir / "templates"))
    app.mount("/static", StaticFiles(directory=str(base_dir / "static")), name="static")

    @app.get("/api/health")
    def health() -> dict:
        return {"ok": True, "service": "pokemon-qr2-python", "engine": "FastAPI + Pillow + Segno + OpenCV + SQLite"}

    app.include_router(create_network_router(config))
    app.include_router(create_pokemon_router(catalog))
    app.include_router(create_qr_router(catalog))
    app.include_router(create_shares_router(store, config))

    @app.get("/", response_class=HTMLResponse)
    def studio_page(request: Request) -> HTMLResponse:
        return templates.TemplateResponse(request=request, name="index.html")

    @app.get("/s/{share_id}", response_class=HTMLResponse, response_model=None)
    def share_landing_page(share_id: str, request: Request) -> HTMLResponse | RedirectResponse:
        share = store.get(share_id)
        if (
            share
            and share["direct_redirect"]
            and not share.get("pin_hash")
            and share["kind"] == "link"
            and len(share["links"]) == 1
            and not store.is_download_limit_reached(share)
        ):
            store.increment_views(share_id)
            return RedirectResponse(url=share["links"][0]["url"], status_code=302)
        return templates.TemplateResponse(
            request=request,
            name="share.html",
            context={"share_id": share_id},
        )

    return app


app = create_app()

if __name__ == "__main__":
    import uvicorn

    cfg = create_config()
    lans = get_lan_addresses(cfg.port)
    print("\nPokéQR2 (Python Edition) running on:")
    print(f"  Local:   http://localhost:{cfg.port}")
    for lan in lans:
        print(f"  Network: {lan['url']} ({lan['label']})")
    print("")
    uvicorn.run("app.main:app", host="0.0.0.0", port=cfg.port, reload=False)
