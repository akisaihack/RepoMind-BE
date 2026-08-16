"""app/api/v1/chat.py가 호출할 질의응답 오케스트레이션 서비스.

app/services/code_graph_import.py와 같은 패턴: 요청을 받아서 -> 필요한
컨텍스트를 채우고 -> LangGraph 파이프라인을 실행하고 -> API 응답 DTO로
변환해서 반환.

아직 구현 전 — docs/langgraph_pipeline.md 4.11, 6번(미해결 이슈 1번:
세션↔레포 매핑) 참고.
"""

from app.ai.rag.pipeline import run_qa_pipeline
from app.dtos.chat import ChatRequest, ChatResponseData


class QAService:
    def __init__(self) -> None:
        # TODO: 세션 저장소(현재 app.repositories.memory_store, 추후 실제
        # DB)를 주입받아서 session_id -> github_repository_id를 조회할 수
        # 있어야 함. 지금은 세션↔레포 연결 자체가 미해결 상태.
        pass

    def ask(self, session_id: str, request: ChatRequest) -> ChatResponseData:
        """질문을 받아 파이프라인을 실행하고 ChatResponseData를 반환.

        app/api/v1/chat.py의
        `# TODO: 실제 RAG 파이프라인 연동 시 아래 목(Mock) 데이터를 삭제하고
        실제 생성 로직으로 교체` 자리에서 이 메서드를 호출하도록 교체하면 됨
        (get_mock_chat_response() 대신 이 메서드 호출).
        """
        raise NotImplementedError("아직 구현 전 — docs/langgraph_pipeline.md 4.11 참고")


__all__ = ["QAService", "run_qa_pipeline"]
