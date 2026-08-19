from unittest.mock import MagicMock, patch

from app.factories.pipeline import create_analysis_pipeline
from app.services.analysis_pipeline import AnalysisPipelineService


def test_create_analysis_pipeline(app):
    session_mock = MagicMock()
    
    with app.app_context():
        # Set config to avoid ValueError
        app.config["NEO4J_URI"] = "bolt://localhost:7687"
        app.config["NEO4J_USERNAME"] = "neo4j"
        app.config["NEO4J_PASSWORD"] = "password"
        app.config["GITHUB_TOKEN"] = "fake-token"
        app.config["AZURE_OPENAI_ENDPOINT"] = "https://fake.openai.azure.com"
        app.config["AZURE_OPENAI_API_KEY"] = "fake-key"
        app.config["AZURE_OPENAI_EMBEDDING_DEPLOYMENT"] = "text-embedding-ada-002"
        
        with patch("app.factories.pipeline.Neo4jClient") as mock_neo4j:
            with patch("app.factories.pipeline.GitHubClient") as mock_github:
                with patch("app.factories.pipeline.create_azure_openai_client") as mock_openai:
                    pipeline = create_analysis_pipeline(
                        session=session_mock,
                        repository_url="https://github.com/myowner/myrepo.git"
                    )
                    
                    assert isinstance(pipeline, AnalysisPipelineService)
                    
                    # Verify dynamic GitHub Client initialization
                    mock_github.assert_called_once_with(
                        token="fake-token",
                        owner="myowner",
                        repository="myrepo"
                    )
