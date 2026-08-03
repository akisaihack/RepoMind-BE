"""Chat query API endpoint."""

from flask import Blueprint, jsonify, request

chat_bp = Blueprint("chat", __name__)

@chat_bp.post("/sessions/<session_id>/chat")
def chat(session_id: str):
    """
    Handle chat queries for a specific session.
    Expects JSON payload with 'question' and optionally 'question_kind'.
    """
    data = request.get_json() or {}
    question = data.get("question")
    
    # TODO: DTO validation and RAG Pipeline execution will be implemented here.
    # Currently returning a placeholder response.
    
    return jsonify({
        "success": True,
        "data": {
            "session_id": session_id,
            "message": "API endpoint is configured. DTO and Logic pending."
        }
    }), 200
