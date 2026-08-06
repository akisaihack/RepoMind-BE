"""Tests for Repository API endpoints."""

def test_create_repository(client):
    """Test creating a new repository analysis request."""
    response = client.post(
        "/api/v1/repositories/",
        json={"repo_url": "https://github.com/owner/repo"}
    )
    assert response.status_code == 201
    
    data = response.get_json()
    assert data["success"] is True
    assert "repo_id" in data["data"]
    assert data["data"]["status"] == "indexing"


def test_get_repository_status(client):
    """Test fetching the status of a repository analysis."""
    repo_id = "test_repo_123"
    response = client.get(f"/api/v1/repositories/{repo_id}")
    assert response.status_code == 200
    
    data = response.get_json()
    assert data["success"] is True
    assert data["data"]["repo_id"] == repo_id
    assert data["data"]["status"] == "completed"
    assert data["data"]["progress_percent"] == 100


def test_list_repositories(client):
    """Test listing all registered repositories."""
    response = client.get("/api/v1/repositories/")
    assert response.status_code == 200
    
    data = response.get_json()
    assert data["success"] is True
    assert isinstance(data["data"]["repositories"], list)
