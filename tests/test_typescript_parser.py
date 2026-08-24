"""app/parsers/languages/typescript.py 단위 테스트.

인라인 소스 문자열을 fixture로 써서 parse_typescript_file()의 DTO 출력을
검증함(Neo4j/pgvector 등 실제 DB 연결은 필요 없음 — 순수 파싱 로직만 테스트).
"""

from app.parsers.languages.typescript import parse_typescript_file

TSX_SRC = b"""
import React from "react";
import { PollService } from "../services/pollService";

interface PollProps {
    id: number;
    onVote: (id: number) => void;
}

export class PollCard extends React.Component<PollProps> implements Comparable<PollCard> {
    private pollService: PollService = new PollService();
    count: number;

    constructor(props: PollProps) {
        super(props);
    }

    handleVote(id: number): void {
        this.props.onVote(id);
        this.pollService.castVote(id);
    }
}

class UserRepository extends BaseRepository<User, number> {
}

export function fetchPolls() {
    return usePolls();
}

export const usePolls = () => {
    return fetchPolls();
};
"""


def test_parses_class_with_extends_implements_and_generics():
    result = parse_typescript_file("src/poll/PollCard.tsx", TSX_SRC)
    assert result.path == "src/poll/PollCard.tsx"
    assert result.package is None
    assert "react" in result.imports
    assert "../services/pollService" in result.imports

    poll_card = next(c for c in result.classes if c.name == "PollCard")
    assert poll_card.kind == "class"
    assert poll_card.extends == "React.Component"
    assert poll_card.extends_generic_params == ("PollProps",)
    assert poll_card.implements == ("Comparable",)
    assert poll_card.layer == "Component"


def test_generic_extends_captures_all_type_arguments():
    # UserRepository extends BaseRepository<User, number> — 상속 대상 자체의
    # 제네릭 타입 인자가 2개 이상이어도 전부 보존돼야 함(단일 인자만 확인하고
    # 넘어가는 회귀를 막기 위한 케이스).
    result = parse_typescript_file("src/repo/UserRepository.ts", TSX_SRC)
    user_repo = next(c for c in result.classes if c.name == "UserRepository")
    assert user_repo.extends == "BaseRepository"
    assert user_repo.extends_generic_params == ("User", "number")


def test_interface_is_extracted_with_interface_kind_and_no_methods():
    result = parse_typescript_file("src/poll/PollCard.tsx", TSX_SRC)
    poll_props = next(c for c in result.classes if c.name == "PollProps")
    assert poll_props.kind == "interface"
    assert poll_props.methods == ()


def test_field_definitions_use_real_type_annotations():
    result = parse_typescript_file("src/poll/PollCard.tsx", TSX_SRC)
    poll_card = next(c for c in result.classes if c.name == "PollCard")
    fields_by_name = {f.name: f.type for f in poll_card.fields}
    assert fields_by_name.get("pollService") == "PollService"
    assert fields_by_name.get("count") == "number"


def test_constructor_is_marked_and_receiver_extraction_distinguishes_props_vs_field():
    result = parse_typescript_file("src/poll/PollCard.tsx", TSX_SRC)
    poll_card = next(c for c in result.classes if c.name == "PollCard")

    constructor = next(m for m in poll_card.methods if m.name == "constructor")
    assert constructor.is_constructor is True

    handle_vote = next(m for m in poll_card.methods if m.name == "handleVote")
    calls_by_receiver = {call.receiver: call.name for call in handle_vote.invoked_calls}
    assert calls_by_receiver.get("props") == "onVote"
    assert calls_by_receiver.get("pollService") == "castVote"


def test_orphan_top_level_functions_wrapped_in_synthetic_module_class():
    result = parse_typescript_file("src/poll/PollCard.tsx", TSX_SRC)
    module_class = next(c for c in result.classes if c.name == "PollCard$module")
    assert module_class.kind == "class"
    method_names = {m.name for m in module_class.methods}
    # function 선언 스타일(fetchPolls)과 화살표 함수 const 스타일(usePolls) 둘 다 잡혀야 함
    assert method_names == {"fetchPolls", "usePolls"}

    use_polls = next(m for m in module_class.methods if m.name == "usePolls")
    assert any(
        call.receiver is None and call.name == "fetchPolls" for call in use_polls.invoked_calls
    )


def test_ts_extension_uses_typescript_grammar_not_tsx():
    # .ts 파일은 JSX 문법이 없는 순수 TS grammar로 파싱돼야 함 — 확장자로
    # 올바른 grammar가 선택되는지 확인 (틀린 grammar를 쓰면 여기서 예외가 남).
    src = b"""
    export class Plain {
        value: number = 1;
    }
    """
    result = parse_typescript_file("src/plain.ts", src)
    plain = next(c for c in result.classes if c.name == "Plain")
    assert plain.fields[0].type == "number"


def test_file_with_no_classes_interfaces_or_functions_returns_empty_result():
    result = parse_typescript_file("empty.ts", b"// just a comment\n")
    assert result.classes == ()
    assert result.imports == ()
