"""MethodVersion-aware chunk import tests."""

from unittest.mock import Mock

from app.services.chunk_import import ChunkImportService


def test_reuses_existing_version_without_embedding_again(tmp_path) -> None:
    source = tmp_path / "App.java"
    source.write_text("class App { void run() {} }", encoding="utf-8")
    repository = Mock()
    repository.find_existing_graph_node_ids.side_effect = lambda ids: set(ids)
    embedding_service = Mock()
    messages: list[str] = []

    result = ChunkImportService(
        repository,
        embedding_service,
        on_progress=messages.append,
    ).import_repository(100, tmp_path, "abc123")

    assert result.chunks == 1
    embedding_service.embed.assert_not_called()
    repository.upsert_chunks.assert_not_called()
    assert any("reusing 1" in message for message in messages)


def test_embeds_only_new_method_versions(tmp_path) -> None:
    source = tmp_path / "App.java"
    source.write_text("class App { void first() {} void second() {} }", encoding="utf-8")
    repository = Mock()
    repository.find_existing_graph_node_ids.side_effect = lambda ids: {ids[0]}
    embedding_service = Mock()
    embedding_service.embed.return_value = [[0.0] * 1536]

    ChunkImportService(repository, embedding_service).import_repository(
        100, tmp_path, "abc123"
    )

    saved_chunks, saved_embeddings = repository.upsert_chunks.call_args.args
    assert len(saved_chunks) == 1
    assert len(saved_embeddings) == 1
