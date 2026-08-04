"""Tests for Session API endpoints."""

def test_create_session(client):
    """Test creating a new chat session for a repository."""
    repo_id = "test_repo_123"
    response = client.post(
        "/api/v1/sessions/",
        json={"repo_id": repo_id, "title": "My Test Session"}
    )
    assert response.status_code == 201
    
    data = response.get_json()
    assert data["success"] is True
    assert "session_id" in data["data"]
    assert data["data"]["repo_id"] == repo_id
    assert data["data"]["title"] == "My Test Session"


def test_get_session_messages(client):
    """Test fetching message history for a session."""
    session_id = "test_session_123"
    response = client.get(f"/api/v1/sessions/{session_id}/messages")
    assert response.status_code == 200
    
    data = response.get_json()
    assert data["success"] is True
    assert data["data"]["session_id"] == session_id
    assert isinstance(data["data"]["messages"], list)


def test_list_sessions(client):
    """Test listing chat sessions, optionally filtered by repo_id."""
    response = client.get("/api/v1/sessions/?repo_id=test_repo_123")
    assert response.status_code == 200
    
    data = response.get_json()
    assert data["success"] is True
    assert isinstance(data["data"]["sessions"], list)
