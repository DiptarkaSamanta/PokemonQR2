from __future__ import annotations

import json
import re
import threading
import time
from pathlib import Path
from typing import Any

import requests

from .config import AppConfig

FALLBACK_POKEMON: list[dict[str, Any]] = [
    {"id": 1, "name": "bulbasaur", "displayName": "Bulbasaur", "types": ["grass", "poison"]},
    {"id": 4, "name": "charmander", "displayName": "Charmander", "types": ["fire"]},
    {"id": 6, "name": "charizard", "displayName": "Charizard", "types": ["fire", "flying"]},
    {"id": 7, "name": "squirtle", "displayName": "Squirtle", "types": ["water"]},
    {"id": 9, "name": "blastoise", "displayName": "Blastoise", "types": ["water"]},
    {"id": 25, "name": "pikachu", "displayName": "Pikachu", "types": ["electric"]},
    {"id": 26, "name": "raichu", "displayName": "Raichu", "types": ["electric"]},
    {"id": 39, "name": "jigglypuff", "displayName": "Jigglypuff", "types": ["normal", "fairy"]},
    {"id": 52, "name": "meowth", "displayName": "Meowth", "types": ["normal"]},
    {"id": 54, "name": "psyduck", "displayName": "Psyduck", "types": ["water"]},
    {"id": 59, "name": "arcanine", "displayName": "Arcanine", "types": ["fire"]},
    {"id": 65, "name": "alakazam", "displayName": "Alakazam", "types": ["psychic"]},
    {"id": 68, "name": "machamp", "displayName": "Machamp", "types": ["fighting"]},
    {"id": 94, "name": "gengar", "displayName": "Gengar", "types": ["ghost", "poison"]},
    {"id": 130, "name": "gyarados", "displayName": "Gyarados", "types": ["water", "flying"]},
    {"id": 131, "name": "lapras", "displayName": "Lapras", "types": ["water", "ice"]},
    {"id": 133, "name": "eevee", "displayName": "Eevee", "types": ["normal"]},
    {"id": 134, "name": "vaporeon", "displayName": "Vaporeon", "types": ["water"]},
    {"id": 135, "name": "jolteon", "displayName": "Jolteon", "types": ["electric"]},
    {"id": 136, "name": "flareon", "displayName": "Flareon", "types": ["fire"]},
    {"id": 143, "name": "snorlax", "displayName": "Snorlax", "types": ["normal"]},
    {"id": 149, "name": "dragonite", "displayName": "Dragonite", "types": ["dragon", "flying"]},
    {"id": 150, "name": "mewtwo", "displayName": "Mewtwo", "types": ["psychic"]},
    {"id": 151, "name": "mew", "displayName": "Mew", "types": ["psychic"]},
    {"id": 175, "name": "togepi", "displayName": "Togepi", "types": ["fairy"]},
    {"id": 196, "name": "espeon", "displayName": "Espeon", "types": ["psychic"]},
    {"id": 197, "name": "umbreon", "displayName": "Umbreon", "types": ["dark"]},
    {"id": 212, "name": "scizor", "displayName": "Scizor", "types": ["bug", "steel"]},
    {"id": 248, "name": "tyranitar", "displayName": "Tyranitar", "types": ["rock", "dark"]},
    {"id": 282, "name": "gardevoir", "displayName": "Gardevoir", "types": ["psychic", "fairy"]},
    {"id": 384, "name": "rayquaza", "displayName": "Rayquaza", "types": ["dragon", "flying"]},
    {"id": 445, "name": "garchomp", "displayName": "Garchomp", "types": ["dragon", "ground"]},
    {"id": 448, "name": "lucario", "displayName": "Lucario", "types": ["fighting", "steel"]},
    {"id": 658, "name": "greninja", "displayName": "Greninja", "types": ["water", "dark"]},
    {"id": 700, "name": "sylveon", "displayName": "Sylveon", "types": ["fairy"]},
    {"id": 778, "name": "mimikyu", "displayName": "Mimikyu", "types": ["ghost", "fairy"]},
]

POKEMON_TYPE_PALETTES: dict[str, dict[str, str]] = {
    "electric": {"name": "electric", "label": "Electric", "fg": "#1e1b4b", "fgSecondary": "#b45309", "eye": "#d97706", "bg": "#fefce8", "badgeBg": "#fef08a", "accent": "#eab308"},
    "fire": {"name": "fire", "label": "Fire", "fg": "#431407", "fgSecondary": "#dc2626", "eye": "#ea580c", "bg": "#fff7ed", "badgeBg": "#fed7aa", "accent": "#f97316"},
    "water": {"name": "water", "label": "Water", "fg": "#082f49", "fgSecondary": "#0284c7", "eye": "#0369a1", "bg": "#f0f9ff", "badgeBg": "#bae6fd", "accent": "#0ea5e9"},
    "grass": {"name": "grass", "label": "Grass", "fg": "#052e16", "fgSecondary": "#16a34a", "eye": "#15803d", "bg": "#f0fdf4", "badgeBg": "#bbf7d0", "accent": "#22c55e"},
    "psychic": {"name": "psychic", "label": "Psychic", "fg": "#500724", "fgSecondary": "#db2777", "eye": "#be185d", "bg": "#fdf2f8", "badgeBg": "#fbcfe8", "accent": "#ec4899"},
    "ghost": {"name": "ghost", "label": "Ghost", "fg": "#1e103c", "fgSecondary": "#6d28d9", "eye": "#5b21b6", "bg": "#f5f3ff", "badgeBg": "#ddd6fe", "accent": "#8b5cf6"},
    "dragon": {"name": "dragon", "label": "Dragon", "fg": "#1e1b4b", "fgSecondary": "#4338ca", "eye": "#3730a3", "bg": "#eef2ff", "badgeBg": "#c7d2fe", "accent": "#6366f1"},
    "dark": {"name": "dark", "label": "Dark", "fg": "#09090b", "fgSecondary": "#3f3f46", "eye": "#18181b", "bg": "#fafafa", "badgeBg": "#e4e4e7", "accent": "#52525b"},
    "fairy": {"name": "fairy", "label": "Fairy", "fg": "#4c0519", "fgSecondary": "#e11d48", "eye": "#be123c", "bg": "#fff1f2", "badgeBg": "#fecdd3", "accent": "#f43f5e"},
    "ice": {"name": "ice", "label": "Ice", "fg": "#083344", "fgSecondary": "#0891b2", "eye": "#0e7490", "bg": "#ecfeff", "badgeBg": "#a5f3fc", "accent": "#06b6d4"},
    "fighting": {"name": "fighting", "label": "Fighting", "fg": "#450a0a", "fgSecondary": "#b91c1c", "eye": "#991b1b", "bg": "#fef2f2", "badgeBg": "#fecaca", "accent": "#ef4444"},
    "poison": {"name": "poison", "label": "Poison", "fg": "#3b0764", "fgSecondary": "#9333ea", "eye": "#7e22ce", "bg": "#faf5ff", "badgeBg": "#e9d5ff", "accent": "#a855f7"},
    "ground": {"name": "ground", "label": "Ground", "fg": "#451a03", "fgSecondary": "#b45309", "eye": "#92400e", "bg": "#fffbeb", "badgeBg": "#fde68a", "accent": "#d97706"},
    "rock": {"name": "rock", "label": "Rock", "fg": "#1c1917", "fgSecondary": "#57534e", "eye": "#44403c", "bg": "#fafaf9", "badgeBg": "#e7e5e4", "accent": "#78716c"},
    "bug": {"name": "bug", "label": "Bug", "fg": "#1a2e05", "fgSecondary": "#4d7c0f", "eye": "#3f6212", "bg": "#f7fee7", "badgeBg": "#d9f99d", "accent": "#84cc16"},
    "steel": {"name": "steel", "label": "Steel", "fg": "#0f172a", "fgSecondary": "#475569", "eye": "#334155", "bg": "#f8fafc", "badgeBg": "#cbd5e1", "accent": "#64748b"},
    "flying": {"name": "flying", "label": "Flying", "fg": "#172554", "fgSecondary": "#2563eb", "eye": "#1d4ed8", "bg": "#eff6ff", "badgeBg": "#bfdbfe", "accent": "#3b82f6"},
    "normal": {"name": "normal", "label": "Normal", "fg": "#0f172a", "fgSecondary": "#334155", "eye": "#dc2626", "bg": "#ffffff", "badgeBg": "#f1f5f9", "accent": "#ef4444"},
}


def get_palette_for_types(types: list[str] | None) -> dict[str, str]:
    primary = (types[0].lower() if types else "normal")
    return POKEMON_TYPE_PALETTES.get(primary, POKEMON_TYPE_PALETTES["normal"])


def _format_display_name(slug: str) -> str:
    return " ".join(part.capitalize() for part in slug.split("-"))


def generate_fallback_pokemon_svg(pokemon_id: int, label: str | None = None, type_name: str = "electric") -> str:
    palette = POKEMON_TYPE_PALETTES.get(type_name, POKEMON_TYPE_PALETTES["electric"])
    known = next((p for p in FALLBACK_POKEMON if p["id"] == pokemon_id), None)
    name = label or (known["displayName"] if known else f"PKMN #{pokemon_id}")
    initials = re.sub(r"[^a-zA-Z0-9 ]", "", name).strip()[:3].upper() or f"#{pokemon_id}"
    return (
        '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 256 256" width="256" height="256">'
        f'<defs><linearGradient id="bg" x1="0" y1="0" x2="1" y2="1">'
        f'<stop offset="0%" stop-color="{palette["badgeBg"]}"/>'
        f'<stop offset="100%" stop-color="{palette["accent"]}"/></linearGradient></defs>'
        '<circle cx="128" cy="128" r="118" fill="#ffffff" stroke="#0f172a" stroke-width="10"/>'
        '<path d="M 10 128 A 118 118 0 0 1 246 128 Z" fill="url(#bg)" stroke="#0f172a" stroke-width="10"/>'
        '<rect x="10" y="118" width="236" height="20" fill="#0f172a"/>'
        '<circle cx="128" cy="128" r="46" fill="#ffffff" stroke="#0f172a" stroke-width="10"/>'
        f'<text x="128" y="137" text-anchor="middle" font-family="sans-serif" font-weight="800" font-size="28" fill="#0f172a">{initials}</text>'
        f'<text x="128" y="210" text-anchor="middle" font-family="sans-serif" font-weight="700" font-size="22" fill="#334155">#{pokemon_id:03d}</text>'
        "</svg>"
    )


class PokemonCatalog:
    def __init__(self, config: AppConfig) -> None:
        self.config = config
        self._lock = threading.Lock()
        self._index_cache: list[dict[str, Any]] | None = None
        self._detail_cache: dict[str, dict[str, Any]] = {}
        for item in FALLBACK_POKEMON:
            self._detail_cache[str(item["id"])] = item
            self._detail_cache[item["name"].lower()] = item

    def load_index(self) -> list[dict[str, Any]]:
        with self._lock:
            if self._index_cache is not None:
                return self._index_cache

        cache_file = self.config.cache_dir / "pokemon-index.json"
        if cache_file.exists():
            try:
                if time.time() - cache_file.stat().st_mtime < 7 * 24 * 3600:
                    data = json.loads(cache_file.read_text(encoding="utf-8"))
                    if isinstance(data, list) and data:
                        with self._lock:
                            self._index_cache = data
                        return data
            except Exception:
                pass

        try:
            resp = requests.get("https://pokeapi.co/api/v2/pokemon?limit=1025", timeout=5)
            if resp.ok:
                results = resp.json().get("results", [])
                entries: list[dict[str, Any]] = []
                for row in results:
                    match = re.search(r"/pokemon/(\d+)/?$", row.get("url", ""))
                    if not match:
                        continue
                    pid = int(match.group(1))
                    slug = row["name"]
                    entries.append({
                        "id": pid,
                        "name": slug,
                        "displayName": _format_display_name(slug),
                    })
                if entries:
                    self.config.cache_dir.mkdir(parents=True, exist_ok=True)
                    cache_file.write_text(json.dumps(entries), encoding="utf-8")
                    with self._lock:
                        self._index_cache = entries
                    return entries
        except Exception:
            pass

        fallback = [{"id": p["id"], "name": p["name"], "displayName": p["displayName"]} for p in FALLBACK_POKEMON]
        with self._lock:
            self._index_cache = fallback
        return fallback

    def search(self, query: str = "", offset: int = 0, limit: int = 48) -> dict[str, Any]:
        all_entries = self.load_index()
        fallback_by_id = {p["id"]: p for p in FALLBACK_POKEMON}
        q = query.strip().lower()
        filtered = all_entries
        if q:
            q_num = q.lstrip("#")
            filtered = [
                p for p in all_entries
                if q in p["name"].lower()
                or q in p["displayName"].lower()
                or str(p["id"]) == q_num
                or q_num in f"{p['id']:03d}"
            ]

        slice_items = []
        for item in filtered[offset : offset + limit]:
            known = self._detail_cache.get(str(item["id"])) or fallback_by_id.get(item["id"])
            slice_items.append({
                "id": item["id"],
                "name": item["name"],
                "displayName": item["displayName"],
                "types": known["types"] if known else [],
            })

        return {
            "total": len(filtered),
            "offset": offset,
            "limit": limit,
            "results": slice_items,
        }

    def get_detail(self, id_or_name: str) -> dict[str, Any] | None:
        key = id_or_name.strip().lower()
        if not key or not re.match(r"^[a-z0-9-]+$", key):
            return None
        if key in self._detail_cache:
            return self._detail_cache[key]

        try:
            resp = requests.get(f"https://pokeapi.co/api/v2/pokemon/{key}", timeout=5)
            if resp.ok:
                payload = resp.json()
                entry = {
                    "id": int(payload["id"]),
                    "name": payload["name"],
                    "displayName": _format_display_name(payload["name"]),
                    "types": [t["type"]["name"] for t in payload.get("types", [])],
                }
                self._detail_cache[str(entry["id"])] = entry
                self._detail_cache[entry["name"].lower()] = entry
                return entry
        except Exception:
            pass

        if key.isdigit() and 1 <= int(key) <= 2000:
            pid = int(key)
            return {
                "id": pid,
                "name": f"pokemon-{pid}",
                "displayName": f"Pokémon #{pid}",
                "types": ["normal"],
            }
        return None

    def get_sprite_bytes(
        self,
        pokemon_id: int,
        style: str = "official",
        shiny: bool = False,
        type_hint: str | None = None,
    ) -> tuple[bytes, str]:
        safe_style = style if style in ("official", "home", "pixel") else "official"
        self.config.sprites_cache_dir.mkdir(parents=True, exist_ok=True)
        cache_path = self.config.sprites_cache_dir / f"{pokemon_id}-{safe_style}-{'shiny' if shiny else 'std'}.png"

        if cache_path.exists():
            return cache_path.read_bytes(), "image/png"

        shiny_seg = "shiny/" if shiny else ""
        if safe_style == "home":
            url = f"https://raw.githubusercontent.com/PokeAPI/sprites/master/sprites/pokemon/other/home/{shiny_seg}{pokemon_id}.png"
        elif safe_style == "pixel":
            url = f"https://raw.githubusercontent.com/PokeAPI/sprites/master/sprites/pokemon/{shiny_seg}{pokemon_id}.png"
        else:
            url = f"https://raw.githubusercontent.com/PokeAPI/sprites/master/sprites/pokemon/other/official-artwork/{shiny_seg}{pokemon_id}.png"

        try:
            resp = requests.get(url, timeout=6)
            if resp.ok and resp.content:
                cache_path.write_bytes(resp.content)
                return resp.content, resp.headers.get("content-type", "image/png")
        except Exception:
            pass

        known = self._detail_cache.get(str(pokemon_id))
        t = type_hint or (known["types"][0] if known and known.get("types") else "electric")
        svg = generate_fallback_pokemon_svg(pokemon_id, known["displayName"] if known else None, t)
        return svg.encode("utf-8"), "image/svg+xml; charset=utf-8"
