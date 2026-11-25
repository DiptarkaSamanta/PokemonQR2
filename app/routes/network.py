from __future__ import annotations

from fastapi import APIRouter, Request

from ..config import AppConfig, get_lan_addresses


def create_network_router(config: AppConfig) -> APIRouter:
    router = APIRouter(prefix="/api/network", tags=["network"])

    @router.get("")
    @router.get("/")
    def get_network_info(request: Request) -> dict:
        port = request.url.port or config.port
        lan_options = get_lan_addresses(port)
        scheme = request.url.scheme or "http"
        host_header = request.headers.get("host") or f"localhost:{port}"
        request_origin = f"{scheme}://{host_header}"
        recommended = next((o["url"] for o in lan_options if o["isPrimary"]), None)
        if not recommended:
            recommended = lan_options[0]["url"] if lan_options else request_origin
        return {
            "requestOrigin": request_origin,
            "recommendedShareBase": recommended,
            "lanAddresses": lan_options,
            "port": port,
        }

    return router
