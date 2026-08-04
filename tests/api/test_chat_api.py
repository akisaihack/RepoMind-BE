"""Tests for Chat Query API endpoint."""

def test_chat_query(client):
    """Test submitting a chat query and receiving a structured answer."""
    session_id = "test_session_123"
    response = client.post(
        f"/api/v1/sessions/{session_id}/chat",
        json={"question": "회원 탈퇴는 어떻게 해?"}
    )
    assert response.status_code == 200
    
    data = response.get_json()
    assert data["success"] is True
    
    # Check for the core fields expected by the frontend StructuredAnswer
    response_data = data["data"]
    assert "summary" in response_data
    assert isinstance(response_data["claims"], list)
    assert isinstance(response_data["evidence"], list)
    assert "confidence" in response_data
    
    # Check graph structure
    assert "graph" in response_data
    assert isinstance(response_data["graph"]["nodes"], list)
    assert isinstance(response_data["graph"]["edges"], list)
