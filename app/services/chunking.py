"""파싱 결과(JavaFileResult)를 pgvector에 저장할 코드 청크(CodeChunk)로
변환하는 로직.

DB(pgvector) 접근이나 임베딩 호출은 전혀 하지 않음 — 그건 app/services/
embedding.py와 실제 저장소(repository) 쪽 책임. 여기서는 "어떤 텍스트를,
어떤 메타데이터와 함께 청크로 만들지"만 담당함.

app/graph/mappings.py와 대응 관계: mappings.py는 같은 파싱 결과를 그래프
노드/엣지로 바꾸고, 이 모듈은 벡터 검색용 청크로 바꿈. 서로 독립적으로
동작하고(하나가 없어도 다른 하나는 문제없이 돌아감), 최종적으로 그래프
쪽 노드 id와 청크 id를 나중에 서로 연결(cross-reference)해서 Graph-RAG의
"벡터로 시작점 찾고 그래프로 깊이 탐색" 구조를 완성함.
"""

from app.dtos.analysis import JavaFileResult, JavaMethodResult
from app.dtos.chunk import CodeChunk
from app.graph.identifiers import normalize_repository_path
from app.graph.mappings import class_node_id, method_node_id


def _chunk_id(file_path: str, class_index: int, method_index: int) -> str:
    """파일 안에서 몇 번째 클래스/메서드인지로 결정적 id를 만듦.

    app/graph/mappings.py의 노드 id 규칙과 동일한 방식 — 이름이 겹쳐도
    항상 유일하고, 나중에 그래프 쪽 Method 노드 id(`Method::{class_id}::
    {method_index}`)와 같은 인덱스를 공유하므로 청크<->그래프 노드를
    맞춰보기 쉬움.
    """
    return f"Chunk::{file_path}::{class_index}::{method_index}"


def _graph_node_id(
    github_repository_id: int,
    normalized_path: str,
    class_index: int,
    class_kind: str,
    method_index: int,
) -> str:
    """app/graph/mappings.py가 Method 노드에 부여하는 id를 그대로 재계산.

    class_index/method_index가 항상 같은 순서(enumerate)로 나오기 때문에,
    이 값은 실제 Neo4j Method 노드 id와 100% 동일함 — 별도로 조회할 필요
    없이 계산만으로 그래프 노드를 가리킬 수 있음.
    """
    class_id = class_node_id(github_repository_id, normalized_path, class_index, class_kind)
    return method_node_id(class_id, method_index)


def _build_chunk_text(
    package: str | None,
    class_name: str | None,
    layer: str,
    method_result: JavaMethodResult,
) -> str:
    """실제로 임베딩할 텍스트를 만듦.

    메서드 소스코드만 넣으면 "이게 어디 소속인지" 문맥이 없어서, 앞에
    패키지/클래스/레이어/시그니처를 주석 형태로 붙임. 이렇게 하면 임베딩
    벡터 자체가 소속 문맥을 반영하게 돼서 검색 품질이 좋아짐.
    """
    method_label = method_result.name or "<unknown>"
    header_lines = []
    if package:
        header_lines.append(f"// package: {package}")
    header_lines.append(f"// class: {class_name or '<unknown>'} ({layer})")
    header_lines.append(f"// method: {method_label}{method_result.param_signature}")
    return "\n".join(header_lines) + "\n" + method_result.text


def build_chunks_from_file(
    github_repository_id: int,
    file_result: JavaFileResult,
    commit_hash: str,
) -> list[CodeChunk]:
    """자바 파일 파싱 결과 하나에서 메서드/생성자 단위 청크를 전부 뽑음.

    github_repository_id/commit_hash는 실제 GitHub 저장소 id와 실제 커밋
    SHA여야 함 — 이 청크가 그래프 쪽 Repository/Commit 노드와 정확히 같은
    key로 연결되기 때문에 더미값을 넣으면 연결이 끊어짐.
    """
    chunks: list[CodeChunk] = []
    normalized_path = normalize_repository_path(file_result.path)

    for class_index, class_result in enumerate(file_result.classes):
        for method_index, method_result in enumerate(class_result.methods):
            chunks.append(
                CodeChunk(
                    id=_chunk_id(normalized_path, class_index, method_index),
                    graph_node_id=_graph_node_id(
                        github_repository_id,
                        normalized_path,
                        class_index,
                        class_result.kind,
                        method_index,
                    ),
                    text=_build_chunk_text(
                        file_result.package, class_result.name, class_result.layer, method_result
                    ),
                    path=normalized_path,
                    github_repository_id=github_repository_id,
                    commit_hash=commit_hash,
                    package=file_result.package,
                    class_name=class_result.name,
                    class_kind=class_result.kind,
                    layer=class_result.layer,
                    method_name=method_result.name,
                    param_signature=method_result.param_signature,
                    is_constructor=method_result.is_constructor,
                    start_line=method_result.start_line,
                    end_line=method_result.end_line,
                    api_mapping=method_result.api_mapping,
                )
            )

    return chunks
