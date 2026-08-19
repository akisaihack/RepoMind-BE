"""소스 코드 정적 분석(파싱) 결과를 담는 DTO들.

app/parsers/languages/ 아래의 언어별 파서들이 이 DTO 형태로 결과를 반환함.
파일 하나를 파싱한 결과만 표현하며, 여러 파일에 걸친 관계(호출 관계 해석,
import 해석 등)는 다루지 않음 — 그건 app/graph/mappings.py의 책임.
"""

from dataclasses import dataclass
from uuid import UUID


@dataclass(frozen=True, slots=True)
class APIMapping:
    """`@GetMapping` 등에서 추출한 HTTP 메서드 + 경로."""

    http_method: str
    path: str


@dataclass(frozen=True, slots=True)
class ExtendsImplementsResult:
    """클래스/인터페이스 선언부에서 뽑아낸 상속·구현 관계.

    extends_generic_params는 `JpaRepository<Poll, Long>`처럼 상속 대상이
    제네릭을 쓸 때, 그 타입 파라미터(Poll, Long)를 버리지 않고 보존하기
    위한 필드. Repository가 어떤 Entity를 다루는지(MANAGES 관계) 추론할 때 씀.
    """

    extends_name: str | None
    extends_generic_params: tuple[str, ...]
    implements_names: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class MethodCall:
    """메서드 본문 안에서 발견된 호출 하나 (리시버 + 호출된 메서드 이름).

    `pollRepository.findById(id)`면 receiver="pollRepository", name="findById".
    리시버 없이 그냥 `foo()`처럼 부르면 receiver=None (같은 클래스 메서드
    호출이거나 static import라는 뜻). 타입 추론은 하지 않고 텍스트 상의
    식별자만 뽑은 값이라, 체이닝(`list.stream().filter(...)`)처럼 리시버가
    단순 식별자가 아닌 경우엔 receiver=None으로 남음.
    """

    receiver: str | None
    name: str


@dataclass(frozen=True, slots=True)
class FieldResult:
    """클래스 필드 하나 (이름 + 타입).

    메서드 호출의 리시버 이름(`pollRepository`)을 필드 타입(`PollRepository`)과
    매칭해서 CALLS 관계를 좁히는 데 씀 (app/graph/mappings.py).
    """

    name: str
    type: str


@dataclass(frozen=True, slots=True)
class JavaMethodResult:
    """메서드 또는 생성자 하나를 파싱한 결과."""

    name: str | None
    param_signature: str
    is_constructor: bool
    start_line: int
    end_line: int
    text: str
    api_mapping: APIMapping | None
    invoked_calls: tuple[MethodCall, ...]


@dataclass(frozen=True, slots=True)
class JavaClassResult:
    """클래스 또는 인터페이스 하나를 파싱한 결과."""

    name: str | None
    kind: str  # "class" 또는 "interface"
    layer: str
    extends: str | None
    extends_generic_params: tuple[str, ...]
    implements: tuple[str, ...]
    fields: tuple[FieldResult, ...]
    methods: tuple[JavaMethodResult, ...]
    qualified_name: str | None = None


@dataclass(frozen=True, slots=True)
class JavaFileResult:
    """자바 소스 파일 하나를 파싱한 최종 결과."""

    path: str
    package: str | None
    imports: tuple[str, ...]
    classes: tuple[JavaClassResult, ...]


@dataclass(frozen=True, slots=True)
class AnalysisRequest:
    repository_id: UUID
    repository_url: str
    branch: str


@dataclass(frozen=True, slots=True)
class AnalysisFailureInfo:
    error_code: str
    message: str
