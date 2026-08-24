"""app/parsers/languages/python.py 단위 테스트."""

from app.parsers.languages.python import parse_python_file

SERVICE_SRC = b'''
from app.repositories.poll_repository import PollRepository
import json


class PollService(BaseService, LoggingMixin, metaclass=ABCMeta):
    max_items: int = 10

    def __init__(self, repository):
        self.repository = repository
        self.cache = PollRepository()

    def save(self, poll):
        self.repository.save(poll)
        return persist_helper(poll)

    @staticmethod
    def helper():
        return None


@app.route("/polls", methods=["GET"])
def list_polls():
    return fetch_all()


def fetch_all():
    return list_polls()
'''


def test_parses_class_with_bases_and_layer():
    result = parse_python_file("services/poll_service.py", SERVICE_SRC)
    assert result.path == "services/poll_service.py"
    assert result.package is None
    assert "app.repositories.poll_repository" in result.imports
    assert "json" in result.imports

    poll_service = next(c for c in result.classes if c.name == "PollService")
    assert poll_service.kind == "class"
    # metaclass=ABCMeta는 키워드 인자라 상속 관계에서 제외되고, 나머지 위치
    # 인자 중 첫 번째가 extends, 그 다음이 implements로 감.
    assert poll_service.extends == "BaseService"
    assert poll_service.implements == ("LoggingMixin",)
    assert poll_service.layer == "Service"  # "services/" 경로 키워드로 분류됨


def test_init_is_marked_as_constructor_and_decorator_is_unwrapped():
    result = parse_python_file("services/poll_service.py", SERVICE_SRC)
    poll_service = next(c for c in result.classes if c.name == "PollService")
    methods_by_name = {m.name: m for m in poll_service.methods}

    assert methods_by_name["__init__"].is_constructor is True
    assert methods_by_name["save"].is_constructor is False
    # @staticmethod로 데코레이트된 메서드도 정상적으로 언랩되어 메서드 목록에 잡혀야 함
    assert "helper" in methods_by_name


def test_field_extraction_from_annotation_and_constructor_call_heuristic():
    result = parse_python_file("services/poll_service.py", SERVICE_SRC)
    poll_service = next(c for c in result.classes if c.name == "PollService")
    fields_by_name = {f.name: f.type for f in poll_service.fields}

    assert fields_by_name["max_items"] == "int"  # 타입 힌트 달린 클래스 속성
    # self.cache = PollRepository() -> 생성자 호출 패턴으로 타입 best-effort 추론
    assert fields_by_name["cache"] == "PollRepository"
    # self.repository = repository는 단순 파라미터 전달이라 타입을 알 수 없어서 필드로 안 잡혀야 함
    assert "repository" not in fields_by_name


def test_receiver_extraction_distinguishes_field_vs_same_class_call():
    result = parse_python_file("services/poll_service.py", SERVICE_SRC)
    poll_service = next(c for c in result.classes if c.name == "PollService")
    save_method = next(m for m in poll_service.methods if m.name == "save")

    calls_by_receiver = {call.receiver: call.name for call in save_method.invoked_calls}
    assert calls_by_receiver.get("repository") == "save"  # self.repository.save(...)
    assert calls_by_receiver.get(None) == "persist_helper"  # bare 모듈 함수 호출


def test_decorated_top_level_function_wrapped_in_synthetic_module_class():
    result = parse_python_file("services/poll_service.py", SERVICE_SRC)
    module_class = next(c for c in result.classes if c.name == "poll_service$module")
    method_names = {m.name for m in module_class.methods}
    # @app.route(...) 데코레이터가 붙은 최상위 함수도 정상적으로 언랩되어 잡혀야 함
    assert method_names == {"list_polls", "fetch_all"}

    list_polls = next(m for m in module_class.methods if m.name == "list_polls")
    assert any(
        call.receiver is None and call.name == "fetch_all" for call in list_polls.invoked_calls
    )


def test_file_with_no_classes_or_functions_returns_empty_result():
    result = parse_python_file("__init__.py", b"# just a comment\n")
    assert result.classes == ()
    assert result.imports == ()
