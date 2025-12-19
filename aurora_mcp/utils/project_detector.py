from __future__ import annotations

from pathlib import Path
from typing import Optional

# Common project root markers across ecosystems and tools
PROJECT_ROOT_MARKERS = [
    # Version Control
    ".git",
    ".hg",
    ".svn",
    # Python
    "pyproject.toml",
    # Node.js
    "package.json",
    # Rust
    "Cargo.toml",
    # Go
    "go.mod",
    # Java
    "pom.xml",
    "build.gradle",
    # C/C++
    "CMakeLists.txt",
    # PHP
    "composer.json",
    # Ruby
    "Gemfile",
    # IDE Projects
    ".project",  # Eclipse
]


def _candidate_directories(start_path: Path) -> list[Path]:
    """Return a list of directories to inspect, walking up to filesystem root."""
    return [start_path] + list(start_path.parents)


def _normalize_start_path(file_path: str) -> Optional[Path]:
    """Normalize user input to a directory to begin searching from."""
    if not file_path:
        return None
    try:
        path = Path(file_path).resolve()
        if path.exists():
            if path.is_file():
                return path.parent
            return path
        # For non-existent paths, fall back to parent if it looks like a file
        return path.parent if path.suffix else path
    except (OSError, ValueError):
        return None


def find_project_root(file_path: str | None) -> Optional[str]:
    """Find the project root directory by walking up from the given file path.

    Args:
        file_path: Absolute (or relative) path to a file or directory.

    Returns:
        Absolute path to project root as string, or None if not found or on error.
    """
    start_dir = _normalize_start_path(file_path) if file_path is not None else None
    if start_dir is None:
        return None

    try:
        for candidate in _candidate_directories(start_dir):
            for marker in PROJECT_ROOT_MARKERS:
                if (candidate / marker).exists():
                    return str(candidate)
            if candidate == candidate.parent:
                break
    except (OSError, ValueError):
        return None
    return None


def extract_project_name(project_path: str | None) -> str:
    """Extract a human-readable project name from the project path."""
    if not project_path:
        return ""
    try:
        return Path(project_path).name
    except (OSError, ValueError):
        return ""


def is_same_project(path1: Optional[str], path2: Optional[str]) -> bool:
    """Check if two paths belong to the same project."""
    if not path1 or not path2:
        return False
    try:
        return Path(path1).resolve() == Path(path2).resolve()
    except (OSError, ValueError):
        return False
