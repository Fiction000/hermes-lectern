import json

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from test_index_refresh import vault
from test_paths_frontmatter import core


def test_optional_dashboard_config_and_backward_compatibility(vault):
    config_path = core.config_path()
    config_path.write_text(json.dumps({"root": str(vault), "exclude": ["Attachments"]}))
    assert core.load_config() == {"root": str(vault), "exclude": ["Attachments"], "attention_field": None, "inbox_folder": None, "locale": "auto"}
    configured = core.configure(str(vault), attention_field="review_for", inbox_folder="Dropzone", locale="ja")
    assert configured["attention_field"] == "review_for"
    assert core.load_config() == configured
    assert core.status()["attention_field"] == "review_for"


def test_config_rejects_bad_optional_values(vault):
    for options in ({"attention_field": 2}, {"inbox_folder": "a/b"}, {"inbox_folder": ".hidden"}, {"locale": "fr"}):
        with pytest.raises(core.VaultError):
            core.configure(str(vault), **options)


def test_dashboard_uses_configured_attention_and_inbox(vault):
    (vault / "TaskNotes").mkdir()
    (vault / "TaskNotes" / "a.md").write_text("---\ntags: [tasknote]\nstatus: waiting\nreview_for: true\n---\n# A")
    (vault / "Dropzone").mkdir()
    (vault / "Dropzone" / "b.md").write_text("# B")
    core.configure(str(vault), attention_field="review_for", inbox_folder="Dropzone")
    core.refresh()
    result = core.dashboard()
    assert [item["path"] for item in result["attention"]] == ["TaskNotes/a.md"]
    assert [item["path"] for item in result["inbox"]] == ["Dropzone/b.md"]
    assert result["sections"]["attention"] is True
    core.configure(str(vault), attention_field=None, inbox_folder=None)
    result = core.dashboard()
    assert result["attention"] == [] and result["inbox"] == []
    assert result["sections"]["attention"] is False


def test_config_api_accepts_and_validates_optional_fields(vault):
    import importlib.util
    from pathlib import Path
    spec = importlib.util.spec_from_file_location("vault_api_under_test", Path(core.__file__).with_name("plugin_api.py"))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    app = FastAPI(); app.include_router(module.router)
    client = TestClient(app)
    response = client.put("/config", json={"root": str(vault), "attention_field": "review_for", "inbox_folder": "Dropzone", "locale": "en"})
    assert response.status_code == 200
    assert response.json()["locale"] == "en"
    assert client.put("/config", json={"root": str(vault), "inbox_folder": "a/b"}).status_code == 400


def test_status_reports_exclude_so_settings_can_round_trip(vault):
    core.configure(str(vault), exclude=["Attachments", "Templates"], locale="ja")
    assert core.status()["exclude"] == ["Attachments", "Templates"]


def test_dashboard_has_no_japanese_labels(vault):
    import re, json
    (vault / "TaskNotes").mkdir(exist_ok=True)
    (vault / "TaskNotes" / "t.md").write_text("---\ntags: [tasknote]\nstatus: in-progress\n---\nbody\n", encoding="utf-8")
    core.configure(str(vault))
    core.refresh()
    out = json.dumps(core.dashboard(), ensure_ascii=False)
    assert not re.search("[\u3040-\u30ff\u4e00-\u9fff]", out)
    assert "" in core.dashboard()["in_progress"]


def test_data_lives_under_hermes_lectern_and_old_settings_carry_over(vault):
    assert core.config_path().parent.name == "hermes-lectern"
    assert core.db_path().parent.name == "hermes-lectern"
    old = core.home() / "hermes-vault" / "config.json"
    old.parent.mkdir(parents=True, exist_ok=True)
    old.write_text(json.dumps({"root": str(vault), "locale": "ja", "attention_field": "needs_me"}))
    core.config_path().unlink(missing_ok=True)
    loaded = core.load_config()
    assert loaded["locale"] == "ja" and loaded["attention_field"] == "needs_me"
    assert core.config_path().exists() and old.exists()
