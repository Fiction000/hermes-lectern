import base64
import importlib.util
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from test_index_refresh import vault  # noqa: F401  (fixture)
from test_paths_frontmatter import core

API_PATH = Path(__file__).parents[1] / "dashboard" / "plugin_api.py"
spec = importlib.util.spec_from_file_location("vault_api_asset_test", API_PATH)
api = importlib.util.module_from_spec(spec)
spec.loader.exec_module(api)
app = FastAPI(); app.include_router(api.router, prefix="/api/plugins/hermes-lectern")
client = TestClient(app)

PNG = b"\x89PNG\r\n\x1a\n" + b"fake-png-bytes"


def put(root, rel, data=PNG):
    p = root / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_bytes(data)
    return p


def code(fn, *args):
    with pytest.raises(core.VaultError) as info:
        fn(*args)
    return info.value.code


def test_relative_to_note_folder(vault):
    put(vault, "Notes/img/a.png")
    r = core.resolve_asset("img/a.png", "Notes/n.md")
    assert r["path"] == "Notes/img/a.png" and r["mime"] == "image/png" and r["size"] == len(PNG)
    assert base64.b64decode(r["data"]) == PNG


def test_root_fallback(vault):
    put(vault, "pics/a.png")
    assert core.resolve_asset("pics/a.png", "Notes/n.md")["path"] == "pics/a.png"


def test_bare_name_in_excluded_attachments(vault):
    put(vault, "Attachments/shot.jpg")
    r = core.resolve_asset("shot.jpg", "Notes/n.md")
    assert r["path"] == "Attachments/shot.jpg" and r["mime"] == "image/jpeg"


def test_same_folder_then_shortest_then_alphabetical(vault):
    put(vault, "one/x.png"); put(vault, "two/x.png"); put(vault, "two/deep/x.png"); put(vault, "x.png")
    assert core.resolve_asset("x.png", "two/n.md")["path"] == "two/x.png"
    assert core.resolve_asset("x.png", "elsewhere/n.md")["path"] == "x.png"
    (vault / "x.png").unlink()
    core.refresh()
    assert core.resolve_asset("x.png", "elsewhere/n.md")["path"] == "one/x.png"


def test_size_suffix_anchor_and_brackets_stripped(vault):
    put(vault, "Attachments/a.png")
    assert core.resolve_asset("a.png|300", "n.md")["path"] == "Attachments/a.png"
    assert core.resolve_asset("a.png#frag", "n.md")["path"] == "Attachments/a.png"
    assert core.resolve_asset("<a.png>", "n.md")["path"] == "Attachments/a.png"


def test_url_encoded_name(vault):
    put(vault, "Attachments/a b.png")
    assert core.resolve_asset("a%20b.png", "n.md")["path"] == "Attachments/a b.png"


@pytest.mark.parametrize("ext,mime", [("svg", "image/svg+xml"), ("webp", "image/webp"), ("gif", "image/gif"), ("avif", "image/avif"), ("bmp", "image/bmp"), ("jpeg", "image/jpeg")])
def test_mime_types(vault, ext, mime):
    put(vault, f"Attachments/i.{ext}", b"x")
    assert core.resolve_asset(f"i.{ext}")["mime"] == mime


def test_hidden_refused(vault):
    put(vault, ".hidden/a.png"); put(vault, ".b.png")
    assert code(core.resolve_asset, ".hidden/a.png") == "bad_asset_path"
    assert code(core.resolve_asset, ".b.png") == "bad_asset_path"
    core.refresh()
    assert code(core.resolve_asset, "a.png") == "asset_not_found"


def test_parent_absolute_empty_refused(vault, tmp_path):
    outside = put(tmp_path, "outside.png")
    assert code(core.resolve_asset, "../outside.png", "n.md") == "bad_asset_path"
    assert code(core.resolve_asset, "a/../../outside.png", "n.md") == "bad_asset_path"
    assert code(core.resolve_asset, str(outside), "n.md") == "bad_asset_path"
    assert code(core.resolve_asset, "", "n.md") == "bad_asset_path"
    assert code(core.resolve_asset, "|300", "n.md") == "bad_asset_path"


def test_symlinks_refused(vault, tmp_path):
    outside = put(tmp_path / "elsewhere", "secret.png")
    (vault / "Attachments").mkdir()
    (vault / "Attachments" / "link.png").symlink_to(outside)
    (vault / "linkdir").symlink_to(outside.parent)
    core.refresh()
    assert code(core.resolve_asset, "link.png") == "asset_not_found"  # symlinks are never indexed
    assert code(core.resolve_asset, "Attachments/link.png") == "bad_asset_path"
    assert code(core.resolve_asset, "linkdir/secret.png") == "bad_asset_path"


def test_non_image_refused(vault):
    put(vault, "Attachments/doc.pdf", b"%PDF"); put(vault, "n.md", b"# n")
    assert code(core.resolve_asset, "doc.pdf") == "not_image"
    assert code(core.resolve_asset, "n.md") == "not_image"


def test_too_large_refused(vault, monkeypatch):
    put(vault, "Attachments/big.png", b"x" * 11)
    monkeypatch.setattr(core, "MAX_ASSET_BYTES", 10)
    assert code(core.resolve_asset, "big.png") == "asset_too_large"
    assert core.MAX_ASSET_BYTES == 10


def test_default_limit_is_15_mb():
    assert core.MAX_ASSET_BYTES == 15 * 1024 * 1024


def test_missing(vault):
    assert code(core.resolve_asset, "nope.png", "n.md") == "asset_not_found"
    assert code(core.resolve_asset, "d/nope.png", "n.md") == "asset_not_found"


def test_cache_sees_new_image_after_refresh(vault):
    put(vault, "Attachments/a.png")
    assert core.resolve_asset("a.png")["path"] == "Attachments/a.png"
    put(vault, "Attachments/new.png", b"new")
    core.refresh()
    assert base64.b64decode(core.resolve_asset("new.png")["data"]) == b"new"


def test_cache_follows_config_change(vault, tmp_path):
    put(vault, "Attachments/a.png")
    core.resolve_asset("a.png")
    other = tmp_path / "other"; other.mkdir(); (other / ".obsidian").mkdir()
    put(other, "Attachments/b.png")
    core.configure(str(other))
    assert core.resolve_asset("b.png")["path"] == "Attachments/b.png"
    assert code(core.resolve_asset, "a.png") == "asset_not_found"


def test_http_route_returns_base64(vault):
    put(vault, "Notes/img/a.png")
    res = client.get("/api/plugins/hermes-lectern/asset", params={"path": "img/a.png", "from": "Notes/n.md"})
    assert res.status_code == 200
    body = res.json()
    assert body["mime"] == "image/png" and base64.b64decode(body["data"]) == PNG


def test_http_route_errors(vault):
    base = "/api/plugins/hermes-lectern/asset"
    assert client.get(base, params={"path": "../x.png"}).json() == {"error": "bad_asset_path"}
    assert client.get(base, params={"path": "x.png"}).status_code == 404
    assert client.get(base, params={"path": "x.txt"}).json() == {"error": "not_image"}
