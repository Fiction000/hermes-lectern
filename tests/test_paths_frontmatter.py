import importlib.util
from pathlib import Path

CORE_PATH = Path(__file__).parents[1] / "dashboard" / "vault_core.py"
spec = importlib.util.spec_from_file_location("vault_core_test", CORE_PATH)
core = importlib.util.module_from_spec(spec)
spec.loader.exec_module(core)


def test_frontmatter_block_inline_and_scalars():
    text = '---\r\ntags:\r\n  - tasknote\r\n  - "domain/test"\r\nprojects: ["[[A]]", "B"]\r\nneeds_me: true\r\ndue: 2026-11-20\r\nowner: \'Tatsu\'\r\n---\r\n# 見出し\r\nbody'
    props, body = core.parse_frontmatter(text)
    assert props == {"tags": ["tasknote", "domain/test"], "projects": ["[[A]]", "B"], "needs_me": True, "due": "2026-11-20", "owner": "Tatsu"}
    assert body == "# 見出し\nbody"


def test_frontmatter_missing_or_unterminated_is_plain_text():
    for text in ("# no metadata", "---\ntitle: broken\n# body"):
        assert core.parse_frontmatter(text) == ({}, text)


def test_path_rejection_matrix(tmp_path):
    root = tmp_path / "vault"
    root.mkdir()
    (root / ".obsidian").mkdir()
    for bad in ("", "/abs.md", "a\\b.md", "a\x00b.md", "../x.md", "./x.md", "a/../x.md", ".hidden.md", "a/.hidden.md", "Attachments/x.md", "a.txt"):
        with __import__("pytest").raises(core.VaultError, match="bad_path"):
            core._validate(bad, note=True, root=root, exclude=["Attachments"])


def test_missing_nested_path_is_allowed(tmp_path):
    root = tmp_path / "vault"
    root.mkdir(); (root / ".obsidian").mkdir()
    assert core._validate("new/nested.md", note=True, root=root).as_posix().endswith("vault/new/nested.md")


def test_double_quoted_scalars_preserve_japanese_backslashes_and_common_escapes():
    assert core.parse_scalar(r'"日本語\メモ"') == r"日本語\メモ"
    assert core.parse_scalar(r'"first\nsecond"') == "first\nsecond"
    assert core.parse_scalar(r'"a\tb\"c\\d"') == 'a\tb"c\\d'


def test_quoted_value_keeps_hash_inside_quotes():
    fm, _ = core.parse_frontmatter('---\ntitle: "42: カード（notes-app #1）をどう閉じるか"\nnote: plain # comment\n---\n')
    assert fm["title"] == "42: カード（notes-app #1）をどう閉じるか"
    assert fm["note"] == "plain"
