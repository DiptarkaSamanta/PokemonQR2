from __future__ import annotations

import os
import re
import socket
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class AppConfig:
    port: int
    data_dir: Path
    uploads_dir: Path
    cache_dir: Path
    sprites_cache_dir: Path
    db_path: Path
    max_file_size_bytes: int = 100 * 1024 * 1024
    max_files_per_share: int = 25


def create_config(data_dir_override: str | Path | None = None) -> AppConfig:
    port = int(os.environ.get("PORT", "3001"))
    base_data = Path(
        data_dir_override
        or os.environ.get("POKEQR2_DATA_DIR")
        or Path(__file__).resolve().parent.parent / "data"
    )
    uploads_dir = base_data / "uploads"
    cache_dir = base_data / "cache"
    sprites_cache_dir = cache_dir / "sprites"
    db_path = base_data / "pokeqr2.db"
    return AppConfig(
        port=port,
        data_dir=base_data,
        uploads_dir=uploads_dir,
        cache_dir=cache_dir,
        sprites_cache_dir=sprites_cache_dir,
        db_path=db_path,
    )


def _is_private_lan_ip(ip: str) -> bool:
    return (
        ip.startswith("192.168.")
        or ip.startswith("10.")
        or bool(re.match(r"^172\.(1[6-9]|2\d|3[01])\.", ip))
    )


def _score_interface(name: str, ip: str) -> tuple[int, bool]:
    lower = name.lower()
    looks_virtual = (
        "vethernet" in lower
        or "docker" in lower
        or "wsl" in lower
        or "virtual" in lower
        or "vmware" in lower
        or "vbox" in lower
        or ip.startswith("192.168.56.")
    )
    looks_wifi = (
        "wi-fi" in lower
        or "wifi" in lower
        or "wlan" in lower
        or "wireless" in lower
    )
    score = 0
    if _is_private_lan_ip(ip):
        score += 5
    if looks_wifi:
        score += 10
    if looks_virtual:
        score -= 10
    is_primary = _is_private_lan_ip(ip) and not looks_virtual
    return score, is_primary


def get_lan_addresses(port: int) -> list[dict[str, Any]]:
    discovered: list[tuple[str, str]] = []

    if os.name == "nt":
        try:
            proc = subprocess.run(
                ["ipconfig"],
                capture_output=True,
                text=True,
                timeout=3,
                check=False,
            )
            current_adapter = "Network"
            for line in proc.stdout.splitlines():
                stripped = line.strip()
                if line and not line.startswith(" ") and line.rstrip().endswith(":"):
                    current_adapter = (
                        line.rstrip(": \r\n")
                        .replace("Ethernet adapter ", "")
                        .replace("Wireless LAN adapter ", "")
                    )
                elif "IPv4" in stripped and ":" in stripped:
                    ip = stripped.split(":", 1)[1].strip().split("(")[0].strip()
                    if ip and not ip.startswith("127.") and not ip.startswith("169.254."):
                        discovered.append((current_adapter, ip))
        except Exception:
            discovered = []

    if not discovered:
        try:
            for info in socket.getaddrinfo(socket.gethostname(), None, socket.AF_INET):
                ip = str(info[4][0])
                if not ip.startswith("127.") and not ip.startswith("169.254."):
                    discovered.append(("Interface", ip))
        except Exception:
            pass

    seen: set[str] = set()
    scored: list[tuple[int, dict[str, Any]]] = []
    for name, ip in discovered:
        if ip in seen:
            continue
        seen.add(ip)
        score, is_primary = _score_interface(name, ip)
        scored.append(
            (
                score,
                {
                    "label": f"{name} ({ip})",
                    "address": ip,
                    "url": f"http://{ip}:{port}",
                    "isPrimary": is_primary,
                },
            )
        )

    scored.sort(key=lambda pair: pair[0], reverse=True)
    return [item for _, item in scored]
