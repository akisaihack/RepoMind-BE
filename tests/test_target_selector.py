"""분석 대상 선택기의 휴리스틱·LLM·fallback 동작 검증."""

from unittest.mock import patch

from app.ai.rag.nodes.target_selector import select_target
from app.ai.target_selector import TargetSelector
from app.dtos.target_selection import SelectionSource, TargetSelectionDecision


class FakeSelector:
    def __init__(self, result=None, error=None):
        self.result = result
        self.error = error
        self.calls = 0

    def invoke(self, _input):
        self.calls += 1
        if self.error:
            raise self.error
        return self.result


def _hit(method: str, similarity: float, api_path: str | None = None) -> dict:
    return {
        "graph_node_id": f"version:{method}",
        "method_node_id": f"method:{method}",
        "text": f"void {method}() {{}}",
        "similarity": similarity,
        "path": "AuthController.java",
        "class_name": "AuthController",
        "method_name": method,
        "api_http_method": "POST",
        "api_path": api_path,
        "commit_hash": "abc123",
    }


def test_returns_none_without_candidates() -> None:
    assert TargetSelector().select("질문", []) is None


def test_exact_method_name_wins_over_unrelated_vector_candidate() -> None:
    vector = _hit("test_pre_delete_skips_plugin_table_when_absent", 0.9)
    exact = _hit("requestExport", 1.0)

    result = TargetSelector().select(
        "requestExport 함수에서 spinKey를 제거한 이유는?",
        [vector],
        exact_candidates=[exact],
        symbol_names=["requestExport", "spinKey"],
    )

    assert result.method_name == "requestExport"
    assert result.selection_source is SelectionSource.EXACT_SYMBOL


def test_exact_candidate_node_skips_azure_selector_creation(app) -> None:
    exact = _hit("requestExport", 1.0)

    with app.app_context(), patch(
        "app.ai.rag.nodes.target_selector.create_azure_target_selector"
    ) as create_selector:
        result = select_target(
            {
                "question": "requestExport 함수에서 spinKey를 제거한 이유는?",
                "symbol_results": [exact],
                "explicit_symbol_names": ["requestExport", "spinKey"],
                "vector_results": [_hit("unrelatedTest", 0.9)],
            }
        )

    create_selector.assert_not_called()
    assert result["selected_target"]["method_name"] == "requestExport"


def test_skips_llm_for_single_or_clear_score_candidate() -> None:
    llm = FakeSelector()
    single = TargetSelector(llm).select("로그인", [_hit("authenticateUser", 0.4)])
    clear = TargetSelector(llm).select(
        "로그인", [_hit("authenticateUser", 0.5), _hit("registerUser", 0.4)]
    )

    assert single.selection_source is SelectionSource.SINGLE_CANDIDATE
    assert clear.method_name == "authenticateUser"
    assert clear.selection_source is SelectionSource.SCORE
    assert llm.calls == 0


def test_ambiguous_login_candidates_are_selected_by_llm() -> None:
    llm = FakeSelector(
        TargetSelectionDecision(
            selected_index=1,
            confidence=0.97,
            reason="로그인 엔드포인트 /signin과 일치",
        )
    )
    result = TargetSelector(llm).select(
        "로그인 요청 처리 흐름",
        [_hit("registerUser", 0.3543, "/signup"), _hit("authenticateUser", 0.3501, "/signin")],
    )

    assert result.method_name == "authenticateUser"
    assert result.selection_source is SelectionSource.LLM
    assert result.confidence == 0.97


def test_llm_failure_falls_back_to_vector_top_one() -> None:
    llm = FakeSelector(error=RuntimeError("provider unavailable"))
    result = TargetSelector(llm).select(
        "로그인", [_hit("registerUser", 0.3543), _hit("authenticateUser", 0.3501)]
    )

    assert result.method_name == "registerUser"
    assert result.selection_source is SelectionSource.FALLBACK
