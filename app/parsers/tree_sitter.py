"""Tree-sitter 파싱 범용(언어 무관) 유틸리티.

언어별 추출 로직(자바 등)은 app/parsers/languages/ 에 있음.
이 모듈은 "주어진 언어로 파서를 만들고, 소스를 트리로 파싱하고,
어떤 언어 모듈이든 재사용할 수 있는 작은 도구들(텍스트 추출, 트리 순회,
노드 검색)"만 담당함.

디스크에서 파일을 읽는 건 의도적으로 여기서 하지 않음 — 파싱 로직을
단위 테스트하기 쉽게 유지하기 위해서고, 호출하는 쪽에서 이미 읽은
source bytes를 넘겨주는 방식으로 씀.
"""

from collections.abc import Callable, Iterable
from dataclasses import dataclass

from tree_sitter import Language, Node, Parser, Tree

VisitFn = Callable[..., bool | None]

_parser_cache: dict[int, Parser] = {}


@dataclass(frozen=True, slots=True)
class ParsedFile:
    """소스 파일 하나와 그걸 파싱한 결과 트리를 묶어놓은 컨테이너."""

    path: str
    source: bytes
    tree: Tree


def build_parser(language: Language) -> Parser:
    """주어진 언어(Language)로 Tree-sitter 파서를 만들고 캐싱함.

    Parser를 만드는 자체는 가벼운 작업이지만, 파일마다 매번 새로 만들
    필요는 없어서 같은 Language 객체에 대해서는 같은 Parser 인스턴스를
    재사용함. tree_sitter.Language가 hashable이라는 보장이 없어서
    functools.lru_cache 대신 id() 기반 수동 캐시를 씀.
    """
    cache_key = id(language)
    if cache_key not in _parser_cache:
        _parser_cache[cache_key] = Parser(language)
    return _parser_cache[cache_key]


def parse_source(parser: Parser, source_bytes: bytes) -> Tree:
    """소스 코드 바이트를 받아서 구문 트리(Tree)로 파싱함."""
    return parser.parse(source_bytes)


def parse_file(parser: Parser, path: str, source_bytes: bytes) -> ParsedFile:
    """파일의 바이트를 파싱하고, 파일 경로와 함께 하나로 묶어서 반환함."""
    tree = parse_source(parser, source_bytes)
    return ParsedFile(path=path, source=source_bytes, tree=tree)


def get_node_text(node: Node, source_bytes: bytes) -> str:
    """노드가 원본 소스에서 차지하는 정확한 텍스트를 잘라서 반환함.

    노드는 자기가 파싱된 소스에 대한 위치 정보(start_byte/end_byte)만
    갖고 있고 텍스트 자체는 들고 있지 않음. 그래서 어떤 노드든 실제
    소스 텍스트가 필요할 땐 이 함수로 복원함.
    """
    return source_bytes[node.start_byte:node.end_byte].decode("utf-8")


def get_child_by_field(node: Node, field_name: str) -> Node | None:
    """노드에서 이름표(field name)가 붙은 자식 노드를 반환함, 없으면 None.

    Node.child_by_field_name()을 감싼 얇은 래퍼로, 호출하는 쪽에서
    Tree-sitter의 암묵적 타입에 의존하지 않고 명확한 타입힌트를 쓸 수
    있게 해줌.
    """
    return node.child_by_field_name(field_name)


def walk(node: Node, visit_fn: VisitFn, **context: object) -> None:
    """트리(서브트리)의 모든 노드를 깊이 우선으로 재귀 순회함.

    각 노드마다 visit_fn(node, **context)를 한 번씩 호출함. 이 함수가
    참(truthy) 값을 반환하면 그 노드의 자식들은 더 이상 안 들어감 —
    예를 들어 중첩 클래스의 본문 안으로는 들어가지 않게 해서, 그 안의
    멤버들이 바깥 클래스의 멤버로 잘못 섞이는 걸 막을 때 씀.
    """
    stop_descent = visit_fn(node, **context)
    if stop_descent:
        return
    for child in node.children:
        walk(child, visit_fn, **context)


def find_nodes_by_type(root_node: Node, node_type: str | Iterable[str]) -> list[Node]:
    """root_node 아래에서 타입이 일치하는 노드를 전부 모아서 반환함.

    node_type은 단일 타입 이름("method_declaration") 하나만 받을 수도
    있고, 여러 종류를 한 번에 찾고 싶은 경우를 위해 타입 이름 목록도
    받을 수 있음.
    """
    types = {node_type} if isinstance(node_type, str) else set(node_type)
    found: list[Node] = []

    def _collect(node: Node) -> None:
        if node.type in types:
            found.append(node)
        return None

    walk(root_node, _collect)
    return found
