import pytest
from uuid import uuid4
from flask import Flask

from app.repositories.repository import DuplicateRepositoryError
from app.repositories.memory_store import get_memory_store, InMemoryRepositoryStore

# No in-memory store reset needed anymore

def test_create_repository_success(client):
    response = client.post(
        "/api/v1/repositories/",
        json={"repository_url": "https://github.com/owner/repo"}
    )
    assert response.status_code == 201
    data = response.json["data"]
    assert data["repository_url"] == "https://github.com/owner/repo"
    assert data["branch"] == "main"
    assert data["analysis_status"] == "pending"

def test_create_repository_duplicate(client):
    client.post(
        "/api/v1/repositories/",
        json={"repository_url": "https://github.com/owner/repo", "branch": "main"}
    )
    response = client.post(
        "/api/v1/repositories/",
        json={"repository_url": "https://github.com/owner/repo", "branch": "main"}
    )
    assert response.status_code == 409
    assert response.json["error"]["code"] == "REPOSITORY_ALREADY_EXISTS"

def test_create_repository_invalid_url(client):
    response = client.post(
        "/api/v1/repositories/",
        json={"repository_url": "invalid-url"}
    )
    assert response.status_code == 400
    assert response.json["error"]["code"] == "INVALID_REPOSITORY_URL"

def test_list_repositories(client):
    client.post("/api/v1/repositories/", json={"repository_url": "https://github.com/owner/repo1"})
    client.post("/api/v1/repositories/", json={"repository_url": "https://github.com/owner/repo2"})
    
    response = client.get("/api/v1/repositories/")
    assert response.status_code == 200
    data = response.json["data"]["repositories"]
    assert len(data) == 2

def test_get_repository_success(client):
    create_response = client.post("/api/v1/repositories/", json={"repository_url": "https://github.com/owner/repo"})
    repo_id = create_response.json["data"]["id"]
    
    response = client.get(f"/api/v1/repositories/{repo_id}")
    assert response.status_code == 200
    assert response.json["data"]["id"] == repo_id
    assert response.json["data"]["repository_url"] == "https://github.com/owner/repo"

def test_get_repository_not_found(client):
    fake_id = str(uuid4())
    response = client.get(f"/api/v1/repositories/{fake_id}")
    assert response.status_code == 404
