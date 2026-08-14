"""Deterministic, repository-scoped identifiers shared by graph importers."""

import re

_WINDOWS_DRIVE = re.compile(r"^[A-Za-z]:")


def repository_key(github_repository_id: int) -> str:
    """Return the resource key for a GitHub repository."""
    _validate_repository_id(github_repository_id)
    return f"{github_repository_id}:repository"


def repository_scoped_key(
    github_repository_id: int,
    kind: str,
    value: str | int,
) -> str:
    """Return a deterministic key for a resource owned by a repository."""
    _validate_repository_id(github_repository_id)
    if not kind or ":" in kind:
        raise ValueError("Graph resource kind must be a non-empty value without ':'.")
    if value == "":
        raise ValueError("Graph resource value must not be empty.")
    return f"{github_repository_id}:{kind}:{value}"


def normalize_repository_path(path: str) -> str:
    """Normalize a repository-relative path without allowing root traversal."""
    if not isinstance(path, str) or not path.strip():
        raise ValueError("Repository path must be a non-empty string.")

    normalized = path.strip().replace("\\", "/")
    if normalized.startswith("/") or _WINDOWS_DRIVE.match(normalized):
        raise ValueError("Repository path must be relative to the repository root.")

    parts: list[str] = []
    for part in normalized.split("/"):
        if part in ("", "."):
            continue
        if part == "..":
            if not parts:
                raise ValueError("Repository path must not escape the repository root.")
            parts.pop()
            continue
        parts.append(part)

    if not parts:
        raise ValueError("Repository path must identify a file or directory.")
    return "/".join(parts)


def file_key(github_repository_id: int, path: str) -> str:
    """Return the shared File key used by GitHub and source-code graphs."""
    return repository_scoped_key(
        github_repository_id,
        "file",
        normalize_repository_path(path),
    )


def _validate_repository_id(github_repository_id: int) -> None:
    if not isinstance(github_repository_id, int) or isinstance(github_repository_id, bool):
        raise ValueError("GitHub repository ID must be an integer.")
    if github_repository_id <= 0:
        raise ValueError("GitHub repository ID must be positive.")
