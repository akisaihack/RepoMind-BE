"""후속 질문 재작성 노드(question_rewriter.py) 통합 테스트.

실제 Flask app context + sqlite 테스트 DB로 ChatSession/ChatMessage를 만들어서,
노드가 세션의 이전 대화를 실제로 읽어오는지, 첫 질문(이력 없음)이면 LLM을 아예
안 부르는지를 확인한다. LLM 호출 자체는 create_azure_question_rewriter를
패치해서 대체한다 (question_classifier.py 계열 테스트와 동일한 패턴).
"""

from unittest.mock import Mock, patch

from app.ai.rag.nodes import question_rewriter
from app.extensions import db
from app.models.chat_session import ChatSession
from app.models.repository import Repository
from app.repositories.chat_message import ChatMessageStore


def _chat_session(*, suffix: str) -> ChatSession:
    repository = Repository(
        repository_url=f"https://github.com/example/repomind-{suffix}.git",
        branch="main",
    )
    return ChatSession(repository=repository, title="취소 요청 흐름")


def test_skips_rewrite_when_no_conversation_id(app) -> None:
    with app.app_context(), patch(
        "app.ai.rag.nodes.question_rewriter.create_azure_question_rewriter"
    ) as create_rewriter:
        result = question_rewriter.rewrite_follow_up_question(
            {"question": "취소 요청 흐름을 알려줘", "github_repository_id": 1}
        )

    assert result == {}
    create_rewriter.assert_not_called()


def test_skips_rewrite_on_first_question_in_session(app) -> None:
    with app.app_context():
        chat_session = _chat_session(suffix="first")
        db.session.add(chat_session)
        db.session.commit()
        session_id = str(chat_session.id)

        with patch(
            "app.ai.rag.nodes.question_rewriter.create_azure_question_rewriter"
        ) as create_rewriter:
            result = question_rewriter.rewrite_follow_up_question(
                {
                    "question": "취소 요청 흐름을 알려줘",
                    "github_repository_id": 1,
                    "conversation_id": session_id,
                }
            )

    assert result == {}
    create_rewriter.assert_not_called()


def test_rewrites_follow_up_question_using_session_history(app) -> None:
    with app.app_context():
        chat_session = _chat_session(suffix="history")
        db.session.add(chat_session)
        db.session.commit()
        session_id = str(chat_session.id)

        ChatMessageStore(db.session).create_exchange(
            session_id=chat_session.id,
            question="취소 요청은 어디서 처리돼?",
            answer="CancelController.cancel()에서 처리합니다.",
            structured_answer={"summary": "CancelController.cancel()에서 처리합니다."},
        )

        rewriter = Mock()
        rewriter.rewrite.return_value = "CancelController.cancel()을 어떻게 수정해야 해?"
        with patch(
            "app.ai.rag.nodes.question_rewriter.create_azure_question_rewriter",
            return_value=rewriter,
        ):
            result = question_rewriter.rewrite_follow_up_question(
                {
                    "question": "그거 어떻게 고쳐?",
                    "github_repository_id": 1,
                    "conversation_id": session_id,
                }
            )

    assert result == {"question": "CancelController.cancel()을 어떻게 수정해야 해?"}
    call_args = rewriter.rewrite.call_args.args
    assert call_args[0] == "그거 어떻게 고쳐?"
    assert "취소 요청은 어디서 처리돼?" in call_args[1]
    assert "CancelController.cancel()에서 처리합니다." in call_args[1]


def test_returns_empty_patch_when_rewrite_matches_original_question(app) -> None:
    with app.app_context():
        chat_session = _chat_session(suffix="unchanged")
        db.session.add(chat_session)
        db.session.commit()
        session_id = str(chat_session.id)

        ChatMessageStore(db.session).create_exchange(
            session_id=chat_session.id,
            question="이전 질문",
            answer="이전 답변",
            structured_answer={"summary": "이전 답변"},
        )

        rewriter = Mock()
        rewriter.rewrite.return_value = "이미 독립적인 질문이야"
        with patch(
            "app.ai.rag.nodes.question_rewriter.create_azure_question_rewriter",
            return_value=rewriter,
        ):
            result = question_rewriter.rewrite_follow_up_question(
                {
                    "question": "이미 독립적인 질문이야",
                    "github_repository_id": 1,
                    "conversation_id": session_id,
                }
            )

    assert result == {}
