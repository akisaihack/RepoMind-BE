from flask import Blueprint, jsonify, request
from dataclasses import asdict
from app.dtos.chat import ChatRequest
from app.sample.mock_chat import get_mock_chat_response

chat_bp = Blueprint("chat", __name__)

@chat_bp.post("/sessions/<session_id>/chat")
def chat(session_id: str):
    """
    특정 세션에 대한 질의응답(Chat) 쿼리를 처리.
    
    <pre>
        JSON 페이로드로 'question'과 선택적인 'question_kind'를 전달받아
        RAG 파이프라인을 통해 답변, 근거, 그래프 데이터를 포함한 결과를 반환.
        (현재는 프론트엔드 연동을 위한 Mock 데이터를 반환 중)
    </pre>
    
    @param session_id 대화가 진행 중인 세션의 고유 ID
    @return JSON 형태의 질의응답 결과 (ChatResponseData)
    @throws KeyError 필수 JSON 필드가 누락된 경우 (추후 적용 예정)
    """
    data = request.get_json() or {}
    req = ChatRequest(
        question=data.get("question", ""),
        question_kind=data.get("question_kind")
    )
    
    # -------------------------------------------------------------------------
    # TODO: 실제 RAG 파이프라인 연동 시 아래 목(Mock) 데이터를 삭제하고 실제 생성 로직으로 교체.
    # -------------------------------------------------------------------------
    response_data = get_mock_chat_response()
    
    return jsonify({
        "success": True,
        "data": asdict(response_data)
    }), 200
