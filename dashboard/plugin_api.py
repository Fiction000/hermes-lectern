from fastapi import APIRouter, Body, HTTPException, Query
from fastapi.responses import JSONResponse
from pydantic import BaseModel

import importlib.util
from pathlib import Path

_spec = importlib.util.spec_from_file_location("hermes_lectern_core", Path(__file__).with_name("vault_core.py"))
if _spec is None or _spec.loader is None:
    raise RuntimeError("cannot load hermes-lectern core")
core = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(core)

router = APIRouter()


class ConfigBody(BaseModel):
    root: str
    exclude: list[str] | None = None
    attention_field: str | None = None
    inbox_folder: str | None = None
    locale: str | None = None


class PathBody(BaseModel):
    path: str


class NoteBody(BaseModel):
    path: str
    content: str
    base_sha256: str | None = None


def _call(fn, *args, **kwargs):
    try:
        return fn(*args, **kwargs)
    except core.VaultError as exc:
        return JSONResponse({"error": exc.code, **exc.extra}, status_code=exc.status)


@router.get("/status")
def get_status():
    return core.status()


@router.put("/config")
def put_config(body: ConfigBody):
    return _call(core.configure, body.root, body.exclude, body.attention_field, body.inbox_folder, body.locale or "auto")


@router.post("/refresh")
def post_refresh():
    return _call(core.refresh)


@router.get("/tree")
def get_tree(path: str = ""):
    return _call(core.tree, path)


@router.get("/notes")
def get_notes(folder: str = "", tag: str = "", sort: str = "mtime", limit: int = Query(100, ge=0, le=1000), offset: int = Query(0, ge=0)):
    return _call(core.list_notes, folder, tag, sort, limit, offset)


@router.get("/search")
def get_search(q: str = "", limit: int = Query(50, ge=0, le=500)):
    return _call(core.search, q, limit)


@router.get("/dashboard")
def get_dashboard():
    return _call(core.dashboard)


@router.get("/note")
def get_note(path: str):
    return _call(core.read_note, path)


@router.put("/note")
def put_note(body: NoteBody):
    if body.base_sha256 is None:
        raise HTTPException(422, {"error": "base_sha256_required"})
    return _call(core.save_note, body.path, body.content, body.base_sha256)


@router.post("/note")
def post_note(body: NoteBody):
    return _call(core.create_note, body.path, body.content)


@router.post("/note/trash")
def post_trash(body: PathBody = Body(...)):
    return _call(core.trash_note, body.path)
