from __future__ import annotations

import json
import re
import tempfile
import uuid
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import quote, urlparse

from fastapi import APIRouter, HTTPException, Query, Request
from fastapi.responses import FileResponse, JSONResponse, StreamingResponse
from starlette.datastructures import UploadFile as StarletteUploadFile

from ..config import AppConfig
from ..db import EXPIRY_DELTAS, ShareStore, generate_share_id, hash_pin, is_valid_slug

SAFE_PREVIEW_MIMES = {
    "image/png",
    "image/jpeg",
    "image/jpg",
    "image/gif",
    "image/webp",
    "application/pdf",
    "audio/mpeg",
    "audio/mp3",
    "audio/wav",
    "audio/ogg",
    "audio/webm",
    "video/mp4",
    "video/webm",
    "text/plain",
    "application/json",
}


def _normalize_link_url(raw: str) -> str | None:
    trimmed = raw.strip()
    if not trimmed:
        return None
    candidate = trimmed if re.match(r"^[a-zA-Z][a-zA-Z0-9+.-]*:", trimmed) else f"https://{trimmed}"
    try:
        parsed = urlparse(candidate)
        if parsed.scheme not in ("http", "https") or not parsed.netloc:
            return None
        return parsed.geturl()
    except Exception:
        return None


def _sanitize_original_filename(name: str | None) -> str:
    base = Path(name or "file").name.replace("\r", "").replace("\n", "").replace("\0", "")
    return base[:180] or "file"


def _parse_json_field(val: Any, fallback: Any) -> Any:
    if val is None or val == "":
        return fallback
    if isinstance(val, str):
        try:
            return json.loads(val)
        except Exception:
            return fallback
    return val


def _extract_auth_credentials(request: Request, pin: str | None, token: str | None) -> tuple[str | None, str | None]:
    pin_hdr = request.headers.get("x-share-pin")
    tok_hdr = request.headers.get("x-share-token")
    return pin_hdr or pin, tok_hdr or token


def create_shares_router(store: ShareStore, config: AppConfig) -> APIRouter:
    router = APIRouter(prefix="/api/shares", tags=["shares"])

    @router.get("")
    @router.get("/")
    def list_shares() -> dict:
        shares = store.list_shares()
        return {"shares": [store.to_public_info(s, unlocked=False) for s in shares]}

    @router.post("", status_code=201)
    @router.post("/", status_code=201)
    async def create_share(request: Request) -> JSONResponse:
        content_type = request.headers.get("content-type", "")
        saved_paths: list[Path] = []

        try:
            uploaded_files_meta: list[dict[str, Any]] = []
            if "multipart/form-data" in content_type:
                form = await request.form()
                body: dict[str, Any] = {k: v for k, v in form.items() if not isinstance(v, StarletteUploadFile)}
                incoming_files = [v for v in form.getlist("files") if isinstance(v, StarletteUploadFile)]
                if len(incoming_files) > config.max_files_per_share:
                    raise HTTPException(
                        status_code=400,
                        detail=f"Maximum {config.max_files_per_share} files allowed per share",
                    )

                config.uploads_dir.mkdir(parents=True, exist_ok=True)
                for up in incoming_files:
                    orig_name = _sanitize_original_filename(up.filename)
                    ext = re.sub(r"[^a-zA-Z0-9.]", "", Path(orig_name).suffix)[:16]
                    stored_name = f"{uuid.uuid4()}{ext}"
                    dest = config.uploads_dir / stored_name
                    total_size = 0
                    with dest.open("wb") as fh:
                        while True:
                            chunk = await up.read(65536)
                            if not chunk:
                                break
                            total_size += len(chunk)
                            if total_size > config.max_file_size_bytes:
                                raise HTTPException(
                                    status_code=413,
                                    detail=f"File '{orig_name}' exceeds max upload size",
                                )
                            fh.write(chunk)
                    saved_paths.append(dest)
                    uploaded_files_meta.append(
                        {
                            "id": str(uuid.uuid4()),
                            "original_name": orig_name,
                            "stored_name": stored_name,
                            "mime_type": up.content_type or "application/octet-stream",
                            "size": total_size,
                        }
                    )
            else:
                raw_body = await request.json()
                if not isinstance(raw_body, dict):
                    raise HTTPException(status_code=400, detail="Invalid JSON body")
                body = raw_body

            raw_title = str(body.get("title") or "").strip()[:120]
            raw_note = str(body.get("note") or "").strip()[:2000]
            raw_slug = str(body.get("customSlug") or "").strip()
            raw_pin = str(body.get("pin") or "").strip()
            raw_expires = str(body.get("expiresIn") or "7d").strip()
            direct_redirect_raw = body.get("directRedirect")
            direct_redirect = direct_redirect_raw is True or str(direct_redirect_raw).lower() == "true"

            max_downloads: int | None = None
            raw_max_dl = body.get("maxDownloads")
            if raw_max_dl is not None and str(raw_max_dl).strip() != "":
                try:
                    parsed_dl = int(str(raw_max_dl).strip())
                except ValueError as exc:
                    raise HTTPException(status_code=400, detail="maxDownloads must be an integer between 1 and 100000") from exc
                if parsed_dl < 1 or parsed_dl > 100000:
                    raise HTTPException(status_code=400, detail="maxDownloads must be an integer between 1 and 100000")
                max_downloads = parsed_dl

            if raw_pin and (len(raw_pin) < 3 or len(raw_pin) > 32):
                raise HTTPException(status_code=400, detail="Passcode must be between 3 and 32 characters")

            if raw_slug:
                if not is_valid_slug(raw_slug):
                    raise HTTPException(status_code=400, detail="Custom slug must be 3-48 characters using letters, numbers, '-' or '_'")
                if store.get(raw_slug):
                    raise HTTPException(status_code=409, detail=f'Slug "{raw_slug}" is already in use')
                share_id = raw_slug
            else:
                share_id = generate_share_id()
                while store.get(share_id):
                    share_id = generate_share_id()

            raw_links = _parse_json_field(body.get("links"), [])
            links: list[dict[str, str]] = []
            if isinstance(raw_links, list):
                for item in raw_links:
                    if not isinstance(item, dict):
                        continue
                    url_str = str(item.get("url") or "").strip()
                    if not url_str:
                        continue
                    norm = _normalize_link_url(url_str)
                    if not norm:
                        raise HTTPException(
                            status_code=400,
                            detail=f'Invalid link URL: "{url_str}". Only http/https URLs are supported.',
                        )
                    label = str(item.get("label") or "").strip()[:80] or urlparse(norm).netloc
                    links.append({"id": str(uuid.uuid4()), "label": label, "url": norm})

            if not links and not uploaded_files_meta:
                raise HTTPException(status_code=400, detail="Provide at least one link or file to share")

            pokemon_raw = _parse_json_field(body.get("pokemon"), None)
            pokemon: dict[str, Any] | None = None
            if isinstance(pokemon_raw, dict) and isinstance(pokemon_raw.get("id"), int) and isinstance(pokemon_raw.get("displayName"), str):
                pokemon = {
                    "id": pokemon_raw["id"],
                    "name": str(pokemon_raw.get("name") or "")[:60],
                    "displayName": pokemon_raw["displayName"][:60],
                    "types": [str(t) for t in (pokemon_raw.get("types") or [])[:2]],
                    "shiny": bool(pokemon_raw.get("shiny")),
                    "artworkStyle": pokemon_raw.get("artworkStyle"),
                }

            if not uploaded_files_meta and links:
                kind = "link"
            elif uploaded_files_meta and not links:
                kind = "file"
            else:
                kind = "bundle"

            delta = EXPIRY_DELTAS.get(raw_expires, EXPIRY_DELTAS["7d"])
            now_dt = datetime.now(timezone.utc)
            expires_at = (now_dt + delta).isoformat() if delta else None

            default_title = raw_title or (
                uploaded_files_meta[0]["original_name"]
                if len(uploaded_files_meta) == 1 and not links
                else (
                    links[0]["label"]
                    if len(links) == 1 and not uploaded_files_meta
                    else (f"{pokemon['displayName']}'s PokéDrop" if pokemon else "PokéDrop Share")
                )
            )

            record = {
                "id": share_id,
                "kind": kind,
                "title": default_title,
                "note": raw_note,
                "links": links,
                "files": uploaded_files_meta,
                "pokemon": pokemon,
                "pin_hash": hash_pin(raw_pin) if raw_pin else None,
                "direct_redirect": bool(direct_redirect and kind == "link" and len(links) == 1 and not raw_pin),
                "created_at": now_dt.isoformat(),
                "expires_at": expires_at,
                "max_downloads": max_downloads,
                "views": 0,
                "downloads": 0,
            }
            store.create(record)

            return JSONResponse(
                status_code=201,
                content={
                    "share": store.to_public_info(record, unlocked=True),
                    "sharePath": f"/s/{share_id}",
                },
            )
        except HTTPException:
            for p in saved_paths:
                p.unlink(missing_ok=True)
            raise
        except Exception as exc:
            for p in saved_paths:
                p.unlink(missing_ok=True)
            raise HTTPException(status_code=500, detail=str(exc) or "Failed to create share") from exc

    @router.get("/{share_id}/public")
    def get_public_share(
        share_id: str,
        request: Request,
        trackView: str = Query(default="0"),
        pin: str | None = Query(default=None),
        token: str | None = Query(default=None),
    ) -> dict:
        share = store.get(share_id)
        if not share:
            raise HTTPException(status_code=404, detail="Share not found or expired")
        if store.is_download_limit_reached(share):
            raise HTTPException(status_code=410, detail="Download limit reached for this share")

        pin_val, tok_val = _extract_auth_credentials(request, pin, token)
        unlocked = store.is_authorized(share, pin_val, tok_val)

        if trackView == "1":
            store.increment_views(share_id)
            share["views"] += 1

        return {"share": store.to_public_info(share, unlocked=unlocked)}

    @router.post("/{share_id}/verify")
    async def verify_share_pin(share_id: str, request: Request) -> dict:
        share = store.get(share_id)
        if not share:
            raise HTTPException(status_code=404, detail="Share not found or expired")
        if store.is_download_limit_reached(share):
            raise HTTPException(status_code=410, detail="Download limit reached for this share")

        body = await request.json()
        pin_val = str(body.get("pin") or "").strip()
        if not store.is_authorized(share, pin=pin_val):
            raise HTTPException(status_code=401, detail="Incorrect passcode")

        token = store.sign_unlock_token(share_id)
        return {"token": token, "share": store.to_public_info(share, unlocked=True)}

    @router.get("/{share_id}/files/{file_id}")
    def download_or_preview_file(
        share_id: str,
        file_id: str,
        request: Request,
        preview: str = Query(default="0"),
        pin: str | None = Query(default=None),
        token: str | None = Query(default=None),
    ) -> FileResponse:
        share = store.get(share_id)
        if not share:
            raise HTTPException(status_code=404, detail="Share not found or expired")
        if store.is_download_limit_reached(share):
            raise HTTPException(status_code=410, detail="Download limit reached for this share")

        pin_val, tok_val = _extract_auth_credentials(request, pin, token)
        if not store.is_authorized(share, pin_val, tok_val):
            raise HTTPException(status_code=401, detail="Passcode required")

        file_meta = next((f for f in share["files"] if f["id"] == file_id), None)
        if not file_meta:
            raise HTTPException(status_code=404, detail="File not found in share")

        disk_path = store.resolve_stored_file_path(file_meta["stored_name"])
        if not disk_path or not disk_path.exists():
            raise HTTPException(status_code=404, detail="File missing on disk")

        wants_preview = preview == "1"
        safe_mime = file_meta["mime_type"].lower() in SAFE_PREVIEW_MIMES
        headers = {"X-Content-Type-Options": "nosniff"}

        if wants_preview and safe_mime:
            encoded = quote(file_meta["original_name"])
            headers["Content-Disposition"] = f"inline; filename*=UTF-8''{encoded}"
            return FileResponse(path=disk_path, media_type=file_meta["mime_type"], headers=headers)

        store.increment_downloads(share_id)
        return FileResponse(
            path=disk_path,
            filename=file_meta["original_name"],
            media_type="application/octet-stream",
            headers=headers,
        )

    @router.get("/{share_id}/zip")
    def download_zip(
        share_id: str,
        request: Request,
        pin: str | None = Query(default=None),
        token: str | None = Query(default=None),
    ) -> StreamingResponse:
        share = store.get(share_id)
        if not share:
            raise HTTPException(status_code=404, detail="Share not found or expired")
        if store.is_download_limit_reached(share):
            raise HTTPException(status_code=410, detail="Download limit reached for this share")

        pin_val, tok_val = _extract_auth_credentials(request, pin, token)
        if not store.is_authorized(share, pin_val, tok_val):
            raise HTTPException(status_code=401, detail="Passcode required")

        if not share["files"]:
            raise HTTPException(status_code=400, detail="This share has no files")

        store.increment_downloads(share_id)

        tmp = tempfile.SpooledTemporaryFile(max_size=10 * 1024 * 1024)
        used_names: dict[str, int] = {}
        with zipfile.ZipFile(tmp, "w", compression=zipfile.ZIP_DEFLATED) as zf:
            for f in share["files"]:
                disk_path = store.resolve_stored_file_path(f["stored_name"])
                if not disk_path or not disk_path.exists():
                    continue
                orig = f["original_name"]
                count = used_names.get(orig, 0)
                used_names[orig] = count + 1
                arc_name = (
                    orig
                    if count == 0
                    else f"{Path(orig).stem}-{count}{Path(orig).suffix}"
                )
                zf.write(disk_path, arcname=arc_name)
        tmp.seek(0)

        safe_zip = re.sub(r"[^a-zA-Z0-9_-]+", "-", share["title"])[:48] or share_id
        encoded_zip = quote(f"{safe_zip}.zip")

        def iterfile():
            try:
                while True:
                    chunk = tmp.read(65536)
                    if not chunk:
                        break
                    yield chunk
            finally:
                tmp.close()

        return StreamingResponse(
            iterfile(),
            media_type="application/zip",
            headers={"Content-Disposition": f"attachment; filename*=UTF-8''{encoded_zip}"},
        )

    @router.delete("/{share_id}")
    def delete_share(share_id: str) -> dict:
        if not store.delete(share_id):
            raise HTTPException(status_code=404, detail="Share not found")
        return {"deleted": True, "id": share_id}

    return router
