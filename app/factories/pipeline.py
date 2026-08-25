"""Factory for creating the AnalysisPipelineService and its complex dependency graph."""

import logging

from flask import current_app
from sqlalchemy.orm import Session

from app.clients.azure_openai import create_azure_openai_client
from app.clients.github import GitHubClient
from app.clients.neo4j import Neo4jClient
from app.graph.mappers.github import GitHubGraphMapper
from app.graph.repositories.code_graph import CodeGraphRepository
from app.graph.repositories.github_history import GitHubHistoryGraphRepository
from app.repositories.code_chunk import CodeChunkRepository
from app.repositories.commit_file_change import CommitFileChangeRepository
from app.repositories.repository import RepositoryStore
from app.services.analysis_pipeline import AnalysisPipelineService
from app.services.chunk_import import ChunkImportService
from app.services.code_graph_import import CodeGraphImportService
from app.services.embedding import EmbeddingService
from app.services.git_clone import GitCloneService
from app.services.github_history import GitHubHistoryCollector
from app.services.github_history_import import GitHubHistoryImportService
from app.services.method_history_index import MethodHistoryIndexer
from app.services.repository_identity import RepositoryIdentityValidator

logger = logging.getLogger(__name__)


def create_analysis_pipeline(
    session: Session,
    repository_url: str,
) -> AnalysisPipelineService:
    """Instantiate the analysis pipeline and all required services/clients.
    
    Args:
        session: An active SQLAlchemy DB session.
        repository_url: The GitHub URL to analyze (e.g. https://github.com/owner/repo)
    
    Returns:
        A fully configured AnalysisPipelineService.
    """
    config = current_app.config

    # 1. Parse owner and repo from URL
    # e.g., "https://github.com/foo/bar" -> owner="foo", repo="bar"
    url_parts = repository_url.rstrip("/").split("/")
    owner, repo_name = url_parts[-2], url_parts[-1]
    if repo_name.endswith(".git"):
        repo_name = repo_name[:-4]

    # 2. Setup Clients
    neo4j_client = Neo4jClient.from_config(config)
    
    # We dynamically pass the target repository to GitHubClient instead of using config
    github_client = GitHubClient(
        token=config["GITHUB_TOKEN"],
        owner=owner,
        repository=repo_name,
    )
    
    azure_openai_client = create_azure_openai_client(config)

    # 3. Setup Repositories
    repository_store = RepositoryStore(session)
    commit_file_change_repo = CommitFileChangeRepository(session)
    code_chunk_repo = CodeChunkRepository(session)
    
    code_graph_repo = CodeGraphRepository(neo4j_client)
    github_history_graph_repo = GitHubHistoryGraphRepository(neo4j_client)

    # 4. Setup Services
    git_clone_service = GitCloneService()
    
    # Code Graph Import
    def github_lookup(repo_id: int):
        return github_client.get_repository_by_id(repo_id)
        
    identity_validator = RepositoryIdentityValidator(neo4j_client, github_lookup)
    code_graph_import_service = CodeGraphImportService(
        graph_repository=code_graph_repo,
        identity_validator=identity_validator,
    )
    method_history_indexer = MethodHistoryIndexer(git_clone_service, code_graph_repo)
    
    # GitHub History Import
    github_collector = GitHubHistoryCollector(github_client)
    github_mapper = GitHubGraphMapper()
    history_import_service = GitHubHistoryImportService(
        collector=github_collector,
        file_change_repository=commit_file_change_repo,
        graph_mapper=github_mapper,
        graph_repository=github_history_graph_repo,
    )
    
    # Chunk & Embedding Import
    embedding_service = EmbeddingService(
        client=azure_openai_client,
        deployment=config["AZURE_OPENAI_EMBEDDING_DEPLOYMENT"],
    )
    chunk_import_service = ChunkImportService(
        chunk_repository=code_chunk_repo,
        embedding_service=embedding_service,
        on_progress=lambda message: logger.info("코드 청크 처리: %s", message),
    )
    
    # 5. Assemble Pipeline
    return AnalysisPipelineService(
        git_clone_service=git_clone_service,
        history_import_service=history_import_service,
        code_graph_import_service=code_graph_import_service,
        method_history_indexer=method_history_indexer,
        chunk_import_service=chunk_import_service,
        repository_store=repository_store,
    )
