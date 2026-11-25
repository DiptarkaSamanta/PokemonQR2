from __future__ import annotations

import hashlib
import hmac
import json
import os
import re
import secrets
import sqlite3
import threading
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from .config import AppConfig

SLUG_PATTERN = re.compile(r"^[a-zA-Z0-9_-]{3,48}$")
ID_ALPHABET = "abcdefghjkmnpqrstuvwxyz23456789"


def is_valid_slug(value: str) -> bool:
    return bool(SLUG_PATTERN.match(value))


def generate_share_id() -> str:
    return "".join(secrets.choice(ID_ALPHABET) for _ in range(7))


def hash_pin(pin: str) -> str:
    salt = secrets.token_hex(16)
    derived = hashlib.scrypt(pin.encode("utf-8"), salt=salt.encode("utf-8"), n=16384, r=8, p=1, dklen=32)
    return f"{salt}:{derived.hex()}"


def verify_pin_hash(pin: str, stored_hash: str) -> bool:
    if ":" not in stored_hash:
        return False
    salt, key_hex = stored_hash.split(":", 1)
    try:
        key_bytes = bytes.fromhex(key_hex)
    except ValueError:
        return False
    derived = hashlib.scrypt(pin.encode("utf-8"), salt=salt.encode("utf-8"), n=16384, r=8, p=1, dklen=32)
    return hmac.compare_digest(key_bytes, derived)


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _parse_iso(ts: str | None) -> datetime | None:
    if not ts:
        return None
    try:
        return datetime.fromisoformat(ts.replace("Z", "+00:00"))
    except ValueError:
        return None


EXPIRY_DELTAS: dict[str, timedelta | None] = {
    "1h": timedelta(hours=1),
    "24h": timedelta(hours=24),
    "7d": timedelta(days=7),
    "30d": timedelta(days=30),
    "never": None,
}


class ShareStore:
    def __init__(self, config: AppConfig) -> None:
        self.config = config
        self._lock = threading.Lock()
        self._token_secret = (
            os.environ.get("POKEQR2_TOKEN_SECRET") or secrets.token_hex(32)
        ).encode("utf-8")
        self._init_db()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.config.db_path, check_same_thread=False)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        return conn

    def _init_db(self) -> None:
        self.config.data_dir.mkdir(parents=True, exist_ok=True)
        self.config.uploads_dir.mkdir(parents=True, exist_ok=True)
        self.config.sprites_cache_dir.mkdir(parents=True, exist_ok=True)

        with self._lock, self._connect() as conn:
            conn.execute("PRAGMA journal_mode = WAL")
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS shares (
                    id TEXT PRIMARY KEY,
                    kind TEXT NOT NULL,
                    title TEXT NOT NULL,
                    note TEXT NOT NULL DEFAULT '',
                    pokemon_json TEXT,
                    pin_hash TEXT,
                    direct_redirect INTEGER NOT NULL DEFAULT 0,
                    created_at TEXT NOT NULL,
                    expires_at TEXT,
                    max_downloads INTEGER,
                    views INTEGER NOT NULL DEFAULT 0,
                    downloads INTEGER NOT NULL DEFAULT 0
                );

                CREATE TABLE IF NOT EXISTS share_links (
                    id TEXT PRIMARY KEY,
                    share_id TEXT NOT NULL REFERENCES shares(id) ON DELETE CASCADE,
                    label TEXT NOT NULL,
                    url TEXT NOT NULL,
                    position INTEGER NOT NULL DEFAULT 0
                );

                CREATE TABLE IF NOT EXISTS share_files (
                    id TEXT PRIMARY KEY,
                    share_id TEXT NOT NULL REFERENCES shares(id) ON DELETE CASCADE,
                    original_name TEXT NOT NULL,
                    stored_name TEXT NOT NULL,
                    mime_type TEXT NOT NULL,
                    size INTEGER NOT NULL,
                    position INTEGER NOT NULL DEFAULT 0
                );
                """
            )

    def resolve_stored_file_path(self, stored_name: str) -> Path | None:
        if not stored_name or ".." in stored_name or "/" in stored_name or "\\" in stored_name:
            return None
        base = self.config.uploads_dir.resolve()
        candidate = (base / stored_name).resolve()
        try:
            candidate.relative_to(base)
        except ValueError:
            return None
        return candidate

    def _remove_files_from_disk(self, files: list[dict[str, Any]]) -> None:
        for f in files:
            target = self.resolve_stored_file_path(f["stored_name"])
            if target and target.exists():
                target.unlink(missing_ok=True)

    def is_expired(self, share: dict[str, Any]) -> bool:
        exp = _parse_iso(share.get("expires_at"))
        return exp is not None and exp <= _utc_now()

    def is_download_limit_reached(self, share: dict[str, Any]) -> bool:
        max_dl = share.get("max_downloads")
        return max_dl is not None and share["downloads"] >= max_dl

    def purge_expired(self) -> int:
        now_iso = _utc_now().isoformat()
        removed_files: list[dict[str, Any]] = []
        removed_count = 0
        with self._lock, self._connect() as conn:
            rows = conn.execute(
                "SELECT id, expires_at FROM shares WHERE expires_at IS NOT NULL"
            ).fetchall()
            expired_ids = [
                r["id"] for r in rows
                if (_parse_iso(r["expires_at"]) or _utc_now()) <= _parse_iso(now_iso)
            ]
            if expired_ids:
                placeholders = ",".join("?" for _ in expired_ids)
                file_rows = conn.execute(
                    f"SELECT stored_name FROM share_files WHERE share_id IN ({placeholders})",
                    expired_ids,
                ).fetchall()
                removed_files = [dict(r) for r in file_rows]
                conn.execute(
                    f"DELETE FROM shares WHERE id IN ({placeholders})",
                    expired_ids,
                )
                removed_count = len(expired_ids)

        if removed_files:
            self._remove_files_from_disk(removed_files)
        return removed_count

    def _hydrate(self, conn: sqlite3.Connection, row: sqlite3.Row) -> dict[str, Any]:
        share_id = row["id"]
        links = [
            {"id": r["id"], "label": r["label"], "url": r["url"]}
            for r in conn.execute(
                "SELECT id, label, url FROM share_links WHERE share_id = ? ORDER BY position ASC",
                (share_id,),
            ).fetchall()
        ]
        files = [
            {
                "id": r["id"],
                "original_name": r["original_name"],
                "stored_name": r["stored_name"],
                "mime_type": r["mime_type"],
                "size": r["size"],
            }
            for r in conn.execute(
                "SELECT id, original_name, stored_name, mime_type, size FROM share_files WHERE share_id = ? ORDER BY position ASC",
                (share_id,),
            ).fetchall()
        ]
        pokemon = json.loads(row["pokemon_json"]) if row["pokemon_json"] else None
        return {
            "id": row["id"],
            "kind": row["kind"],
            "title": row["title"],
            "note": row["note"],
            "pokemon": pokemon,
            "pin_hash": row["pin_hash"],
            "direct_redirect": bool(row["direct_redirect"]),
            "created_at": row["created_at"],
            "expires_at": row["expires_at"],
            "max_downloads": row["max_downloads"],
            "views": row["views"],
            "downloads": row["downloads"],
            "links": links,
            "files": files,
        }

    def create(self, record: dict[str, Any]) -> dict[str, Any]:
        with self._lock, self._connect() as conn:
            conn.execute(
                """
                INSERT INTO shares (
                    id, kind, title, note, pokemon_json, pin_hash,
                    direct_redirect, created_at, expires_at, max_downloads, views, downloads
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    record["id"],
                    record["kind"],
                    record["title"],
                    record["note"],
                    json.dumps(record["pokemon"]) if record.get("pokemon") else None,
                    record.get("pin_hash"),
                    1 if record.get("direct_redirect") else 0,
                    record["created_at"],
                    record.get("expires_at"),
                    record.get("max_downloads"),
                    record.get("views", 0),
                    record.get("downloads", 0),
                ),
            )
            for idx, link in enumerate(record.get("links", [])):
                conn.execute(
                    "INSERT INTO share_links (id, share_id, label, url, position) VALUES (?, ?, ?, ?, ?)",
                    (link["id"], record["id"], link["label"], link["url"], idx),
                )
            for idx, f in enumerate(record.get("files", [])):
                conn.execute(
                    """
                    INSERT INTO share_files (id, share_id, original_name, stored_name, mime_type, size, position)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        f["id"],
                        record["id"],
                        f["original_name"],
                        f["stored_name"],
                        f["mime_type"],
                        f["size"],
                        idx,
                    ),
                )
        return record

    def get(self, share_id: str) -> dict[str, Any] | None:
        with self._lock, self._connect() as conn:
            row = conn.execute("SELECT * FROM shares WHERE id = ?", (share_id,)).fetchone()
            if not row:
                return None
            hydrated = self._hydrate(conn, row)
            if self.is_expired(hydrated):
                conn.execute("DELETE FROM shares WHERE id = ?", (share_id,))
                self._remove_files_from_disk(hydrated["files"])
                return None
            return hydrated

    def list_shares(self) -> list[dict[str, Any]]:
        self.purge_expired()
        with self._lock, self._connect() as conn:
            rows = conn.execute("SELECT * FROM shares ORDER BY created_at DESC").fetchall()
            return [self._hydrate(conn, r) for r in rows]

    def increment_views(self, share_id: str) -> None:
        with self._lock, self._connect() as conn:
            conn.execute("UPDATE shares SET views = views + 1 WHERE id = ?", (share_id,))

    def increment_downloads(self, share_id: str) -> None:
        with self._lock, self._connect() as conn:
            conn.execute("UPDATE shares SET downloads = downloads + 1 WHERE id = ?", (share_id,))

    def delete(self, share_id: str) -> bool:
        removed_files: list[dict[str, Any]] = []
        with self._lock, self._connect() as conn:
            row = conn.execute("SELECT id FROM shares WHERE id = ?", (share_id,)).fetchone()
            if not row:
                return False
            file_rows = conn.execute(
                "SELECT stored_name FROM share_files WHERE share_id = ?", (share_id,)
            ).fetchall()
            removed_files = [dict(r) for r in file_rows]
            conn.execute("DELETE FROM shares WHERE id = ?", (share_id,))
        self._remove_files_from_disk(removed_files)
        return True

    def sign_unlock_token(self, share_id: str) -> str:
        exp_ms = int(time.time() * 1000) + 12 * 3600 * 1000
        payload = f"{share_id}.{exp_ms}".encode("utf-8")
        sig = hmac.new(self._token_secret, payload, hashlib.sha256).hexdigest()
        return f"{exp_ms}.{sig}"

    def verify_unlock_token(self, share_id: str, token: str) -> bool:
        if "." not in token:
            return False
        exp_str, sig_hex = token.split(".", 1)
        try:
            exp_ms = int(exp_str)
        except ValueError:
            return False
        if exp_ms < int(time.time() * 1000):
            return False
        payload = f"{share_id}.{exp_ms}".encode("utf-8")
        expected = hmac.new(self._token_secret, payload, hashlib.sha256).hexdigest()
        return hmac.compare_digest(sig_hex, expected)

    def is_authorized(self, share: dict[str, Any], pin: str | None = None, token: str | None = None) -> bool:
        pin_hash = share.get("pin_hash")
        if not pin_hash:
            return True
        if token and self.verify_unlock_token(share["id"], token):
            return True
        if pin and verify_pin_hash(pin, pin_hash):
            return True
        return False

    def to_public_info(self, share: dict[str, Any], unlocked: bool) -> dict[str, Any]:
        out: dict[str, Any] = {
            "id": share["id"],
            "kind": share["kind"],
            "title": share["title"],
            "note": share["note"] if unlocked else "",
            "pokemon": share["pokemon"],
            "hasPin": bool(share.get("pin_hash")),
            "unlocked": unlocked,
            "directRedirect": share["direct_redirect"],
            "createdAt": share["created_at"],
            "expiresAt": share.get("expires_at"),
            "maxDownloads": share.get("max_downloads"),
            "views": share["views"],
            "downloads": share["downloads"],
            "linksCount": len(share["links"]),
            "filesCount": len(share["files"]),
        }
        if unlocked:
            out["links"] = share["links"]
            out["files"] = [
                {
                    "id": f["id"],
                    "originalName": f["original_name"],
                    "mimeType": f["mime_type"],
                    "size": f["size"],
                }
                for f in share["files"]
            ]
        return out
