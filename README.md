# PokéQR2 Studio (Python Edition)

A complete re-implementation of **PokéQR Studio** built with a **Python-native** backend and rendering stack:

- **Web Framework**: FastAPI + Uvicorn + Jinja2
- **Image & QR Rendering Engine**: Segno + Pillow + NumPy (server-side rendering of PNGs up to 2048px and SVGs)
- **Live Scannability Verification**: OpenCV (`cv2.QRCodeDetector`)
- **Database & File Sharing**: SQLite (`pokeqr2.db`) with `scrypt` PIN hashing, HMAC unlock tokens, safe inline file previews, and `.zip` bundle streaming
- **Frontend**: Lightweight zero-build HTML/CSS/Vanilla ES Modules

## Features
- **Share Links & Files**: Direct URLs, hosted short links, multi-file uploads, combined link+file bundles, tiny offline inline payloads, PIN lock, expiry, download limits, and Wi-Fi LAN IP auto-detection.
- **All 6 Pokémon QR Modes**:
  - **8-Bit Pixel Sprite** (grid-snapped pixel Pokémon with Segno 0–7 mask optimization)
  - **Neon Scene Glow** (synthwave/elemental glowing scene with neon corner/alignment eyes and glowing QR tiles)
  - **Center Badge** (`pokeball` / `circle` / `squircle`)
  - **Halftone Art Blend**, **Art Backdrop**, and **Clean Theme**
  - **Collectible PokéQR Share Card** frame export

## Quick Start (Windows)
Double-click `Start-PokeQR2.bat` or run:
```powershell
.venv\Scripts\python.exe -m app.main
```
Then open `http://localhost:3001`.

## Run Tests
```powershell
.venv\Scripts\pytest.exe
```
