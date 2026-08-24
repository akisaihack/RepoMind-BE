"""app/parsers/languages/javascript.py 단위 테스트.

인라인 소스 문자열을 fixture로 써서 parse_javascript_file()의 DTO 출력을
검증함(Neo4j/pgvector 등 실제 DB 연결은 필요 없음 — 순수 파싱 로직만 테스트).
"""

from app.parsers.languages.javascript import parse_javascript_file

REACT_CLASS_COMPONENT_SRC = b"""
import React from "react";
import pollService from "../services/pollService";

export class PollCard extends React.Component {
    constructor(props) {
        super(props);
        this.pollService = pollService;
    }

    handleVote(id) {
        this.props.onVote(id);
        this.pollService.castVote(id);
    }
}

export function fetchPolls() {
    return usePolls();
}

export function usePolls() {
    return fetchPolls();
}
"""


def test_parses_class_with_extends_and_layer():
    result = parse_javascript_file("PollCard.jsx", REACT_CLASS_COMPONENT_SRC)
    assert result.path == "PollCard.jsx"
    assert result.package is None
    assert "react" in result.imports
    assert "../services/pollService" in result.imports
    assert len(result.classes) == 2  # PollCard 클래스 + 합성 module 클래스

    poll_card = next(c for c in result.classes if c.name == "PollCard")
    assert poll_card.kind == "class"
    assert poll_card.extends == "React.Component"
    assert poll_card.layer == "Component"
    assert poll_card.extends_generic_params == ()
    assert poll_card.implements == ()


def test_receiver_extraction_distinguishes_props_vs_field_call():
    result = parse_javascript_file("PollCard.jsx", REACT_CLASS_COMPONENT_SRC)
    poll_card = next(c for c in result.classes if c.name == "PollCard")
    handle_vote = next(m for m in poll_card.methods if m.name == "handleVote")

    calls_by_receiver = {call.receiver: call.name for call in handle_vote.invoked_calls}
    assert calls_by_receiver.get("props") == "onVote"
    assert calls_by_receiver.get("pollService") == "castVote"


def test_orphan_top_level_functions_wrapped_in_synthetic_module_class():
    result = parse_javascript_file("PollCard.jsx", REACT_CLASS_COMPONENT_SRC)
    module_class = next(c for c in result.classes if c.name == "PollCard$module")
    assert module_class.kind == "class"
    assert module_class.layer == "Module"
    method_names = {m.name for m in module_class.methods}
    assert method_names == {"fetchPolls", "usePolls"}

    # usePolls가 같은 모듈 안의 fetchPolls를 호출 -> receiver=None으로 남아야 함
    use_polls = next(m for m in module_class.methods if m.name == "usePolls")
    assert any(
        call.receiver is None and call.name == "fetchPolls" for call in use_polls.invoked_calls
    )


def test_file_with_no_classes_or_functions_returns_empty_result():
    result = parse_javascript_file("empty.js", b"// just a comment\n")
    assert result.classes == ()
    assert result.imports == ()


def test_arrow_function_assigned_to_const_is_treated_as_top_level_function():
    src = b"""
    export const formatDate = (date) => {
        return date.toISOString();
    };
    """
    result = parse_javascript_file("utils/formatDate.js", src)
    module_class = next(c for c in result.classes if c.name == "formatDate$module")
    method_names = {m.name for m in module_class.methods}
    assert "formatDate" in method_names
    assert module_class.layer == "Util"  # utils/ 경로 키워드로 분류됨
