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


def java_qualified_name(
    package_name: str | None,
    enclosing_names: tuple[str, ...],
    declaration_name: str,
) -> str:
    """Build a Java declaration name including its package and enclosing classes."""
    if not declaration_name or not declaration_name.strip():
        raise ValueError("Java declaration name must not be empty.")
    parts = [*(name.strip() for name in enclosing_names), declaration_name.strip()]
    if any(not part for part in parts):
        raise ValueError("Java enclosing declaration names must not be empty.")
    if package_name and package_name.strip():
        parts.insert(0, package_name.strip())
    return ".".join(parts)


def normalize_java_parameter_signature(signature: str) -> str:
    """Remove formatting-only whitespace from a parser-produced Java signature."""
    if not isinstance(signature, str) or not signature.strip():
        raise ValueError("Java parameter signature must not be empty.")
    normalized = re.sub(r"\s+", "", signature)
    if not normalized.startswith("(") or not normalized.endswith(")"):
        raise ValueError("Java parameter signature must be enclosed in parentheses.")
    return normalized


def class_key(
    github_repository_id: int,
    path: str,
    node_type: str,
    qualified_name: str,
) -> str:
    """Return a stable Class/Interface key independent of declaration order."""
    normalized_type = node_type.lower()
    if normalized_type not in {"class", "interface"}:
        raise ValueError("Java class node type must be 'class' or 'interface'.")
    if not qualified_name or not qualified_name.strip():
        raise ValueError("Java qualified name must not be empty.")
    value = f"{normalize_repository_path(path)}:{qualified_name.strip()}"
    return repository_scoped_key(github_repository_id, normalized_type, value)


def method_key(class_id: str, method_name: str, parameter_signature: str) -> str:
    """Return a stable method key, with overloads separated by parameter types."""
    if not class_id or not method_name or not method_name.strip():
        raise ValueError("Class key and method name must not be empty.")
    signature = normalize_java_parameter_signature(parameter_signature)
    return f"{class_id}:method:{method_name.strip()}:{signature}"


def constructor_key(class_id: str, class_name: str, parameter_signature: str) -> str:
    """Return a constructor key distinct from an equally named regular method."""
    if not class_id or not class_name or not class_name.strip():
        raise ValueError("Class key and constructor name must not be empty.")
    signature = normalize_java_parameter_signature(parameter_signature)
    return f"{class_id}:constructor:{class_name.strip()}:{signature}"


def _validate_repository_id(github_repository_id: int) -> None:
    if not isinstance(github_repository_id, int) or isinstance(github_repository_id, bool):
        raise ValueError("GitHub repository ID must be an integer.")
    if github_repository_id <= 0:
        raise ValueError("GitHub repository ID must be positive.")
