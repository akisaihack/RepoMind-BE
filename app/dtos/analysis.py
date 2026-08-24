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
class JavaScriptMethodResult:
    """JS/JSX의 메서드·함수 하나를 파싱한 결과 (class 메서드, top-level 함수,
    화살표 함수로 대입된 const 전부 이 형태로 통일해서 담음).

    필드 모양은 app/dtos/protocols.py의 MethodResultProtocol을 그대로 따름 —
    JavaMethodResult와 구조적으로 동일함(중복이지만, 이름으로 어느 언어
    결과인지 명확히 구분하기 위해 의도적으로 분리함).
    """

    name: str | None
    param_signature: str
    is_constructor: bool
    start_line: int
    end_line: int
    text: str
    api_mapping: APIMapping | None
    invoked_calls: tuple[MethodCall, ...]


@dataclass(frozen=True, slots=True)
class JavaScriptClassResult:
    """JS의 class 하나, 또는 파일당 합성 "module" 클래스(orphan 최상위 함수들을
    담는 컨테이너 — app/parsers/languages/javascript.py 참고) 하나.

    kind는 항상 "class"임(JS에는 interface 키워드가 없음). extends_generic_params/
    implements는 JS에 해당 개념이 없어서 항상 빈 튜플.
    """

    name: str | None
    kind: str  # 항상 "class"
    layer: str
    extends: str | None
    extends_generic_params: tuple[str, ...]
    implements: tuple[str, ...]
    fields: tuple[FieldResult, ...]
    methods: tuple[JavaScriptMethodResult, ...]
    qualified_name: str | None = None


@dataclass(frozen=True, slots=True)
class JavaScriptFileResult:
    """JS/JSX 소스 파일 하나를 파싱한 최종 결과.

    package는 항상 None(JS 모듈은 파일 경로 기반이라 Java식 패키지 개념이
    없음). imports는 import된 모듈 경로 문자열(예: "react", "../services")
    목록 — 대부분 외부 패키지/상대경로라 그래프 해석 단계(resolve_cross_file_
    references)에서 external=True로 남는 게 정상.
    """

    path: str
    package: str | None
    imports: tuple[str, ...]
    classes: tuple[JavaScriptClassResult, ...]


@dataclass(frozen=True, slots=True)
class TypeScriptMethodResult:
    """TypeScript/TSX의 메서드·함수 하나를 파싱한 결과 (class 메서드, 모듈
    최상위 함수, 화살표 함수로 대입된 const 전부 이 형태로 통일해서 담음).

    필드 모양은 JavaScriptMethodResult와 동일 — 이름으로 언어를 구분하기
    위해 의도적으로 분리함.
    """

    name: str | None
    param_signature: str
    is_constructor: bool
    start_line: int
    end_line: int
    text: str
    api_mapping: APIMapping | None
    invoked_calls: tuple[MethodCall, ...]


@dataclass(frozen=True, slots=True)
class TypeScriptClassResult:
    """TS의 class/interface 하나, 또는 파일당 합성 "module" 클래스(orphan
    최상위 함수들을 담는 컨테이너) 하나.

    kind는 "class" 또는 "interface" (TS엔 실제 interface 문법이 있어서 Java와
    동일하게 구분함 — JS/Python과 다른 점). extends_generic_params는 TS의
    제네릭 상속(`extends BaseRepository<User>`)에서 타입 인자를 보존함(Java의
    JpaRepository<Entity> 패턴과 동일하게 MANAGES 엣지 추론에 씀). implements는
    `implements`절의 타입들(제네릭 인자는 벗겨내고 베이스 이름만).
    """

    name: str | None
    kind: str  # "class" | "interface"
    layer: str
    extends: str | None
    extends_generic_params: tuple[str, ...]
    implements: tuple[str, ...]
    fields: tuple[FieldResult, ...]
    methods: tuple[TypeScriptMethodResult, ...]
    qualified_name: str | None = None


@dataclass(frozen=True, slots=True)
class TypeScriptFileResult:
    """TypeScript/TSX 소스 파일 하나를 파싱한 최종 결과.

    package는 항상 None(JS와 동일한 이유). imports는 import된 모듈 경로
    문자열 목록.
    """

    path: str
    package: str | None
    imports: tuple[str, ...]
    classes: tuple[TypeScriptClassResult, ...]


@dataclass(frozen=True, slots=True)
class PythonMethodResult:
    """Python의 메서드·함수 하나를 파싱한 결과 (class 메서드, 모듈 최상위
    함수 전부 이 형태로 통일해서 담음. `__init__`은 is_constructor=True).

    필드 모양은 JavaScriptMethodResult와 동일(구조적으로 MethodResultProtocol을
    따름) — 이름으로 언어를 구분하기 위해 의도적으로 분리함.
    """

    name: str | None
    param_signature: str
    is_constructor: bool
    start_line: int
    end_line: int
    text: str
    api_mapping: APIMapping | None
    invoked_calls: tuple[MethodCall, ...]


@dataclass(frozen=True, slots=True)
class PythonClassResult:
    """Python의 class 하나, 또는 파일당 합성 "module" 클래스(orphan 최상위
    함수들을 담는 컨테이너 — app/parsers/languages/python.py 참고) 하나.

    kind는 항상 "class"임(Python엔 별도 interface 문법이 없음 — ABC는 관례).
    extends_generic_params는 Python 제네릭 타입 파라미터를 이번 범위에서
    추출하지 않아서 항상 빈 튜플. implements는 Java의 "인터페이스 구현"과
    정확히 대응하진 않지만, 다중 상속에서 첫 번째 베이스(extends) 이후의
    나머지 베이스 클래스들을 담는 용도로 재사용함.
    """

    name: str | None
    kind: str  # 항상 "class"
    layer: str
    extends: str | None
    extends_generic_params: tuple[str, ...]
    implements: tuple[str, ...]
    fields: tuple[FieldResult, ...]
    methods: tuple[PythonMethodResult, ...]
    qualified_name: str | None = None


@dataclass(frozen=True, slots=True)
class PythonFileResult:
    """Python 소스 파일 하나를 파싱한 최종 결과.

    package는 항상 None(Python 패키지는 디렉터리 구조 + __init__.py 기반이라
    파일 하나만 봐서는 알 수 없음). imports는 `import`/`from ... import`의
    모듈 경로 문자열 목록 — 대부분 표준 라이브러리/외부 패키지라 그래프
    해석 단계에서 external=True로 남는 게 정상.
    """

    path: str
    package: str | None
    imports: tuple[str, ...]
    classes: tuple[PythonClassResult, ...]


@dataclass(frozen=True, slots=True)
class AnalysisRequest:
    repository_id: UUID
    repository_url: str
    branch: str


@dataclass(frozen=True, slots=True)
class AnalysisFailureInfo:
    error_code: str
    message: str
