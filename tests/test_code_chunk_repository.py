"""PostgreSQL MethodVersion chunk persistence tests."""

from unittest.mock import Mock

from app.parsers.languages.java import parse_java_file
from app.repositories.code_chunk import CodeChunkRepository
from app.services.chunking import build_chunks_from_file


def _chunk():
    parsed = parse_java_file("src/App.java", b"class App { void run() {} }")
    return build_chunks_from_file(100, parsed, "abc123")[0]


def test_migrates_matching_legacy_chunk_to_method_version() -> None:
    session = Mock()
    missing = Mock()
    missing.one_or_none.return_value = None
    legacy_row = Mock()
    legacy = Mock()
    legacy.one_or_none.return_value = legacy_row
    session.scalars.side_effect = (missing, legacy)
    chunk = _chunk()

    CodeChunkRepository(session).upsert_chunks([chunk], [[0.0] * 1536])

    assert legacy_row.graph_node_id == chunk.graph_node_id
    assert legacy_row.method_node_id == chunk.method_node_id
    assert legacy_row.content_hash == chunk.content_hash
    session.add.assert_not_called()


def test_reuses_existing_method_version_without_legacy_lookup() -> None:
    session = Mock()
    existing_row = Mock()
    existing = Mock()
    existing.one_or_none.return_value = existing_row
    session.scalars.return_value = existing
    chunk = _chunk()

    CodeChunkRepository(session).upsert_chunks([chunk], [[0.0] * 1536])

    assert session.scalars.call_count == 1
    assert existing_row.method_node_id == chunk.method_node_id
    assert existing_row.content_hash == chunk.content_hash


def test_finds_existing_method_version_chunk_ids() -> None:
    session = Mock()
    result = Mock()
    result.all.return_value = ["version-a", "version-b"]
    session.scalars.return_value = result

    found = CodeChunkRepository(session).find_existing_graph_node_ids(
        ["version-a", "version-b", "version-c"]
    )

    assert found == {"version-a", "version-b"}
