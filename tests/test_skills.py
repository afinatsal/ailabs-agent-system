"""Test skill filesystem (write/read/list/glob/grep/edit) & parsing blok file."""

import pytest

from ailabs.agents.base import FILE_BLOCK_RE
from ailabs.skills.base import SkillResult
from ailabs.skills.filesystem import (
    edit_file,
    glob_files,
    grep_files,
    list_files,
    read_file,
    write_file,
)
from ailabs.skills.registry import SkillRegistry


@pytest.fixture
def workspace(tmp_path):
    return {"workspace_path": str(tmp_path)}


def test_write_then_read(workspace):
    res = write_file(path="produk/index.html", content="<h1>Halo</h1>", **workspace)
    assert res.ok
    assert workspace["workspace_path"] in str(res.value)

    content = read_file(path="produk/index.html", **workspace)
    assert content.ok
    assert content.value == "<h1>Halo</h1>"


def test_path_traversal_rejected(workspace):
    res = write_file(path="../../etc/evil.txt", content="x", **workspace)
    assert isinstance(res, SkillResult)
    assert not res.ok
    assert "luar workspace" in res.error


def test_list_files(workspace):
    write_file(path="a.txt", content="1", **workspace)
    write_file(path="sub/b.txt", content="2", **workspace)
    assert list_files(**workspace) == ["a.txt", "sub/b.txt"]


def test_registry_discovers_filesystem_skills():
    reg = SkillRegistry()
    assert "write_file" in reg.names()
    assert "read_file" in reg.names()
    assert "list_files" in reg.names()
    assert "glob_files" in reg.names()
    assert "grep_files" in reg.names()
    assert "edit_file" in reg.names()


def test_glob_files(workspace):
    write_file(path="web/index.html", content="x", **workspace)
    write_file(path="web/style.css", content="x", **workspace)
    write_file(path="app.py", content="x", **workspace)
    res = glob_files(pattern="web/*", **workspace)
    assert res.ok
    assert res.value == ["web/index.html", "web/style.css"]


def test_grep_files(workspace):
    write_file(path="produk/index.html", content="<h1>Halo dunia</h1>", **workspace)
    write_file(path="produk/readme.md", content="# Judul", **workspace)
    res = grep_files(pattern="dunia", rel="produk", **workspace)
    assert res.ok
    assert "index.html:1" in res.value


def test_grep_no_match_ok_false(workspace):
    write_file(path="a.txt", content="abc", **workspace)
    res = grep_files(pattern="zzz", **workspace)
    assert isinstance(res, SkillResult)
    assert not res.ok


def test_edit_file(workspace):
    write_file(path="index.html", content="<h1>Halo</h1>", **workspace)
    res = edit_file(path="index.html", old="Halo", new="Selamat datang", **workspace)
    assert res.ok
    assert read_file(path="index.html", **workspace).value == "<h1>Selamat datang</h1>"


def test_edit_file_ambiguous_rejected(workspace):
    write_file(path="index.html", content="ulang ulang", **workspace)
    res = edit_file(path="index.html", old="ulang", new="x", **workspace)
    assert isinstance(res, SkillResult)
    assert not res.ok
    assert "unik" in res.error


def test_edit_file_missing_target(workspace):
    res = edit_file(path="tidak-ada.txt", old="a", new="b", **workspace)
    assert isinstance(res, SkillResult)
    assert not res.ok


def test_registry_context_injected(workspace):
    reg = SkillRegistry(context=workspace)
    skill = reg.get("write_file")
    res = skill.run(path="hello.md", content="hai")
    assert res.ok
    assert str(res.value).startswith(workspace["workspace_path"])


def test_file_block_regex():
    text = (
        "Penjelasan singkat...\n"
        "```file:web/index.html\n<h1>Hello</h1>\n```\n"
        "```file:README.md\n# Judul\n```\n"
    )
    blocks = [
        (m.group(1).strip(), m.group(2).rstrip("\n"))
        for m in FILE_BLOCK_RE.finditer(text)
    ]
    assert blocks == [
        ("web/index.html", "<h1>Hello</h1>"),
        ("README.md", "# Judul"),
    ]
