from __future__ import annotations

import json


def test_health_network_and_studio_html(client):
    home = client.get("/")
    assert home.status_code == 200
    assert "PokéQR2 Studio" in home.text

    health = client.get("/api/health")
    assert health.status_code == 200
    assert health.json()["ok"] is True

    net = client.get("/api/network")
    assert net.status_code == 200
    assert isinstance(net.json()["lanAddresses"], list)


def test_pokemon_search_and_sprite(client):
    feat = client.get("/api/pokemon/featured")
    assert feat.status_code == 200
    assert len(feat.json()["results"]) >= 15

    search = client.get("/api/pokemon?q=gengar")
    assert search.status_code == 200
    assert any(p["name"] == "gengar" for p in search.json()["results"])

    sprite = client.get("/api/pokemon/25/sprite?style=pixel")
    assert sprite.status_code == 200
    assert sprite.headers["content-type"].startswith("image/")


def test_qr_render_endpoints(client):
    preview = client.post(
        "/api/qr/render",
        json={
            "payload": "https://pokeapi.co",
            "style": {"mode": "pixelart"},
            "pokemon": {"id": 25, "name": "pikachu", "displayName": "Pikachu", "types": ["electric"]},
            "outputSize": 512,
            "format": "preview",
        },
    )
    assert preview.status_code == 200
    body = preview.json()
    assert body["imageDataUrl"].startswith("data:image/png;base64,")
    assert body["verification"]["verified"] is True

    png = client.post("/api/qr/render", json={"payload": "https://pokeapi.co", "format": "png", "outputSize": 512})
    assert png.status_code == 200
    assert png.headers["content-type"] == "image/png"
    assert png.content[:4] == b"\x89PNG"

    svg = client.post("/api/qr/render", json={"payload": "https://pokeapi.co", "style": {"mode": "badge"}, "format": "svg", "outputSize": 512})
    assert svg.status_code == 200
    assert "image/svg+xml" in svg.headers["content-type"]


def test_link_share_validation_and_redirect(client):
    bad = client.post("/api/shares", json={"links": [{"label": "Bad", "url": "javascript:alert(1)"}]})
    assert bad.status_code == 400

    ok = client.post(
        "/api/shares",
        json={
            "title": "Py Link",
            "customSlug": "py-pika",
            "directRedirect": True,
            "links": [{"label": "PokéAPI", "url": "https://pokeapi.co"}],
            "pokemon": {"id": 25, "name": "pikachu", "displayName": "Pikachu", "types": ["electric"]},
        },
    )
    assert ok.status_code == 201
    assert ok.json()["share"]["id"] == "py-pika"

    dup = client.post("/api/shares", json={"customSlug": "py-pika", "links": [{"label": "Dup", "url": "https://example.com"}]})
    assert dup.status_code == 409

    redir = client.get("/s/py-pika", follow_redirects=False)
    assert redir.status_code == 302
    assert redir.headers["location"] == "https://pokeapi.co"


def test_bundle_upload_zip_and_delete(client):
    res = client.post(
        "/api/shares",
        data={
            "title": "Charizard Py Bundle",
            "note": "Here are the Python assets",
            "links": json.dumps([{"label": "Docs", "url": "https://fastapi.tiangolo.com"}]),
            "pokemon": json.dumps({"id": 6, "name": "charizard", "displayName": "Charizard", "types": ["fire"]}),
        },
        files=[
            ("files", ("notes.txt", b"hello from python", "text/plain")),
            ("files", ("unsafe.html", b"<script>alert(1)</script>", "text/html")),
        ],
    )
    assert res.status_code == 201
    share = res.json()["share"]
    sid = share["id"]
    assert share["kind"] == "bundle"
    assert len(share["files"]) == 2

    html_f = next(f for f in share["files"] if f["originalName"] == "unsafe.html")
    dl_html = client.get(f"/api/shares/{sid}/files/{html_f['id']}?preview=1")
    assert dl_html.status_code == 200
    assert dl_html.headers["content-disposition"].startswith("attachment;")

    txt_f = next(f for f in share["files"] if f["originalName"] == "notes.txt")
    prev_txt = client.get(f"/api/shares/{sid}/files/{txt_f['id']}?preview=1")
    assert prev_txt.status_code == 200
    assert prev_txt.text == "hello from python"

    zip_res = client.get(f"/api/shares/{sid}/zip")
    assert zip_res.status_code == 200
    assert zip_res.content[:2] == b"PK"

    deleted = client.delete(f"/api/shares/{sid}")
    assert deleted.status_code == 200
    assert client.get(f"/api/shares/{sid}/public").status_code == 404


def test_pin_protection_and_max_downloads(client):
    res = client.post(
        "/api/shares",
        data={"title": "Secret Py TM", "pin": "mewtwo150", "maxDownloads": "1"},
        files=[("files", ("secret.txt", b"top secret", "text/plain"))],
    )
    assert res.status_code == 201
    sid = res.json()["share"]["id"]
    fid = res.json()["share"]["files"][0]["id"]

    locked = client.get(f"/api/shares/{sid}/public")
    assert locked.status_code == 200
    assert locked.json()["share"]["unlocked"] is False
    assert "files" not in locked.json()["share"]

    assert client.get(f"/api/shares/{sid}/files/{fid}").status_code == 401
    assert client.post(f"/api/shares/{sid}/verify", json={"pin": "wrong"}).status_code == 401

    unlock = client.post(f"/api/shares/{sid}/verify", json={"pin": "mewtwo150"})
    assert unlock.status_code == 200
    token = unlock.json()["token"]

    dl1 = client.get(f"/api/shares/{sid}/files/{fid}?token={token}")
    assert dl1.status_code == 200
    assert dl1.text == "top secret"

    dl2 = client.get(f"/api/shares/{sid}/files/{fid}?token={token}")
    assert dl2.status_code == 410
