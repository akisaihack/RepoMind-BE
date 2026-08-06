"""Session management API endpoints."""

from flask import Blueprint, jsonify, request
from dataclasses import asdict

from app.dtos.sessions import SessionCreateRequest
from app.sample.mock_sessions import (
    get_mock_session_response,
    get_mock_message_history,
    get_mock_session_list,
)

sessions_bp = Blueprint("sessions", __name__)


@sessions_bp.post("/")
def create_session():
    """
    특정 레포지토리에 대한 신규 질의응답 세션(대화방) 생성.
    
    <pre>
        repo_id를 받아 새로운 대화 공간(session_id)을 할당하고 반환합니다.
        (현재는 프론트엔드 연동을 위한 Mock 응답 반환)
    </pre>
    """
    data = request.get_json() or {}
    req = SessionCreateRequest(
        repo_id=data.get("repo_id", ""),
        title=data.get("title")
    )
    
    # TODO: 실제 DB 세션 생성 및 저장 로직 추가 예정
    response_data = get_mock_session_response(req.repo_id, req.title)
    
    return jsonify({
        "success": True,
        "data": asdict(response_data)
    }), 201


@sessions_bp.get("/<session_id>/messages")
def get_session_messages(session_id: str):
    """
    기존 대화방의 과거 메시지(질문/답변) 내역 조회.
    
    <pre>
        페이지를 새로고침하더라도 대화 히스토리를 불러오기 위해 사용됩니다.
        (현재는 두 개의 샘플 메시지를 포함한 Mock 응답 반환)
    </pre>
    """
    # TODO: DB에서 session_id로 메시지 목록 불러오는 로직 추가 예정
    response_data = get_mock_message_history(session_id)
    
    return jsonify({
        "success": True,
        "data": asdict(response_data)
    }), 200


@sessions_bp.get("/")
def list_sessions():
    """
    생성된 전체 대화 세션 목록 반환 (옵션 API).
    """
    repo_id = request.args.get("repo_id")
    
    # TODO: DB에서 전체 세션 또는 repo_id에 속한 세션 목록 조회
    response_data = get_mock_session_list(repo_id)
    
    return jsonify({
        "success": True,
        "data": response_data
    }), 200
