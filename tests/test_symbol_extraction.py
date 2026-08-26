from app.ai.symbol_extraction import extract_symbol_candidates


def test_extracts_symbol_candidates_from_natural_language_question() -> None:
    assert extract_symbol_candidates("requestExport 함수에서 spinKey를 제거한 이유는?") == [
        "requestExport",
        "spinKey",
    ]


def test_extracts_simple_method_name_from_context() -> None:
    assert extract_symbol_candidates("login 메서드 변경 이력 알려줘") == ["login"]


def test_extracts_qualified_and_snake_case_names() -> None:
    assert extract_symbol_candidates(
        "LoginService.authenticate와 reset_assignment_table_cache 관계"
    ) == ["authenticate", "LoginService", "reset_assignment_table_cache"]
