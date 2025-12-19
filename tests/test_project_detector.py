from __future__ import annotations

import time
from pathlib import Path

import pytest

from aurora_mcp.utils.project_detector import (
    PROJECT_ROOT_MARKERS,
    extract_project_name,
    find_project_root,
    is_same_project,
)


def test_markers_complete():
    expected = {
        ".git",
        ".hg",
        ".svn",
        "pyproject.toml",
        "package.json",
        "Cargo.toml",
        "go.mod",
        "pom.xml",
        "build.gradle",
        "CMakeLists.txt",
        "composer.json",
        "Gemfile",
        ".project",
    }
    assert expected.issubset(set(PROJECT_ROOT_MARKERS))


def test_find_project_root_simple(tmp_path: Path):
    project_root = tmp_path / "myproj"
    project_root.mkdir()
    marker = project_root / "pyproject.toml"
    marker.write_text("[project]\nname='myproj'\n")
    nested = project_root / "src" / "pkg"
    nested.mkdir(parents=True)
    file_path = nested / "main.py"
    file_path.write_text("print('hello')")

    result = find_project_root(str(file_path))
    assert result == str(project_root)


def test_prefers_nearest_marker(tmp_path: Path):
    outer = tmp_path / "outer"
    inner = outer / "inner"
    inner.mkdir(parents=True)
    (outer / "pyproject.toml").write_text("outer")
    (inner / "package.json").write_text("{}")
    file_path = inner / "src" / "index.js"
    file_path.parent.mkdir(parents=True)
    file_path.write_text("// js")

    result = find_project_root(str(file_path))
    assert result == str(inner)


def test_no_marker_returns_none(tmp_path: Path):
    dir_path = tmp_path / "nomarker"
    dir_path.mkdir()
    result = find_project_root(str(dir_path / "file.txt"))
    assert result is None


def test_symlink_resolution(tmp_path: Path):
    project = tmp_path / "project"
    project.mkdir()
    (project / ".git").mkdir()
    real_dir = project / "real"
    real_dir.mkdir()
    target = real_dir / "file.py"
    target.write_text("print('x')")
    symlink_path = project / "link.py"
    symlink_path.symlink_to(target)

    result = find_project_root(str(symlink_path))
    assert result == str(project)


def test_extract_project_name():
    assert extract_project_name("/Users/user/projects/AuroraKB") == "AuroraKB"
    assert extract_project_name(None) == ""
    assert extract_project_name("") == ""


def test_is_same_project():
    assert is_same_project("/a/b", "/a/b") is True
    assert is_same_project("/a/b", "/a/c") is False
    assert is_same_project(None, "/a/c") is False
    assert is_same_project("/a/b", None) is False


def test_edge_cases(tmp_path: Path):
    assert find_project_root("") is None
    assert find_project_root(None) is None

    deep_path = "/".join(["/a"] * 25) + "/file.py"
    assert find_project_root(deep_path) is None

    special_root = tmp_path / "my project (2024)"
    special_root.mkdir()
    (special_root / "package.json").write_text("{}")
    special_file = special_root / "src" / "main.js"
    special_file.parent.mkdir(parents=True)
    special_file.write_text("// ok")
    assert find_project_root(str(special_file)) == str(special_root)

    assert find_project_root("/nonexistent/path/file.py") is None
    assert find_project_root(str(tmp_path / "randomfile")) is None


def test_performance(tmp_path: Path):
    project = tmp_path / "proj"
    project.mkdir()
    (project / ".git").mkdir()
    file_path = project / "src" / "main.py"
    file_path.parent.mkdir(parents=True)
    file_path.write_text("print('ok')")

    # Warm-up
    find_project_root(str(file_path))

    iterations = 500
    start = time.perf_counter()
    for _ in range(iterations):
        find_project_root(str(file_path))
    end = time.perf_counter()

    avg_ms = (end - start) / iterations * 1000
    # Keep a modest threshold to avoid flakiness in CI while ensuring fast path
    assert avg_ms < 5.0, f"Average time {avg_ms:.3f}ms exceeds threshold"
