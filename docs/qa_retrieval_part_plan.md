# 담당 파트 실행 계획 — 질문 분류 → 검색 전략 결정 → DB 조회 → LLM 근거 전달

> `docs/langgraph_pipeline.md`(전체 설계)와 `docs/langgraph_pipeline_checklist.md`(전체
> 체크리스트)를 이미 읽었다는 전제로, 그중 **"내 파트"만 떼어서** 실행 순서로
> 정리한 문서. 전체 설계를 다시 읽을 필요 없이 이 문서 + 코드 docstring만 보고
> 이어서 작업할 수 있게 하는 게 목적.

---

## 0. 범위 정의 (먼저 확인할 것)

"질문을 분류하고 답변의 형태를 결정해서 DB에서 정보를 검색해 LLM에 넘겨주는
파트"는 LangGraph 7개 노드 중 아래 **5~6개**에 해당한다고 해석함:

| 노드 | 파일 | 내 파트? |
|---|---|---|
| ① 질문 유형 분류 | `nodes/question_analyzer.py` | ✅ |
| ② 코드 심볼 매칭 | `nodes/entity_resolver.py` | ✅ (단, 우선순위 낮음 — 3번 참고) |
| ③ 벡터 검색 (pgvector) | `nodes/vector_retriever.py` | ✅ |
| ③ 그래프 탐색 (Neo4j) | `nodes/graph_retriever.py` | ✅ |
| ④ 근거 통합 | `nodes/evidence_fusion.py` | ✅ |
| ⑤ 근거 충분성 검증 | `nodes/evidence_validator.py` | ✅ (재검색 루프까지가 "검색해서 넘겨주는" 범위에 포함된다고 봄) |
| ⑥ 답변 생성(LLM 호출로 최종 답변 조립) | `nodes/response_composer.py` | ❌ — "LLM 쪽으로 넘겨주는" 다음 단계, 팀원 파트로 가정 |

**내 파트의 최종 산출물** = `state["evidence"]`(근거 리스트) +
`state["question_kind"]`(질문 유형) + `state["is_sufficient"]`/`retry_count` —
이 세 가지가 `response_composer`에게 그대로 넘어가서 팀원이 LLM 호출로 최종
답변(`ChatResponseData`)을 조립하는 구조. **이 경계가 다르면**(예:
response_composer도 내 파트에 포함) 아래 순서는 그대로 두고 8번 항목만
추가하면 됨 — 구조 자체는 안 바뀜.

---

## 0-1. 진행 현황 (2026-08-19 기준)

**완료**: Step 1~6 전부 실제 코드로 구현하고, 각 단계 mock 데이터 기반 검증까지
통과함(아래 "완료" 표시된 단계 참고). **남은 것은 Step 7(`question_analyzer.py`)뿐.**

**추가로 한 일 (원래 이 계획엔 없었음)**: `intent` 질문 유형이 쓸 `CHANGED_BY`
관계(Method↔Commit)를 만드는 배치 작업을 별도로 구현함. 새 섹션 "7. CHANGED_BY
배치 작업(추가 구현)" 참고. **아직 실행 안 함** — 그래프 담당자 승인 필요.
(→ 2026-08-22 업데이트로 이 판단 자체가 바뀜, 0-2 참고)

**계획 대비 정정된 부분**:
- "Method와 Commit이 완전히 분리돼 있다"는 원래 가정은 틀림. 코드 그래프와
  GitHub 이력 그래프가 `file_key()`로 File 노드를 공유해서, 이미
  `(Commit)-[:CHANGED]->(File)-[:DECLARES]->(Class)-[:CONTAINS]->(Method)`
  경로가 존재함(파일 단위라 정밀도는 낮음). `CHANGED_BY`는 "없던 연결을
  새로 만드는 것"이 아니라 "파일 단위 경로를 건너뛰는 메서드 단위 지름길"임.
- Step 1의 `search_similar()`는 아래 코드 스니펫(계획 당시 초안)과 달리,
  처음부터 `(CodeChunk, distance)` 튜플을 반환하도록 구현함(`similarity`
  placeholder 0.0을 쓰지 않음) — Step 2/6에서 실제 유사도 값을 바로 씀.
- **미해결로 남은 확인 사항**: Postgres에 Method↔Commit 연관 테이블을 별도로
  두기로 팀에서 논의된 게 있었는지 미확인(기억은 나는데 문서/코드 어디에도
  없음) — 확인되면 `link_changed_by` 설계를 Neo4j 엣지 단독에서 "Postgres
  테이블 + Neo4j 엣지" 조합으로 바꿔야 할 수 있음. (→ 0-2에서 우선순위 낮아짐)

**다음에 실제 인프라로 검증해야 할 것 (지금은 mock으로만 확인함)**:
- pgvector 열리면: `search_similar()` 실 데이터 검색 결과 확인
- Neo4j 접속되면: `traversal.py`의 네 함수가 실제 `neo4j.graph.Path` 객체에도
  문제없이 동작하는지(지금은 duck-typing 가짜 객체로만 검증)
- `scripts/import_github_history.py`가 대상 레포에 대해 실제로 실행됐는지 확인
  (안 됐으면 Commit 노드 자체가 없어서 changed_by_history 무의미)
- `run_qa_pipeline()` 전체를 실제 앱 컨텍스트에서 이어 돌리는 end-to-end 테스트
  (Step 7까지 끝나야 의미 있음)

---

## 0-2. 팀원 작업 반영 후 재분석 (2026-08-22 기준 — rebase로 MethodVersion 스키마 유입)

### 상황

`feature/ai-java-parser-graph-chunking`을 최신 `develop`(정확히는 merge된
`9cdbfb9`) 위로 rebase하는 중 내 커밋(`25913b4 feat: RAG 검색 파트 구현`)이
팀원 커밋과 충돌 → **충돌난 파일은 원격(팀원) 버전으로 덮어써서 해결**함.
이 문서는 그 결과로 내 파트에 어떤 영향이 생겼는지 다시 분석한 내용.

**⚠️ rebase 자체는 아직 안 끝남.** `.git/rebase-merge/`에 다음 pick이 남아있는
상태(`f1e5a69 feat: 바뀐 청크 결과물` — `scripts/chunking_output.json` 하나만
바뀌는 커밋이라 충돌 가능성은 낮음). `git rebase --continue`를 마저 실행해야
완전히 끝남.

### 무엇이 들어왔나

팀원이 두 커밋으로 **Method 버전 관리(MethodVersion) 스키마**를 코드 그래프에
추가함:

- `fb0a24e feat: 메서드 버전 그래프 관리 #38` — Neo4j 스키마 변경
- `446fc26 feat: 코드 청크 버전 연결 및 재사용 #38` — Postgres `code_chunks`
  테이블 + `CodeChunkRepository` 변경

### 핵심 스키마 변경 요약

| 구분 | 이전 | 이후 |
|---|---|---|
| `code_chunks.graph_node_id` | Method 노드 key | **MethodVersion 노드 key** (컨텐츠 해시 기반, 버전마다 다름) |
| `code_chunks` 신규 컬럼 | — | `method_node_id`(안정적인 Method key), `content_hash` |
| Neo4j 노드 라벨 | `Method` | `Method`(불변 정체성) + **`MethodVersion`**(버전별 스냅샷) 분리 |
| Method 노드 속성 | `name, signature, class_name, start_line, end_line, ...` | `start_line`/`end_line`/소스코드가 **MethodVersion으로 이동**(`startLine`/`endLine`/`sourceCode`, camelCase로 네이밍도 바뀜). Method엔 `name, signature, class_name`만 남음 |
| `CALLS` 관계 | `(Method)-[:CALLS]->(Method)` | **`(MethodVersion)-[:CALLS]->(Method)`** (출발점만 버전, 도착점은 항상 Method) |
| 신규 관계 | — | `HAS_VERSION`(Method→MethodVersion), `INTRODUCED_IN`(MethodVersion→Commit), `DELETED_IN`(Method→Commit) |
| Commit 노드 | — | `MethodVersion-[:INTRODUCED_IN]->Commit`이 GitHub 이력 그래프의 **동일한 Commit 노드**를 가리킴(`repository_scoped_key(repo_id, "commit", sha)` 키 포맷이 두 그래프에서 동일하게 사용됨 — 확인 완료) |

(참고: `app/graph/repositories/code_graph.py`에 `find_method_version_at_commit()`도
같이 추가됨 — 특정 커밋 시점에 유효했던 MethodVersion을 찾는 헬퍼.)

### 내 파트에 생기는 영향 — 정리하면 두 가지

**① 시작 노드 id를 잘못 쓰면 그래프 탐색이 조용히 빈 결과만 반환함 (버그, 우선 수정 필요)**

`vector_retriever.py`가 넘겨주는 `graph_node_id`는 이제 **MethodVersion** 키다.
그런데 `graph_retriever.py`/`traversal.py`는 이 값을 그대로 시작점으로 써서
`MATCH (start {key: $start_node_id})`를 실행한다. 문제는 관계 방향이 대칭이
아니라는 것:

- `calls_forward`(flow): `(MethodVersion)-[:CALLS]->(Method)`이므로 시작점이
  MethodVersion(`graph_node_id`)이어도 **1홉은 맞는다.** 하지만 2홉 이상
  가려면 `Method`에서 다시 `CALLS`를 타야 하는데 `Method`에는 나가는
  `CALLS`가 없음(그건 그 Method의 `MethodVersion`에만 있음) → depth 2 이상은
  구조적으로 항상 끊김.
- `calls_backward`(impact): `CALLS`의 도착점은 항상 **Method**다. 그런데
  지금 코드는 `graph_node_id`(MethodVersion 키)를 시작점으로 넘기므로
  **`(caller)-[:CALLS]->(start)`에 매치되는 게 전혀 없어서 depth와 무관하게
  결과가 항상 빈 배열**이다. 에러는 안 나고 조용히 빈 결과만 나오기 때문에
  지금까지의 mock 테스트로는 못 잡음 — 실 데이터로 처음 확인했다면 "impact
  질문은 왜 항상 근거가 없지?"로 나타났을 버그.
- `shallow_neighborhood`(location): MethodVersion에서 시작해도 동작은 하지만,
  Method가 갖고 있는 `CONTAINS`(소속 Class) 역방향, `EXPOSES`(API 엔드포인트),
  `DELETED_IN` 같은 "위치" 질문에 더 유용한 관계들과 한 홉 멀어짐.
- `changed_by_history`(intent): 애초에 `CHANGED_BY` 관계 자체가 그래프에 없어서
  (아래 ②) 지금은 무관.

**② `CHANGED_BY` 배치 작업이 사실상 불필요해짐 (좋은 소식 — 범위 축소)**

원래 계획: `commit_file_change_hunks`의 줄 범위와 `Method.start_line`/`end_line`을
겹침 비교해서 `CHANGED_BY` 관계를 새로 만드는 배치 작업(섹션 7). 그런데
`MethodVersion-[:INTRODUCED_IN]->Commit`(+ `Method-[:DELETED_IN]->Commit`)이
**이미 정확히 이 정보를 담고 있음** — 컨텐츠 해시가 바뀔 때마다 새
MethodVersion이 생기고, 그 버전을 도입한 커밋이 `INTRODUCED_IN`으로 바로
연결되어 있음. 줄 번호 겹침 휴리스틱보다 오히려 더 정확함(컨텐츠 기준이라
줄 이동에 영향 안 받음).

→ **`intent` 질문 유형은 새 관계 타입을 추가하지 않고, 이미 저장되어 있는
`HAS_VERSION`/`INTRODUCED_IN`/`DELETED_IN`을 읽기만 하는 Cypher로 바로 구현
가능.** 이건 내가 이미 갖고 있는 `traversal.py`/`graph_retriever.py` 파일
안에서 끝나는 변경이라 **그래프 담당자 승인 없이 진행 가능**(새 관계 타입을
공유 Neo4j에 쓰는 게 아니라, 팀원이 이미 만들어 둔 관계를 읽기만 하니까).

### 제안하는 수정 — ✅ 2026-08-22 전부 반영 + mock 검증 완료

1. **`app/ai/rag/state.py`**: `VectorHit`에 `method_node_id: str` 필드 추가.
2. **`app/ai/rag/nodes/vector_retriever.py`**: 반환 dict에
   `"method_node_id": chunk.method_node_id,` 한 줄 추가(이미 `search_similar()`가
   `CodeChunk` ORM 객체를 통째로 주므로 속성은 이미 있음, 꺼내 쓰기만 하면 됨).
3. **`app/ai/rag/nodes/graph_retriever.py`**: 전략별로 시작 id를 다르게 선택:
   - `flow` → `graph_node_id`(벡터로 매칭된 정확한 그 버전에서 출발)
   - `impact`/`intent`/기본(location) → `method_node_id`(안정적인 Method 정체성)
4. **`app/graph/queries/traversal.py`**: 4개 함수 모두 재작성 필요.
   - `calls_forward`/`calls_backward`: `CALLS` 한 종류만 타던 걸
     `[:CALLS|HAS_VERSION*1..{depth*2}]`로 바꿔서 `MethodVersion↔Method`를
     교대로 건너뛰게 함(depth를 2배로 잡는 이유: 논리적 "호출 1홉"이 그래프
     상으로는 `CALLS` + `HAS_VERSION` 2홉이라서). 완벽하진 않음 — 같은
     Method의 다른(형제) 버전이 결과에 섞여 들어올 수 있음. 실 데이터로 결과
     품질 확인 후 필요하면 조정.
   - `changed_by_history`: `CHANGED_BY` 대신 아래 쿼리로 완전히 교체:
     ```cypher
     MATCH (start:Method {key: $start_node_id})
     OPTIONAL MATCH history = (start)-[:HAS_VERSION]->(:MethodVersion)-[:INTRODUCED_IN]->(:Commit)
     OPTIONAL MATCH deletion = (start)-[:DELETED_IN]->(:Commit)
     RETURN history, deletion
     ```
   - `shallow_neighborhood`: 쿼리 자체는 안 바꿔도 됨(이미 라벨 무관하게
     탐색) — 호출하는 쪽(`graph_retriever.py`)에서 넘기는 시작 id만 바뀜.
5. **섹션 7 (`CHANGED_BY` 배치)**: 우선순위를 "필수 대기"에서 "보류"로 낮춤
   (아래 재정리 참고). `scripts/link_changed_by.py`는 그대로 둬도 무해하지만,
   되살릴 일이 생기면 `_methods_in_file()`의
   `method.start_line`/`method.end_line` 조회가 이제 안 맞음(그 속성은
   `MethodVersion.startLine`/`endLine`로 옮겨감) — 고쳐야 동작함.

### 추가로 확인이 필요한 것 (팀 확인 필요, 혼자 결정 안 함)

- `docs/langgraph_pipeline.md` 97~100번째 줄이 아직 "Method 노드의
  `start_line`/`end_line`"이라고 되어 있음 — 실제로는 `MethodVersion`으로
  옮겨갔으니 문서 기준으로 작업하면 헷갈릴 수 있음. 그래프 스키마 소유자에게
  확인 후 문서 업데이트 필요(내 파트 파일이 아니라 직접 고치진 않음).
- `Method`는 snake_case(`start_line`, `class_name`), `MethodVersion`은
  camelCase(`startLine`, `contentHash`)로 속성 네이밍 컨벤션이 다름 — 내
  `traversal.py`는 각자 맞는 이름으로 읽기만 하면 되니 내 코드엔 문제 없지만,
  팀 전체 컨벤션 통일 여부는 그래프 담당자 판단 몫.
- `search_similar()`가 같은 `method_node_id`에 대해 여러 `content_hash`(과거
  버전) row를 반환할 가능성이 있는지 — 재임포트 시 과거 버전 row를 정리하는
  정책이 `chunk_import.py` 쪽에 있는지 확인 필요(있다면 문제 없음, 없다면
  검색 결과에 같은 메서드의 옛날 버전이 중복으로 섞여 나올 수 있음).
- ①에서 설명한 `CALLS|HAS_VERSION` 교대 탐색 방식이 실 데이터에서 형제 버전
  노이즈를 얼마나 만드는지는 실제로 붙여봐야 알 수 있음 — 우선순위 3번
  항목(Step 3 재검증)에서 같이 확인.

### 이번 재분석으로 바뀐 우선순위

1. ~~**rebase 마무리**~~ — ✅ 완료(2026-08-22)
2. ~~**버그 수정**: 위 "제안하는 수정" 1~4번~~ — ✅ 완료 + mock 검증 통과
   (2026-08-22, 아래 0-3 참고)
3. ~~**`changed_by_history` 재작성**~~ — ✅ 완료(위와 같이 반영됨)
4. **다음 할 일**: 실 데이터(pgvector/Neo4j)로 재검증 — 0-3 섹션 가이드
   참고
5. Step 7(`question_analyzer.py`)은 순서상 그대로 마지막
6. `scripts/link_changed_by.py`/`CHANGED_BY_RELATIONSHIP_TYPE`은 보류(당장
   손 안 댐, 필요해지면 그때 line_number 조회 부분만 고쳐서 되살림)

---

## 0-3. 실 데이터 테스트 가이드 (2026-08-22 — 다음 세션은 여기부터)

지금까지는 전부 mock(가짜 데이터)으로만 로직을 검증했음. 여기서부터는 진짜
pgvector/Neo4j에 데이터를 넣고, 진짜 질문을 던져서 결과를 눈으로 확인하는
단계. **순서대로** 진행할 것 — 앞 단계가 안 되면 뒷 단계는 의미 없음.

### 0단계 — 인프라/환경 확인 (막혀 있으면 나머지 전부 불가능)

- [ ] `.env`에 아래 값이 실제 값으로 채워져 있는지 확인(더미값 아님):
  `DATABASE_URL`, `NEO4J_URI`/`NEO4J_USERNAME`/`NEO4J_PASSWORD`,
  `AZURE_OPENAI_ENDPOINT`/`AZURE_OPENAI_API_KEY`/`AZURE_OPENAI_EMBEDDING_DEPLOYMENT`,
  `GITHUB_TOKEN`/`GITHUB_REPOSITORY_OWNER`/`GITHUB_REPOSITORY_NAME`
- [ ] pgvector `CREATE EXTENSION` 권한 풀렸는지 확인(예전에 `team2db`에서
  막혀 있었음) — 안 풀렸으면 이 단계에서 더 못 감, 관리자에게 먼저 확인
- [ ] 마이그레이션 적용: `flask --app wsgi db upgrade` (code_chunks 테이블에
  이번에 팀원이 추가한 `method_node_id`/`content_hash` 컬럼까지 포함해서
  최신 상태인지 확인)
- [ ] Neo4j 접속 확인 — `.env`의 `NEO4J_URI`가 로컬(`neo4j://localhost:7687`)인지
  공유 서버 주소인지 재확인

### 1단계 — 데이터 적재 (pgvector + Neo4j)

테스트 대상 레포를 로컬에 clone해둔 상태에서, **같은 커밋 하나**를 기준으로
아래 두 개를 순서 상관없이 둘 다 실행(둘 다 `--commit-hash`가 같아야
벡터 결과와 그래프 결과가 서로 맞물림):

```
python scripts/import_chunks.py --github-repository-id <REPO_ID> --repository-path "<로컬 clone 경로>" --commit-hash <커밋 SHA>

python scripts/import_code_graph.py --github-repository-id <REPO_ID> --repository-path "<로컬 clone 경로>" --commit-hash <커밋 SHA>
```

- `<REPO_ID>`는 실제 GitHub 레포 id(더미값 금지 — 코드 여기저기서 이 값 기준으로 조회함)
- `import_code_graph.py`는 기본적으로 GitHub API로 origin이 `<REPO_ID>`와
  실제로 일치하는지 검증함 — 테스트용으로 가짜 레포 id를 쓰고 싶으면
  `--skip-repository-validation` 옵션 추가
- 끝나면 각각 "Chunk import: OK" / "Code graph import: OK" 비슷한 메시지가
  뜸(실패하면 에러 메시지에 원인이 나옴)

**(선택, `intent` 질문까지 테스트하고 싶으면)** GitHub 이력도 적재:

```
python scripts/import_github_history.py
```

- 인자 없음 — `.env`의 `GITHUB_REPOSITORY_OWNER`/`GITHUB_REPOSITORY_NAME`
  기준으로 동작함
- 이게 돌아야 Commit 노드에 실제 커밋 메시지/작성자 등이 채워짐 — 안
  돌리면 `changed_by_history()`가 Commit 노드는 찾아도 내용이 빈약함

### 2단계 — `scripts/check_my_part.py`로 내 파트만 직접 실행

레포/그래프 적재가 끝났으면, 질문 유형 4개(`flow`/`impact`/`location`/`intent`)를
하나씩 바꿔가며 돌려보는 게 제일 빠름:

```
python scripts/check_my_part.py --github-repository-id <REPO_ID> --question "회원 탈퇴는 어떻게 처리돼?" --question-kind flow

python scripts/check_my_part.py --github-repository-id <REPO_ID> --question "이 메서드를 누가 호출해?" --question-kind impact

python scripts/check_my_part.py --github-repository-id <REPO_ID> --question "이 코드가 어디 있어?" --question-kind location

python scripts/check_my_part.py --github-repository-id <REPO_ID> --question "이 로직이 왜 이렇게 바뀌었어?" --question-kind intent
```

**뭘 확인하면 되는지:**
- ① `entity_resolver`는 항상 빈 리스트 — 정상(의도한 동작)
- ② `vector_retriever` 출력에 질문이랑 그럴듯하게 관련된 코드가 top-5로
  나오는지, `similarity` 값이 1에 가까운(0.7~0.9대) 게 있는지
- ③ `graph_retriever` 출력(`nodes`/`edges`)이 **`impact`에서도 이제 빈
  배열이 아니라 실제로 뭔가 나오는지**(이게 이번에 고친 버그) — `intent`도
  Commit 노드가 나오는지
- ④ `evidence_fusion`이 vector+graph 합쳐서 근거 리스트를 만드는지, 중복
  없이 나오는지
- ⑤ `evidence_validator`의 `is_sufficient`가 `True`로 나오는지
- 최종 요약에 "근거 N건, is_sufficient=True"가 찍히면 그 질문 유형은
  정상 동작하는 것

**결과가 이상하면**: 스크립트 출력 그대로(에러 스택트레이스 포함) 캡처해서
알려주면 같이 원인 봐줄게 — 인프라 문제(연결 안 됨)인지, 데이터가 아예
안 들어갔는지, 로직 버그인지 구분이 필요해서.

### 2-1단계 — (신규, 2026-08-22) 재검색 루프가 실제로 끝까지 도는지 확인

`evidence_validator.py`(내가 짠 부분)는 "근거 부족 여부 판단 + retry_count
증가"까지만 함. "부족하면 실제로 vector_retriever로 되돌아가서 다시
검색"하는 라우팅 자체는 `pipeline.py`(원래 있던 배관 코드)의
`_route_after_validation()` + `add_conditional_edges()` 담당.

근데 `pipeline.py` 자체 docstring에 **아직 검증 안 된 위험**이 메모돼 있음:
재시도 시 `vector_retriever`로만 돌아가고 `graph_retriever`는 다시 안
도는데, `evidence_fusion`은 이 둘 다 끝나야 합류(join)하는 구조라서,
재시도했을 때 `evidence_fusion`이 정상적으로 다시 도는지가 미확인 상태.

확인 방법: `scripts/check_pipeline_skeleton.py`로 "근거 부족 -> 재시도
-> 그래도 부족 -> retry_count 소진 -> response_composer까지 도달" 시나리오를
끝까지 돌려보기(7개 노드 monkeypatch 더미로 돌리는 스크립트라 실 데이터
없이도 확인 가능 — 다만 지금은 이 시나리오 자체를 아직 안 돌려봄).
문제 있으면(예: graph_results가 재시도 후 stale하게 남아있거나 fusion이
재실행 안 되면) retry 분기 대상을 `vector_retriever`/`graph_retriever`
둘 다로 바꿔야 함 — 이건 `pipeline.py` 수정이라 내 파트 범위를 살짝
넘을 수 있어서, 필요해지면 팀과 먼저 상의.

- [ ] `check_pipeline_skeleton.py`로 재시도 루프 끝까지 도는지 확인

### 3단계 — 남은 것

- 위 테스트 다 정상이면 Step 1~6은 실 데이터 기준으로도 완료로 확정
- Step 7(`question_analyzer.py`)만 남음 — 이건 별도로 진행(팀원과
  `ChatCompletionService` 먼저 조율)
- `scripts/link_changed_by.py`는 계속 보류(0-2 참고, 지금은 불필요)

---

## 0-4. 두 번째 rebase 이후 재확인 (2026-08-23 — `question_kind` enum 전환 + `target_selector` 신규 노드)

팀원이 `question_kind`를 string에서 `QuestionKind`(StrEnum, `app/dtos/question.py`
신규)로 정리하면서 rebase함. 확인 결과:

- **enum 전환 자체는 이미 내 파일들에 자동으로 잘 반영됨** —
  `state.py`/`graph_retriever.py`/`vector_retriever.py` 전부 `QuestionKind`
  기준으로 잘 맞춰져 있음. `StrEnum`이라 기존 문자열 키("flow" 등) 비교와
  호환돼서 추가로 고칠 것 없음.
- **신규 노드 `target_selector` 삽입됨** (`vector_retriever` -> `target_selector`
  -> `graph_retriever` 순서로 파이프라인 변경, `pipeline.py` 확인함): 벡터
  검색 후보 중 LLM으로 제일 적합한 것 하나를 골라 `state["selected_target"]`에
  담아줌(`app/dtos/target_selection.py`의 `SelectedTarget`). 이 DTO가
  `graph_node_id`/`method_node_id`를 그대로 갖고 있어서 내 `graph_retriever.py`
  수정(0-2 참고)이 자연스럽게 호환됨 — `selected_target`이 없으면
  `vector_results[0]`로 폴백하는 방어 코드도 이미 들어가 있음. **손볼 것 없음.**
- **response_composer.py 구현 완료됨**(팀원 파트) — `app/adapters/response_input_adapter.py`,
  `app/ai/answer_generator.py`, `app/services/response_service.py`,
  `app/visualization/*` 등 새 파일들로 구성됨.
- **⚠️ 팀 확인 필요 (정정된 버전)**: 처음엔 "근거가 답변에 아예 안 쓰인다"로
  이해했는데, 다시 확인해보니 그건 아님 — `answer_generator.py`가 실제로
  `code_context`/`graph_context`/`history_context`를 LLM 프롬프트에 다 넣고,
  intent 질문엔 "Issue/PR/Commit 관계 중심으로 설명하라"는 전용 지침까지
  있어서 깃 이력 근거도 답변 문장에 실제로 반영됨. 진짜 확인할 포인트는 두
  가지:
  1. `state["evidence"]`(내 `evidence_fusion.py`가 만드는, 중복 제거되고
     정리된 근거 리스트)는 `evidence_validator`의 재검색 판단에만 쓰이고,
     `response_composer`는 이걸 안 쓰고 `vector_results`/`graph_results`
     원본을 자기가 따로 한 번 더 가공해서 씀 — 중복 작업 아닌지 확인 필요.
  2. 최종 응답 DTO가 원래 계획(`app/dtos/chat.py`의 `ChatResponseData` —
     summary/claims/evidence/confidence/graph, 프론트가 근거를 별도
     목록/카드로 보여줄 수 있는 구조)보다 단순한 형태
     (`app/dtos/response_generation.py`의 `QueryResponse` — answer/intent/visualization,
     근거는 LLM 답변 문장 속에만 녹아있고 별도 목록으로 프론트에 안 보여줌)로
     바뀜 — 의도된 축소인지, 프론트에 근거를 별도로 보여줄 계획이 있는지
     확인 필요.
  **혼자 판단해서 고치지 말고 팀에 먼저 물어볼 것(내일 회의 예정).**
- `config.py`에 `AZURE_OPENAI_DEPLOYMENT`/`AZURE_OPENAI_NANO_DEPLOYMENT`도
  이미 추가돼 있음 — Step 7 사전 준비 항목 하나 저절로 해결됨.
- `scripts/check_my_part.py`는 아직 `target_selector`를 안 거치고 바로
  `graph_retriever`를 호출하는 예전 체인 그대로임 — 방어 코드 덕분에 안
  깨지긴 하지만(폴백), 정확도 테스트하려면 `target_selector` 단계도 껴서
  업데이트하는 게 좋음(다음 실 데이터 테스트 때 같이 손볼 것).

---

## 0-5. 실 데이터 테스트 중 확인 사항 + 회의 안건 확정 (2026-08-23)

**인프라 연결 확인 완료:**
- Postgres/pgvector: `flask --app wsgi db upgrade` 정상 동작 확인. `code_chunks.embedding`
  컬럼이 `NOT NULL`이라 행이 존재한다는 것 자체가 임베딩까지 채워져 저장됐다는
  뜻 — **pgvector 정상 동작 확인.**
- Neo4j: SSH 터널(`ssh -N -L 7687:127.0.0.1:7687 aihack02@10.250.250.5`)을 통해
  `bolt://127.0.0.1:7687`로 접속 성공, Neo4j Browser에서 직접 데이터 확인함.

**Postgres/Neo4j 대상 프로젝트 일치 여부 — 확인 결과 문제 없음:**
- 처음엔 Postgres(`code_chunks`)와 Neo4j(`Commit` 이력)가 서로 다른 프로젝트를
  가리키는 것처럼 보여서 팀 확인 필요 이슈로 분류했었음.
- 확인해보니 이 프로젝트(RepoMind)의 분석 대상은 애초에 RepoMind-BE 자기
  자신이 아니라 **지정된 외부 GitHub 프로젝트**이고, Postgres/Neo4j 둘 다 그
  동일한 외부 프로젝트 기준인 게 맞음 (2026-08-23 확인). **팀 확인 필요
  목록에서 제외.**

**회의 안건 확정 — Step 7 방식은 LangChain으로 결정 (2026-08-23):**
- 원래 계획(`app/services/chat_completion.py`에 Azure OpenAI SDK를 직접
  호출하는 `ChatCompletionService` 신규 작성)을, 팀원의 `response_composer.py`가
  이미 쓰고 있는 LangChain 패턴(`ChatPromptTemplate | AzureChatOpenAI |
  StrOutputParser`, `app/ai/answer_generator.py` 참고)으로 통일하기로 확정함.
  아래 "Step 7" 섹션도 이에 맞춰 갱신함 — **더 이상 팀 확인 필요 항목 아님.**

**남은 회의 안건 (3개, 0-4 참고):**
1. intent 질문에 `CHANGE_HISTORY` 시각화가 자동으로 붙는 게 의도된 것인지
2. `evidence_fusion.py` 결과가 `response_composer`에서 안 쓰이고 중복 로직이
   있는 것 — 정리할지
3. 최종 응답 DTO(`QueryResponse`)에 구조화된 근거 목록이 빠진 것 — 프론트에
   별도로 보여줄 계획이 있는지

---

## 0-6. 실 데이터 적재 완료 + 등록 파이프라인 정리 (2026-08-23)

**중요 발견 — 수동 import 스크립트 대신 쓸 수 있는 자동 파이프라인이 이미 있었음:**

`POST /api/v1/repositories/`(프론트 "등록하기" 버튼)를 호출하면, 백엔드가
Postgres에 `repositories` row를 만든 직후 **백그라운드 스레드로
`AnalysisPipelineService`를 자동 실행**함 (`app/jobs/dispatcher.py` →
`app/factories/pipeline.py` → `app/services/analysis_pipeline.py`). 이 안에서
GitHub 이력 import → git clone → 코드 그래프 import(Neo4j) → 코드 청크+임베딩
import(Postgres)가 **같은 커밋 기준으로 순서대로 자동 실행**됨. 즉
`import_chunks.py`/`import_code_graph.py`/`import_github_history.py`를 손으로
따로 돌릴 필요 없이, **리포지토리 등록(또는 이미 등록된 리포의 "재분석"
버튼) 하나로 다 됨.** 앞으로 실 데이터 테스트는 이 경로를 우선 사용할 것
(0-3 가이드의 수동 스크립트 방식은 이 자동 경로가 안 될 때의 대안으로 격하).

**겪은 문제들 (다음에 같은 문제 겪으면 참고):**
- Postgres 연결 시 `search_path`가 실제 데이터가 있는 `team2` 스키마를 안
  보고 있어서 `relation "repositories" does not exist` 에러 발생 →
  `DATABASE_URL`에 `&options=-csearch_path%3Dteam2` 추가해서 해결.
- 등록 시도 도중 이미 같은 URL+브랜치로 등록된 (다른 시점에 수동 스크립트로만
  일부 채워졌던, 즉 Postgres 청크는 있는데 Neo4j 그래프는 비어있던) row가
  있어서 `DuplicateRepositoryError`(409) 발생 → 삭제 대신 그 리포 카드의
  **"재분석" 버튼**으로 파이프라인 재실행해서 해결 (재분석은 `ready`/`failed`
  상태에서 다시 실행 가능하게 되어 있음).
- 백엔드 로깅 레벨이 따로 설정 안 되어 있어서(`logging.basicConfig` 없음)
  파이프라인 진행 로그(`logger.info`)가 콘솔에 안 찍힘 — 에러(`logger.exception`)만
  찍힘. 정상 동작 중에도 콘솔이 조용한 게 맞으니, 진행 확인은 로그가 아니라
  `GET /api/v1/repositories/`의 `analysis_status`/`latest_analyzed_sha` 값으로
  할 것.

**결과: 재분석 실행 후 실 데이터(Postgres 청크 + Neo4j 그래프 + GitHub 이력)
전부 정상 적재 확인함 (2026-08-23).** 이제 `check_my_part.py` 등으로 질문별
동작 테스트 가능.

---

## 0-7. Step 7 구현 완료 + 전체 파이프라인(`run_qa_pipeline`) 실 데이터 테스트 (2026-08-23)

**Step 7(`question_analyzer.py`) 구현 완료:** `app/ai/question_classifier.py`
신규 작성, `target_selector.py`와 동일한 LangChain `with_structured_output` 패턴
(`QuestionClassificationDecision` DTO, `app/dtos/question.py`). LLM 실패 시
`QuestionKind.LOCATION`으로 방어적 폴백.

**전체 8노드 파이프라인 실 데이터 테스트 (`scripts/check_full_pipeline.py`,
`run_qa_pipeline()` 직접 호출, 질문 5개: flow×2/impact/location/intent):**
5건 모두 에러 없이 끝까지 실행됨, `question_kind` 분류 정확, 답변 내용에
환각(존재하지 않는 클래스/메서드 지어내기) 없음. impact/intent처럼 근거가
부족한 부분은 "확인할 수 없다"고 정직하게 인정하는 것까지 확인함 (근거 없이
지어내지 않음). **내 파트(Step 1~7: question_analyzer ~ evidence_validator)는
기능적으로 완료 및 검증된 것으로 판단.**

테스트 중 발견한 사항 2가지 (내 코드 문제 아님, 팀 확인용):
- **(0-5 안건 #1 구체화)** `impact`/`intent` 질문에서 콘솔에
  `Unsupported visualization type: DEPENDENCY` / `CHANGE_HISTORY` 경고가 찍힘.
  원인 확인함 — `app/visualization/visualization_builder.py`의
  `VisualizationBuilder._builders`에 `VisualizationType.CALL_FLOW`용
  `CallFlowBuilder`만 등록돼 있고 `DEPENDENCY`/`CHANGE_HISTORY` 타입 빌더는
  아직 없음. `answer` 텍스트 자체는 정상 생성되고 `visualization`만 `None`으로
  빠짐 — 답변 품질에 영향 없음, 그래프 시각화 기능만 미완성. 회의 때 누가
  만들지(또는 CALL_FLOW로만 한정할지) 확정 필요.
- **(신규)** `intent` 질문 테스트 중 Neo4j에서
  `relationship type does not exist: DELETED_IN` 경고(warning, 에러 아님) 발생.
  `changed_by_history` 쿼리(`app/graph/queries/traversal.py`, 그래프 담당자
  파트)가 `(start:Method)-[:DELETED_IN]->(:Commit)`을 OPTIONAL MATCH하는데,
  현재 Neo4j 인스턴스엔 `DELETED_IN` 관계가 한 건도 없음(단일 커밋만 import돼서
  삭제 이력 자체가 없을 가능성 높음 — 아직 급한 문제는 아님, 결과에는 영향
  없었음). 그래프 스키마 담당자에게 "의도대로 아직 안 쓰인 것"인지만 확인
  필요.

**핸드오프(Step 5→response_composer) 코드 레벨로 재확인 (0-5 안건 #2 구체화):**
`app/adapters/response_input_adapter.py`의 `adapt_qa_state()`를 직접 읽어서
확인함 — `state["question"]`/`question_kind`(→intent, visualization_type)/
`selected_target`(→target)/`vector_results`/`graph_results`는 다
`ResponseGenerationInput`으로 정상 매핑됨. **근데 `state["evidence"]`(내
Step 5 `evidence_fusion.py`가 만드는, 벡터+그래프 결과를 중복제거해서 합친
결과물)는 adapter가 아예 안 읽음** — adapter가 `vector_results`/
`graph_results`를 evidence를 거치지 않고 직접 다시 변환해서 씀. 즉
`evidence_fusion.py`는 지금 파이프라인에서 output이 어디에도 안 쓰이는
상태(evidence_validator의 `is_sufficient`/`retry_count`만 pipeline.py 라우팅에
쓰이고, evidence 리스트 자체는 죽은 값). 답변 품질엔 문제 없었지만(어차피
adapter가 같은 원본 데이터를 다시 정리해서 씀), 중복 로직 + dedup 미적용
가능성이 실재함 — 내일 회의에서 "evidence_fusion 없애고 adapter로 통합"할지
"adapter가 evidence를 쓰게 고칠지" 결정 필요.

---

## 0-8. `/chat` 실제 파이프라인 연결 완료 확인 (2026-08-24, FE/BE 재풀 후)

FE/BE 둘 다 다시 pull 받은 뒤 재확인함. **mock 데이터 반환하던 `/chat`이 이제
실제 파이프라인에 연결됨.**

**백엔드 (팀원 작업):**
- `app/api/v1/chat.py`: `get_mock_chat_response()` 대신 `QAService.ask()` 호출로
  교체됨. 세션/레포 상태 에러(`SESSION_NOT_FOUND`, `REPOSITORY_NOT_READY`,
  `QA_PIPELINE_FAILED` 등)도 다 처리돼 있음.
- `app/services/qa_service.py`(신규): 세션 id → `ChatSessionStore.get_with_repository()`로
  레포 조회 → `github_repository_id` 꺼내서(0-7에서 얘기했던 UUID→int 변환
  연결고리, 이미 구현됨) `run_qa_pipeline_state(...)` 호출.
- `app/ai/rag/pipeline.py`에 `run_qa_pipeline_state()` 신규 추가됨 — 기존
  `run_qa_pipeline()`(answer만 반환)은 내부적으로 이 함수를 감싸는 형태로
  리팩터링됨(하위 호환 유지, 내가 쓰던 테스트 스크립트들 그대로 동작).
- `app/adapters/qa_response_adapter.py`(신규, `QAResponseAdapter`): 내
  `evidence_fusion.py`가 만든 `state["evidence"]`를 실제로 읽어서 프론트용
  `ChatResponseData`(claims/evidence/confidence/graph/uncertainties/
  suggestedQuestions)를 채움 — **0-7에서 발견한 "evidence_fusion 죽은 코드"
  문제와 "구조화된 근거 목록 없음" 문제가 둘 다 해결됨** (5번 목록 갱신함).
  `visualization`이 `None`이어도 `state["graph_results"]`로 폴백해서 그래프
  데이터가 아예 안 실리진 않게 처리돼 있음 — DEPENDENCY/CHANGE_HISTORY 전용
  빌더 부재 문제도 완전 해결은 아니지만 완화됨.
- 문법 체크(`py_compile`) 통과, import 체인(`ChatMessageStore.create_exchange`,
  `ChatSessionStore.get_with_repository` 등) 다 실제로 존재 확인함.

**프론트엔드 (팀원 작업):**
- `src/services/apiRepoMindService.ts`의 `askQuestion()`: 더 이상
  `throw new Error('Not implemented yet')` 아님 — 세션 없으면 생성 →
  `/sessions/{id}/chat` 호출 → 대화 이력 재조회해서 assistant 메시지 반환하는
  실제 구현으로 교체됨.

**결론: 이제 웹 화면에서 실제로 질문 입력 → 진짜 파이프라인 답변까지 전체
플로우 테스트 가능한 상태.** `VITE_USE_MOCK` 환경변수가 `true`로 설정돼있지
않은지만 확인하면 됨(기본은 실 API 씀).

---

## 0-9. JavaScript 파서 추가 (2026-08-24, 내 파트 범위 밖 — 그래프 담당자 확인 필요)

RAG 파이프라인이 답을 못 주는 게 아니라, **그래프/청크 파이프라인 자체가
Java만 봐서 대상 리포(`spring-security-react-ant-design-polls-app`)의
React/JS 프론트엔드가 아예 안 잡힌다**는 문제를 발견해서, 승인받은 계획대로
JavaScript 파서 + 공통 스캐폴딩을 추가함. **⚠️ 커밋/푸시는 안 했음 — 로컬
워킹 트리에만 파일을 써놨고, 실제 커밋은 각자 확인 후 진행하는 걸로.**

**⚠️ 이건 그래프 담당 팀원이 만든 파일들을 직접 건드린 작업임
(`app/graph/mappings.py`, `app/services/code_graph_import.py`,
`app/services/chunk_import.py`) — 머지 전에 반드시 그래프 담당자한테
공유하고 확인받을 것.**

**계획**: JS/Python/HTML 셋 다 그래프 레벨까지 만들기로 했었으나(JSP는
범용 tree-sitter 문법이 없어서 이번 범위에서 제외 확정). 이번 세션에서
**JavaScript + 공통 스캐폴딩**까지 완료했고, FE에서 실제로 질문 테스트까지
해봐서 정상 동작 확인함(투표 버튼 클릭 → PollCard → PollList 콜 흐름을 정확히
설명하는 답변 받음). **이어서 Python/HTML까지 마저 완료함 — 아래 0-10 참고.**

**추가/수정된 파일:**
- `app/dtos/protocols.py` (신규) — 언어 무관 구조적 계약(`FileResultProtocol`
  등). 새 언어 DTO가 이 모양만 맞추면 그래프/청크 쪽 코드를 안 건드리고
  바로 붙음.
- `app/dtos/analysis.py` (수정) — `JavaScriptFileResult`/`ClassResult`/
  `MethodResult` 추가. 기존 Java DTO는 안 건드림.
- `app/parsers/languages/javascript.py` (신규) — JS/JSX tree-sitter 파서.
  React class 컴포넌트 + 최상위 함수(화살표 함수 포함)까지 지원. 클래스 밖
  최상위 함수는 파일당 합성 `{파일이름}$module` 클래스로 감싸서 기존
  Class→Method 그래프 모양을 그대로 재사용(스키마 변경 없음).
- `app/parsers/registry.py` (신규) — 확장자 → (파서, 그래프 매퍼) 디스패치
  테이블 + `discover_source_files()`. `node_modules`/`.git`/`dist`/`build`
  등 벤더 디렉터리는 아예 안으로 안 들어가게 걸러냄(`os.walk` prune 방식이라
  `node_modules` 통째로 스킵 — 성능상 중요).
- `app/graph/mappings.py` (수정) — **가장 신경 써야 할 파일.**
  `map_java_file`/새 `map_javascript_file` 둘 다 공용 `_map_file_document()`로
  위임하도록 리팩터링(동작은 Java 기존과 동일 — 기존
  `tests/test_code_graph_mapper.py`의 모든 assert를 그대로 돌려서 확인함,
  전부 통과). Class/Method/MethodVersion 노드에 `language` property 추가하고,
  `resolve_cross_file_references()`의 이름 인덱스를 `(language, name)` 튜플
  키로 바꿈 — Java `save()`와 JS `save()`처럼 이름이 우연히 겹칠 때 서로
  잘못 이어지는 걸 막기 위함(수정 전엔 실제로 잘못 이어지는 걸 재현 테스트로
  확인했고, 수정 후 해결 확인함 → `tests/test_cross_language_mapping.py`).
- `app/services/chunking.py`, `code_graph_import.py`, `chunk_import.py`
  (수정) — `*.java` 하드코딩 rglob을 `app/parsers/registry.py` 기반 루프로
  교체. Java 전용 타입 힌트를 `FileResultProtocol` 등으로 일반화.
- `pyproject.toml` (수정) — `tree-sitter-javascript>=0.23,<1` 의존성 추가
  (설치된 tree-sitter 코어 0.26.0과 호환 확인함).
- `tests/test_javascript_parser.py`, `test_parser_registry.py`,
  `test_cross_language_mapping.py` (신규, 11개 테스트 전부 통과 확인).

**검증한 것 / 못 한 것 (솔직하게):**
- 순수 로직(파서 출력, 매퍼 출력, 레지스트리 디스패치, 크로스 언어 이름
  충돌 수정)은 로컬에서 직접 실행해서 확인함. 기존
  `tests/test_code_graph_mapper.py`의 assert 6개를 전부 그대로 재현해서
  수정 후에도 동일하게 통과하는 것도 확인함(회귀 없음).
- **Flask 앱 컨텍스트가 필요한 테스트(`tests/test_chunk_import.py`,
  `tests/test_code_graph_import.py`, `conftest.py`가 DB에 붙는 구조)는
  이 환경에 Flask/SQLAlchemy 전체 스택이 없어서 못 돌려봄** — 로직상
  동등하게 바꿨다고 판단했지만, **`pytest` 전체는 로컬에서 한 번 직접
  돌려보고 머지할 것**.
- Neo4j/pgvector 실제 연결한 end-to-end 임포트(`CodeGraphImportService`/
  `ChunkImportService`를 대상 리포에 실제로 돌려보는 것)는 아직 안 함 —
  다음 단계.

**다음에 할 것:**
1. `pytest` 로컬에서 전체 돌려서 초록불 확인
2. 그래프 담당 팀원한테 `mappings.py`/`code_graph_import.py`/`chunk_import.py`
   변경 내용 공유하고 리뷰받기
3. ~~`pip install -e .` 재실행해서 의존성 설치 반영~~ — 완료, `재분석` 버튼으로
   실 데이터 테스트까지 확인함(위 참고)
4. ~~대상 리포의 실제 `.jsx` 파일로 실제 돌려서 확인~~ — **완료.** FE에서
   PollCard 투표 흐름 질문 → PollList.handleVoteSubmit까지 정확히 추적하는
   답변 받음(JS 그래프 노드가 실제로 쓰이고 있다는 뜻)
5. ~~Python 파서~~ — **완료, 아래 0-10 참고**

---

## 0-10. Python + HTML 파서 추가 (2026-08-24, 이어서 완료)

0-9에서 미룬 Python/HTML까지 마저 완료함. **여전히 커밋/푸시는 안 했음 —
파일만 로컬 워킹 트리에 씀, 그래프 담당자 리뷰 필요한 것도 0-9와 동일.**

**추가된 파일:**
- `app/parsers/languages/python.py` (신규) — Python tree-sitter 파서. class +
  모듈 최상위 함수(JS와 동일하게 `{파일이름}$module`로 감쌈) 지원.
  `__init__`은 이름 규칙으로 생성자 판별. 데코레이터(`@app.route`,
  `@staticmethod` 등)가 선언을 한 겹 감싸는 `decorated_definition` 노드
  처리 추가됨(Java/JS엔 없던 Python 고유 케이스). 필드는 타입 힌트
  (`x: Type`) + `__init__`의 `self.x = SomeClass()` 생성자 호출 패턴
  best-effort 추론 둘 다로 뽑음(파이썬은 필드 타입 선언이 강제가 아니라서
  후자 없인 리시버 타입 매칭이 거의 안 됨).
- `app/parsers/languages/html.py` (신규) — HTML 자체는 별도 DTO 없이
  `<script>` 태그 안 인라인 JS만 뽑아서 기존 `parse_javascript_file()`에
  위임(그래프 매퍼도 `map_javascript_file` 그대로 재사용, 새 매퍼 안 만듦).
  `src="..."`만 있고 본문 없는 스크립트 태그는 자동으로 건너뜀.
- `app/graph/mappings.py` (수정) — `map_python_file` 추가(기존과 동일하게
  `_map_file_document`에 위임, `language="python"`).
- `app/parsers/registry.py` (수정) — `.py`/`.html` 확장자 등록.
- `app/dtos/analysis.py` (수정) — `PythonFileResult`/`ClassResult`/
  `MethodResult` 추가.
- `pyproject.toml` (수정) — `tree-sitter-python`, `tree-sitter-html` 의존성
  추가.
- `tests/test_python_parser.py`, `test_html_parser.py` (신규) + 기존
  `test_cross_language_mapping.py`/`test_parser_registry.py`에 Python/HTML
  케이스 추가 — **총 22개 테스트 전부 로컬에서 통과 확인**(3-way 언어 충돌
  테스트: Java/JS/Python이 전부 `save()`를 갖고 있어도 서로 안 섞이는 것까지
  확인함).

**주의할 점 (아직 못 검증한 것):**
- Python은 대상 리포(폴링앱)에 실제 `.py` 파일이 없어서 합성 fixture로만
  검증함 — 계획 문서에 원래 적어둔 그대로("Python은 target repo에 실 데이터
  없으니 합성 fixture로 검증"). 실 데이터로 검증하려면 Python 코드가 있는
  다른 리포로 재분석 돌려봐야 함.
- HTML은 대상 리포에 `public/index.html` 정도만 있어서(React CRA 기본
  템플릿, 인라인 스크립트 없음) 실질적으로 새로 잡히는 그래프 노드는 거의
  없을 가능성 높음 — 계획에서부터 "실질 가치는 제일 낮다"고 적어뒀던 부분,
  예상대로임.
- Flask/DB 붙는 테스트는 여전히 이 환경에서 못 돌려봄(0-9와 동일한 한계) —
  `pytest` 전체는 로컬에서 한 번 돌려보고 머지할 것.

---

## 0-11. TypeScript(.ts/.tsx) 파서 추가 (2026-08-24, 이어서 완료)

0-9/0-10과 같은 additive 패턴으로 TypeScript/TSX까지 추가함. **여전히
커밋/푸시는 안 했음 — 파일만 로컬 워킹 트리에 씀, 그래프 담당자 리뷰 필요한
것도 0-9/0-10과 동일.**

**JS 파서와 다른 점(그래서 새로 만든 이유 — 재사용 안 하고 별도 파일로 분리)**:
- `.ts` grammar와 `.tsx` grammar가 실제로 다른 두 개 패키지 export(`tree-sitter-typescript`가
  `language_typescript()`/`language_tsx()`를 각각 제공)라, 확장자로 반드시
  구분해서 골라 씀 — `.ts`는 JSX 문법을 아예 못 읽음.
- `interface` 문법이 실제로 있어서 `kind="interface"`로 Java와 동일하게
  구분함(JS/Python엔 이 구분이 없음). 인터페이스는 본문 없는 시그니처라
  `methods`는 항상 빈 튜플.
- 클래스 필드에 타입 주석이 실제로 있어서(`private repo: PollRepository`),
  JS/Python처럼 생성자 호출로 타입을 추측할 필요 없이 진짜 타입을 그대로 씀 —
  리시버 타입 매칭 정확도가 JS/Python보다 높음.
- 제네릭 상속(`extends BaseRepository<User, number>`)을 Java의
  `JpaRepository<Entity>`와 동일한 방식으로 `extends_generic_params`에 보존함.

**추가/수정된 파일:**
- `app/parsers/languages/typescript.py` (신규) — TS/TSX tree-sitter 파서.
- `app/dtos/analysis.py` (수정) — `TypeScriptFileResult`/`ClassResult`/
  `MethodResult` 추가.
- `app/graph/mappings.py` (수정) — `map_typescript_file` 추가(기존과 동일하게
  `_map_file_document`에 위임, `language="typescript"`).
- `app/parsers/registry.py` (수정) — `.ts`/`.tsx` 확장자 등록(둘 다 같은
  `parse_typescript_file`을 참조 — 내부에서 `path.endswith(".tsx")`로 grammar
  분기). "의도적 미지원" 주석에서 TS/TSX 제거(이제 지원하므로).
- `pyproject.toml` (수정) — `tree-sitter-typescript>=0.23,<1` 의존성 추가.
- `tests/test_typescript_parser.py` (신규, 9개) + 기존
  `test_cross_language_mapping.py`(Java/JS/Python/TS 4-way `save()` 충돌
  테스트로 확장)/`test_parser_registry.py`(`.ts`/`.tsx` 등록 확인 + 벤더 제외
  fixture에 `.ts`/`.tsx` 추가)에도 반영 — **총 31개 테스트 전부 로컬에서
  통과 확인.**

**구현 중 발견 + 고친 버그**: `_extract_class_heritage()`가 처음엔 `extends`
절에서 베이스 클래스 식별자 노드 하나만 골라 텍스트를 뽑았는데, 이 방식이
그 바로 옆의 제네릭 타입 인자 노드(`type_arguments`, `<User, number>` 부분)를
텍스트에서 통째로 빼먹어서 `extends_generic_params`가 항상 빈 튜플로
나오는 버그가 있었음. `class UserRepository extends BaseRepository<User, number>`
같은 실제 케이스로 스모크 테스트하다가 발견함. `extends` 절 전체 텍스트에서
`extends` 키워드만 떼어내는 방식으로 고쳐서 해결 — 수정 후
`extends_generic_params == ("User", "number")`로 정상 확인, 회귀 방지용
테스트(`test_generic_extends_captures_all_type_arguments`)도 추가함.

**검증한 것 / 못 한 것 (솔직하게):**
- 순수 로직(파서 출력, 매퍼 출력, 4-way 크로스 언어 이름 충돌)은 로컬에서
  직접 실행해서 확인함(31개 테스트 전부 통과).
- **대상 리포(폴링앱)의 실제 데이터로는 아직 검증 안 함** — 이 리포 자체는
  프론트가 JS(.jsx)라 `.ts`/`.tsx` 파일이 없어서, Python처럼 합성 fixture로만
  검증한 상태. 만약 다른 실제 TS 프로젝트(예: RepoMind-FE 자체가 TS라면 그걸)로
  재분석을 돌려보면 실 데이터 검증이 가능함 — 아직 안 해봄.
- Flask/DB 붙는 테스트는 여전히 이 환경에서 못 돌려봄(0-9/0-10과 동일한
  한계) — `pytest` 전체는 로컬에서 한 번 돌려보고 머지할 것.

**다음에 할 것:**
1. `pytest` 로컬에서 전체(31개) 돌려서 초록불 재확인
2. 그래프 담당 팀원한테 0-9/0-10과 함께 `mappings.py`/`registry.py` TS 관련
   변경 내용 공유하고 리뷰받기
3. 여유 있으면 TS 실 데이터로 재분석 한 번 돌려서(RepoMind-FE 등) 그래프에
   `language="typescript"` 노드가 실제로 생기는지 확인

---

## 0-12. "코드 실행 흐름" 그래프 라벨/타입 개선 (2026-08-24)

FE에서 실제 질문을 던져보고 나온 "코드 실행 흐름" 시각화가 알아보기 어렵다는
피드백을 받아서(노드 배지가 전부 "SYMBOL"로 뭉쳐 있고, 노드 하나는
"코드 버전 (L25-178)"처럼 라인 번호만 보여줘서 무슨 메서드인지 안 보이고,
다른 노드는 "server$module.createClient()"처럼 파서 내부 네이밍이 그대로
노출됨) 원인을 추적해서 고침. **⚠️ 커밋/푸시는 안 했음, 파일만 씀 — 아래
세 파일 모두 리뷰 필요.**

**원인 (정확히 특정함)**: `app/graph/queries/traversal.py`의
`_node_type()`/`_node_label()`이 진짜 원인이었음 —
- `_node_type()`이 Method/MethodVersion/Class/Interface를 전부 "symbol"
  하나로 뭉쳐서 반환 → FE가 전부 같은 "SYMBOL" 배지로 그림.
- `_node_label()`의 MethodVersion 케이스가 자기 자신의 속성(startLine/
  endLine)만 보고 라벨을 만듦 — 정작 "누구의" 버전인지(메서드 이름)는
  부모 Method 노드에만 있어서 안 나옴.
- `_node_label()`의 Method 케이스가 `class_name` 속성을 그대로 써서,
  최상위 함수를 감싸는 합성 클래스 이름("{파일이름}$module" — JS/Python/TS
  파서가 붙이는 내부 전용 이름, app/parsers/languages/*.py 참고)이 그대로
  노출됨(예: "server$module.createClient()").

이 라벨/타입이 실제로 FE까지 어떻게 도달하는지도 코드로 추적함:
`traversal.py` → (CALL_FLOW 질문이면) `app/adapters/response_input_adapter.py`의
`_normalize_node()`가 `label`→`name`으로, `type`을 대문자로 바꿔서
`app/visualization/call_flow_builder.py`에 넘김 → `CallFlowBuilder`가
이름 끝에 ")"가 없으면 "()"를 붙여서 `GraphResponse` 생성 → 이게(또는
CALL_FLOW가 아닌 질문이면 `state["graph_results"]`가 그대로) 최종적으로
`app/adapters/qa_response_adapter.py`의 `_graph_node_from()`을 거쳐 FE
응답(`app/dtos/chat.py`의 `GraphData`)으로 나감.

**수정한 파일:**
- `app/graph/queries/traversal.py` (내 파일, 안전하게 수정 가능)
  - `_node_type()`: "symbol" 하나로 뭉치던 걸 `"method"`/`"method_version"`/
    `"class"`/`"interface"`/`"api"`/`"commit"`로 세분화(그 외는 방어적으로
    `"symbol"` 유지).
  - `_display_class_name()` 신규: 클래스 이름에서 `$module` 접미어만 벗겨냄
    ("server$module" → "server"). Method 라벨에 적용해서
    "server.createClient()" / "client.createClient()"처럼 파일별로
    구분되면서도 내부 네이밍은 안 새어나가게 함.
  - `_collect_method_version_owners()` 신규 + `_node_label()`/`_to_graph_node()`/
    `_path_to_graph_dict()` 수정: calls_forward/calls_backward가 반환하는
    경로엔 HAS_VERSION(Method→MethodVersion) 관계가 이미 포함돼 있다는 점을
    이용해서, MethodVersion 라벨을 만들 때 그 관계에서 부모 Method의
    이름을 끌어와 붙임 — "코드 버전 (L25-178)" → "createClient() (L25-178)".
    부모 Method가 같은 경로 안에 없으면(예: changed_by_history의 단독
    MethodVersion) 예전처럼 라인 번호만 나오는 것으로 안전하게 폴백함(회귀
    테스트로 확인).
- `app/adapters/qa_response_adapter.py` (⚠️ 팀원 파일, 리뷰 필요) —
  `_GRAPH_NODE_TYPES` 화이트리스트에 `"method"`/`"method_version"`/
  `"class"`/`"interface"` 추가. **이거 안 하면 traversal.py를 아무리
  고쳐도 여기서 전부 "symbol"로 도로 뭉개져서 FE까지 하나도 안 감** —
  실제로 로컬에서 재현해보고 확인한 문제임.
- `app/dtos/chat.py` (⚠️ 팀원 파일, 리뷰 필요) — `GraphNode.type`의
  `Literal`에 같은 4개 값 추가(타입 힌트 정합성 — 런타임 강제는 안
  되지만 계약 문서로서 부정확해지는 걸 방지).
- `tests/test_graph_traversal.py` — 기존 테스트 1개(`MethodVersion` type
  기대값이 "symbol"이던 것)를 "method_version"으로 수정 + 신규 4개
  (타입 세분화, `$module` 접미어 제거, HAS_VERSION 통한 이름 붙이기,
  부모를 못 찾을 때의 폴백) 추가.

**검증한 것:**
- `traversal.py`/`qa_response_adapter.py`/`dtos/chat.py` 순수 로직은
  로컬에서 직접 실행(fake Node/Path 객체로 실제 스크린샷 시나리오를
  그대로 재현) — MethodVersion 노드가 "handleConnect() (L25-178)"로,
  두 `createClient()`가 "server.createClient()"/"client.createClient()"로
  구분되는 것 확인함.
- `traversal.py` → `response_input_adapter.py` → `call_flow_builder.py` →
  `qa_response_adapter.py`까지 전체 체인을 로컬에서 이어붙여서 최종
  `GraphNode(type="method_version", label="handleConnect() (L25-178)")`
  형태로 끝까지 정상 도달하는 것까지 확인함(라벨/타입 둘 다 FE 응답
  직전까지 안 깨짐).
- 관련 기존 테스트 전부(`test_graph_traversal.py`, `test_qa_response_adapter.py`,
  `test_visualization_builder.py`, `test_response_generation_dtos.py`,
  나머지 파서/그래프 테스트 포함 총 51개) 로컬에서 통과 확인 — 회귀 없음.

**아직 안 한 것 / 팀 논의 필요:**
- FE가 새로 늘어난 `type` 값("method"/"method_version"/"class"/"interface")을
  실제로 다른 배지/아이콘으로 그리게 바꾸는 건 프론트 담당자 작업 — 지금은
  값만 세분화된 상태고, FE가 몰라도 최소한 깨지진 않음(기존에 없던 값이
  추가된 것뿐이라 기존 렌더링 로직이 default 처리만 잘 해두면 안전).
- Method/MethodVersion이 그래프 내부 모델링(CALLS가 버전에서 출발) 때문에
  화면에 별개 노드로 노출되는 구조적인 문제는 이번엔 안 건드림(라벨/타입만
  고침) — 필요하면 팀 논의해서 화면상 하나로 합칠지 결정할 것.
- 실 데이터(Neo4j 붙여서)로는 아직 검증 안 함 — 로컬 fake 객체 재현으로만
  확인한 상태, FE에서 실제 질문 다시 던져서 스크린샷과 비교해보는 게 최종
  확인.

---

## 0-13. "location" 그래프 File 노드 라벨 + FLOW 그래프 EXPOSES 엣지 필터링 버그 수정 (2026-08-24~26)

두 라운드로 나뉘어 진행됨: 먼저 팀원의 이력(history) 관련 머지를 pull 받은
뒤 그래프 부분이 잘 살아있는지 확인하다가 두 개의 새 버그를 찾아서 리포트만
해뒀고, 이어서 사용자가 스크린샷으로 새로 보고한 "location" 시각화 문제를
같은 세션에서 진단·수정함. 이번 절은 그 두 라운드를 합쳐서 기록.

### (A) File/Package 노드 라벨 버그 (2026-08-24, 두 번째 라운드)

"이 파일이 어디서 쓰이나요" 류의 LOCATION 질문(`shallow_neighborhood` 탐색)에
대한 그래프 시각화에서, File 노드 라벨이 사람이 읽을 수 있는 파일명이 아니라
내부 그래프 key(`"123231656:file:polling-app-client/src/app/App.js"`)가 그대로
노출되는 문제를 사용자가 스크린샷으로 제보함.

**원인**: `app/graph/repositories/code_graph.py`의 `ALLOWED_NODE_LABELS`에는
`File`/`Package`가 정상적인 노드 타입으로 포함돼 있고 `app/graph/mappings.py`가
실제로 File 노드를 만드는데(속성은 `path`만 있고 `name`은 없음), 0-12에서
고친 `traversal.py`의 `_node_type()`/`_node_label()`/`_node_detail()`이
Method/MethodVersion/Class/Interface/Endpoint/Commit만 알고 File/Package는
전혀 모르는 상태였음 — 그래서 전부 방어적 기본값(`"symbol"` 타입 +
`node.get("name") or node.get("key")` 라벨)으로 떨어졌고, `name`이 없으니
`key`가 그대로 라벨로 노출됨.

**수정 (`app/graph/queries/traversal.py`, 내 파일)**:
- `_node_type()`에 `"File"→"file"`, `"Package"→"package"` 분기 추가.
- `_node_label()`에 File 분기 추가 — `path`에서 파일명만 잘라서 보여줌
  (`path.rsplit("/", 1)[-1]`), Package는 `name` 그대로.
- `_node_detail()`에 File 분기 추가 — 전체 경로는 여기 보존(라벨은
  파일명만, 필요하면 detail에서 전체 경로 확인 가능).
- `tests/test_graph_traversal.py`에 회귀 테스트 2개 추가
  (`test_file_node_shows_filename_instead_of_raw_graph_key`,
  `test_package_node_is_typed_distinctly_from_generic_symbol`).

**함께 넓힌 화이트리스트**: `app/adapters/qa_response_adapter.py`의
`_GRAPH_NODE_TYPES`와 `app/dtos/chat.py`의 `GraphNode.type` Literal에
`"file"`/`"package"` 추가 — 0-12와 같은 이유(안 넓히면 traversal.py가 아무리
잘 분류해도 여기서 다시 "symbol"로 뭉개짐).

### (B) FLOW 그래프에서 EXPOSES(엔드포인트) 엣지가 조용히 사라지는 버그 (2026-08-24 발견, 2026-08-26 수정)

(A)와 별개로, 팀원이 pull한 이력(history) 관련 머지에 `qa_response_adapter.py`의
`_filtered_flow_graph()`/`_log_graph_diagnostics()`가 새로 딸려 들어온 걸
확인하던 중 발견. FLOW 그래프를 FE에 공개하기 전에 "진짜 flow에 쓰는 엣지
타입"만 남기고 걸러내는 방어 로직인데, 화이트리스트(`_FLOW_EDGE_TYPES`)가
`{"calls", "http_calls", "handled_by"}`로 돼 있었음.

**원인**: 코드베이스 전체를 grep해도 `"HANDLED_BY"`/`"handled_by"`를 만드는
곳이 어디에도 없음 — Method→Endpoint 관계로 실제 쓰이는 타입은
`app/graph/repositories/code_graph.py`의 `ALLOWED_RELATIONSHIP_TYPES`와
`app/graph/queries/traversal.py`의 `endpoint_path` 쿼리에 있는 `"EXPOSES"`
(소문자화되면 `"exposes"`)뿐. 즉 존재하지도 않는 타입 이름을 화이트리스트에
넣어놓은 것이어서, 실제 EXPOSES 엣지는 전부 `_filtered_flow_graph()`에서
걸러지고, 그 엣지에만 연결된 엔드포인트 노드까지 같이 사라짐 — API 엔드포인트
질문(예: "이 취소 요청은 어느 엔드포인트에서 처리돼?")에 대한 FLOW 그래프에서
엔드포인트 노드 자체가 통째로 안 보이는 결과가 됨. fake Neo4j 객체로 재현해서
실제로 확인함.

**수정 방향은 사용자와 상의 후 결정**: 엣지 타입 이름을 새로 만들어서
어딘가에서 rename하는 방식도 가능했지만, 다른 관계 타입들과 동일하게
"Neo4j 관계 이름을 그대로 소문자화"하는 `_graph_edge_from()`의 기존 규칙을
따르는 쪽으로 정리하기로 함(새 메커니즘을 안 늘리는 쪽).

**수정한 파일:**
- `app/adapters/qa_response_adapter.py` (⚠️ 팀원 파일) — `_FLOW_EDGE_TYPES`에서
  `"handled_by"`를 빼고 `"exposes"`로 교체.
- `app/dtos/chat.py` (⚠️ 팀원 파일) — `GraphData` 클래스 docstring이
  `"``kind == 'flow'`` exposes only ``calls``, ``http_calls``, and
  ``handled_by`` edges."`로 돼 있던 걸 `"exposes"`로 수정(코드 계약과
  문서가 어긋나 있던 것도 같이 바로잡음).
- `tests/test_qa_response_adapter.py` — 회귀 테스트 신규 추가
  (`test_flow_graph_keeps_endpoint_nodes_reached_via_exposes_edge`):
  Method→Endpoint EXPOSES 엣지가 있는 FLOW 그래프를 넣었을 때 엔드포인트
  노드와 엣지가 살아남는지 확인.

### (C) `_filtered_flow_graph()`가 엣지가 하나도 없을 때 노드까지 지우는 동작 (수정 안 함 — 의도된 결정)

같은 파일을 보다가 발견한 별개의 문제: 호출이 하나도 없는 메서드에 대해
FLOW 질문을 하면(`GraphResponse.edges == []`), `_filtered_flow_graph()`의
`connected_ids` 집합이 비어서 유일한 노드까지 걸러져 빈 그래프
(`nodes=[], edges=[]`)가 나감. 이 때문에 기존 테스트
`test_adapts_grounded_rag_response_with_visualization`이
`result.graph.nodes[0].type == "symbol"`을 기대하다가 `IndexError`로 깨져
있었음.

**사용자에게 두 가지 선택지를 제시함**: (1) 고립 노드라도 화면에 보이게
`_filtered_flow_graph()` 로직을 바꾸는 안(내 추천), (2) 지금 동작(빈 그래프)을
그대로 유지하고 테스트 기대값만 현재 동작에 맞게 고치는 안. **사용자가
(2)를 선택함 — "빈 그래프 유지, 테스트만 수정".** 즉 `_filtered_flow_graph()`의
동작은 의도적으로 안 건드림.

**수정한 파일:**
- `tests/test_qa_response_adapter.py` — 해당 테스트의 마지막 부분을
  `assert result.graph.nodes[0].type == "symbol"` → `assert result.graph.nodes
  == []` / `assert result.graph.kind == "flow"`로 수정(현재 동작을 정확히
  기술하도록).

**참고**: 호출이 하나도 없는 메서드의 FLOW 그래프가 통째로 비어 보이는 게
FE 입장에서 여전히 어색할 수 있음 — 나중에 UX 논의가 다시 나오면 (C)의
선택지 (1)로 되돌릴 수 있다는 점을 팀에 남겨둠(코드 변경은 지금 없음, 결정
기록만).

**검증한 것:**
- `tests/test_qa_response_adapter.py` + `tests/test_graph_traversal.py`
  로컬 실행 — 16개 전부 통과.
- `pytest tests/ --ignore=tests/test_response_generation_dtos.py` 전체
  로컬 실행 — 51개 전부 통과(제외한 1개는 `app.ai.rag.evidence_ids` 모듈이
  이 세션의 로컬 미러에 없어서 생기는 순수 샌드박스 제약이고, 이번 수정과는
  무관 — 0-9/0-10/0-11에서도 반복 언급된 동일한 한계).

**아직 안 한 것:**
- 실 데이터(Neo4j)로는 검증 안 함 — fake 객체 재현 + 단위 테스트로만 확인.
- (C)에서 남긴 "고립 노드 숨김" UX가 실제로 괜찮은지는 FE에서 빈 호출
  메서드로 다시 질문해서 확인해볼 것.

---

## 0-14. 후속 질문이 이전 대화 맥락을 못 잡는 문제 — 원인 확정 (2026-08-26, ⚠️ 구현은 0-15에서 완료됨)

사용자가 "질문 하나 하고 이어서 질문하면 맥락이 잘 안 이어지는 것 같다"고
보고해서 코드로 원인을 추적함. **Claude 세션 문제가 아니라 RepoMind 백엔드
자체의 실제 동작임을 확인.**

**원인 (정확히 특정함)**: `app/services/qa_service.py`의 `QAService.ask()`가
`run_qa_pipeline_state()`를 호출할 때 `conversation_id=str(context.session_id)`를
넘겨서 `QAState.conversation_id`(`app/ai/rag/state.py`)에 실리긴 하지만,
파이프라인의 9개 노드(`question_analyzer`, `entity_resolver`,
`vector_retriever`, `target_selector`, `graph_retriever`, `evidence_enricher`,
`evidence_fusion`, `evidence_validator`, `response_composer`) 중 이 값을
실제로 읽는 곳이 하나도 없음(`grep -rn "conversation_id"` 전체 결과로 확인 —
정의/전달만 있고 소비하는 곳이 없음). 이전 대화를 조회하는
`ChatMessageStore.list_by_session()`(`app/repositories/chat_message.py`)도
이미 구현돼 있지만, 실제로 호출되는 곳은 `app/api/v1/chat.py`에서 답변이
끝난 뒤 **저장**(`create_exchange`)할 때뿐 — 새 질문을 처리하기 *전에* 이전
메시지를 불러와서 파이프라인에 넘기는 코드는 어디에도 없음.

결과적으로 FE 화면엔 이전 대화가 다 보이지만(FE가 세션 메시지 목록을 별도로
다시 불러와서 렌더링함, 0-8 참고), 백엔드 입장에서는 매 질문이 완전히
독립적으로(이전 질문/답변을 전혀 모르는 상태로) 검색·분류·답변됨 — 그래서
"그거 어떻게 고쳐?"류의 후속 질문이 "그거"가 뭔지 못 잡음.

**사용자와 상의한 구현 방향 (참고용으로 기록, 아직 미채택):**
1. 후속 질문 재작성(query rewriting) — 새 노드(또는 question_analyzer 확장)가
   `ChatMessageStore.list_by_session()`으로 최근 대화를 불러와서, LLM으로
   후속 질문을 독립형 질문으로 재작성한 뒤 그 결과를 기존 검색 파이프라인에
   그대로 흘려보냄. 검색(vector/graph) 정확도까지 같이 개선됨 — 이번 대화에서
   추천한 방향.
2. 답변 생성 프롬프트에만 최근 대화 이력 주입 — 검색은 원문 질문 그대로 쓰고,
   `response_composer`/`answer_generator.py` 프롬프트에만 최근 이력을 곁들여서
   톤/맥락만 자연스럽게. 구현은 더 간단하지만 검색 자체의 정확도는 못 고침.
3. 1+2 하이브리드.

**사용자 결정 (2026-08-26, 최초)**: 일단 설명만 듣고 구현은 보류. →
같은 날 대화를 이어가면서 옵션 1(질문 재작성)으로 바로 구현해달라는 요청을
받아서 실제로 구현함 — 아래 0-15 참고.

---

## 0-15. 후속 질문 재작성(query rewriting) 구현 — 0-14 이어서 (2026-08-26)

0-14에서 진단만 하고 보류했던 걸, 같은 대화에서 "질문 재작성 방식으로
구현해줘"라는 요청을 받아 실제로 구현함. 방향은 0-14에서 정리한 옵션 1
(검색 이전 단계에서 질문 자체를 독립형으로 재작성) 그대로.

**왜 옵션 1인지 (사용자 질문에 답한 내용)**: `vector_retriever.py`가
`state["question"]`을 그대로 임베딩해서 pgvector 검색을 하고,
`graph_retriever.py`는 그 결과의 `graph_node_id`를 Neo4j 탐색 시작점으로
쓴다. "그거 어떻게 고쳐?"를 원문 그대로 임베딩하면 애초에 관련 없는 코드가
검색되므로, 답변 생성 프롬프트에만 이력을 곁들이는 옵션 2는 이미 잘못 검색된
근거를 못 고친다 — 오히려 `evidence_validator`가 "근거 불충분"으로 재시도만
반복할 위험도 있음. 검색 이전에 질문 자체를 고치는 게 근본적인 해결책.

**신규/수정 파일 (전부 내 파트, 팀원 리뷰 불필요):**
- `app/dtos/question_rewrite.py` (신규) — `QuestionRewriteDecision`
  (`rewritten_question`, `reason`), `app/dtos/question.py`의
  `QuestionClassificationDecision`과 동일한 패턴.
- `app/ai/generation/prompts.py` — `QUESTION_REWRITE_SYSTEM_PROMPT`/
  `QUESTION_REWRITE_USER_PROMPT` 추가. 대명사·생략된 주어를 이전 대화에서
  가리키는 실제 대상으로 채워 넣되, 질문의 의도 자체는 바꾸지 말라고 명시.
- `app/ai/question_rewriter.py` (신규) — `QuestionRewriter` /
  `create_azure_question_rewriter`. `app/ai/question_classifier.py`와
  완전히 동일한 구조: LLM 실패 시 예외를 삼키고 **원본 질문을 그대로
  반환**(파이프라인을 막지 않는 방어적 폴백). `history`가 빈 문자열이면
  (세션의 첫 질문) LLM을 아예 호출하지 않음 — 불필요한 지연/비용 방지.
- `app/ai/rag/nodes/question_rewriter.py` (신규) — 새 파이프라인 노드
  `rewrite_follow_up_question()`. `state["conversation_id"]`가 없으면(스크립트/
  테스트 등 세션 밖 호출) 완전히 스킵. 있으면 `ChatMessageStore.list_by_session()`
  으로 세션 메시지를 불러와서(최근 3턴 = 메시지 6개까지만, 프롬프트 무한정
  안 커지게) `QuestionRewriter`를 호출하고, 재작성 결과가 원본과 다를 때만
  `{"question": rewritten}`을 반환해서 state를 덮어씀.
- `app/ai/rag/pipeline.py` — `question_rewriter` 노드를 그래프에 추가하고
  `START -> question_rewriter -> question_analyzer -> ...`로 맨 앞에 배치.
  question_analyzer보다 먼저 와야 하는 이유: 후속 질문의 유형 분류(flow/
  impact/intent/location)도 맥락이 채워진(재작성된) 질문 기준으로 해야
  정확하기 때문.
- `tests/test_question_rewriter.py` (신규) — `QuestionRewriter` 단위 테스트
  5개(재작성 성공/이력 없으면 LLM 스킵/LLM 실패 시 원본 폴백/빈 응답 폴백/
  LLM 없이 생성됐을 때 폴백).
- `tests/test_question_rewriter_node.py` (신규) — 실제 Flask app context +
  sqlite 테스트 DB로 ChatSession/ChatMessage를 만들어서 노드 자체를 통합
  테스트(conversation_id 없음/첫 질문/이전 대화로 재작성/재작성 결과가
  원본과 같으면 patch 없음, 총 4개).
- `tests/test_qa_pipeline.py` — question_rewriter가 question_analyzer보다
  먼저 실행되고, 재작성된 질문이 이후 모든 노드(question_analyzer,
  vector_retriever 등)에 그대로 전달되는지 확인하는 파이프라인 순서 테스트
  1개 추가. 기존 2개 테스트는 `conversation_id`를 안 넘기므로(None → 노드가
  LLM/DB 호출 없이 바로 스킵) 수정 없이 그대로 통과함.

**검증한 것:**
- 신규 테스트 10개 + 기존 `test_qa_pipeline.py`/`test_qa_service.py` 전부
  로컬에서 통과 확인.
- `pytest tests/` 전체(286개, flask_cors 등 누락 의존성 설치 후 처음으로
  이 세션에서 전체 스위트를 완전히 돌려봄) 통과 — 회귀 없음.

**아직 안 한 것 / 참고:**
- 실 데이터(Azure OpenAI + 실제 세션)로는 검증 안 함 — LLM 호출부는
  Mock으로만 확인.
- "최근 3턴만 반영"은 임의로 정한 기본값 — 실사용해보고 너무 짧거나 길면
  `app/ai/rag/nodes/question_rewriter.py`의 `MAX_HISTORY_EXCHANGES` 상수만
  고치면 됨.
- 재작성이 매 후속 질문마다 LLM 호출을 하나 더 쓰므로, 응답 지연이 체감될
  정도인지는 실제로 붙여보고 확인 필요(nano 배포 우선 사용이라 비용/속도는
  낮은 편으로 설계함).

---

## 0-16. 그래프에서 getter/setter 노드 제외 (2026-08-26)

사용자 피드백: "그래프가 나올 때 getter, setter 같은 너무 부가적인 노드는
빼고 던져주면 좋겠다." 실행 흐름/의존성/위치 그래프 전부 공통으로 겪는
문제라, 모든 그래프 타입이 거쳐가는 단일 지점인 `traversal.py`의
`_path_to_graph_dict()`에서 한 번에 처리함(FLOW 전용이 아니라 flow/impact/
intent/location 전부에 적용됨 — 아래 "아직 안 한 것" 참고).

**구현 (`app/graph/queries/traversal.py`, 내 파일):**
- `_TRIVIAL_ACCESSOR_NAME_PATTERN = re.compile(r"^(get|set|is)[A-Z0-9]")` +
  `_is_trivial_accessor_name()`: "get"/"set"/"is" 뒤에 대문자·숫자가 바로
  오는 이름만 매치 — "getUsername"/"setPassword"/"isActive"는 걸리고,
  "getaway"/"issueRefund"/"setup" 같은 일반 단어는 안 걸리게 함(오탐 방지,
  회귀 테스트로 확인).
- `_effective_method_name(node, method_version_owner)`: Method 노드는 자기
  `name`, MethodVersion은 자기 이름이 없어서(0-12에서 만든) HAS_VERSION
  소유자 매핑을 통해 부모 Method의 이름을 빌려서 판별.
- `_path_to_graph_dict()`에 `keep_node_id` 파라미터 추가 — 이 탐색의
  시작 노드 key는 getter/setter 패턴에 걸리더라도 무조건 남김("getCurrentUser()
  흐름을 알려줘"처럼 시작점 자체가 getter인 질문까지 사라지면 안 되므로).
  `calls_forward`/`calls_backward`/`shallow_neighborhood`/`changed_by_history`
  4개 함수 전부 자기 `start_node_id`를 이 파라미터로 넘기도록 수정.
- getter/setter로 필터링된 노드를 가리키던 엣지도 같이 제거(양 끝 노드가
  둘 다 남아있는 엣지만 최종 결과에 포함).

**의도적으로 감수한 트레이드오프**: getter/setter 노드를 지우면 그 노드를
거쳐가던 경로의 연결이 끊길 수 있음(예: A가 getB()를 부르고 그 반환값으로
C를 부르는 흐름이었다면, getB()를 지우는 순간 그래프 상으로는 A와 C 사이에
아무 연결도 안 보이게 됨). "정확한 전체 그래프"보다 "읽기 쉬운 요약"을
우선한 의도적 선택 — 실 데이터로 확인해서 너무 자주 끊긴다 싶으면 재논의
필요.

**수정한 파일:**
- `app/graph/queries/traversal.py` — 위 구현.
- `tests/test_graph_traversal.py` — 회귀 테스트 4개 추가: getter/setter
  Method 노드 + 연결된 엣지가 같이 제거되는지, 시작 노드 자체가 getter여도
  `keep_node_id`로 남는지, MethodVersion이 HAS_VERSION 소유자 이름으로
  올바르게 판별되는지, "getaway"류 오탐이 없는지.

**검증한 것:**
- 신규 테스트 4개 + 기존 `test_graph_traversal.py` 9개 전부 통과, 회귀 없음
  확인.

**아직 안 한 것 / 팀 논의 필요:**
- FLOW뿐 아니라 IMPACT/LOCATION/INTENT 그래프에도 전부 적용됨 — 사용자가
  "그래프가 나올 때"라고 일반적으로 말해서 전체 적용으로 해석했는데, 만약
  IMPACT(영향 범위) 질문에서는 getter/setter 호출도 "누가 이 필드에 의존
  하는지" 판단에 필요한 정보일 수 있어서 이 부분은 실사용해보고 너무
  공격적으로 지워진다 싶으면 question_kind별로 켜고 끄는 걸 고려할 것.
- Lombok이 자동 생성하는 `equals`/`hashCode`/`toString`/`canEqual` 같은
  다른 보일러플레이트는 이번 범위에 포함 안 함(사용자가 명시적으로 언급한
  get/set만 처리) — 필요하면 같은 패턴으로 추가 가능.
- 실 데이터(Neo4j)로는 검증 안 함 — fake 객체 재현 + 단위 테스트로만 확인.

---

## 0-17. 서로 무관한 동명 메서드가 CALLS로 잘못 이어지는 문제 ("ChatMessageStore.get() → RepositoryStore.get()"류, 2026-08-26)

사용자가 스크린샷 두 장을 보고함:

1. "PollCard가 호출하는 함수 알려줘" 질문에 PollCard가 아니라 PollList 관련
   노드가 나오고, COMMIT/CLASS 노드까지 섞여서 나옴(이건 아직 미해결 — 아래
   "아직 안 한 것" 참고).
2. **"ChatMessageStore.get() → RepositoryStore.get() → ChatSessionStore.get()"**
   처럼 서로 완전히 무관한 클래스의 동명(`get`) 메서드끼리 CALLS로 이어진
   그래프가 질문과 무관하게 계속 반복해서 나타남("이거 계속 나오는데" — 사용자
   표현).

2번을 코드로 추적해서 원인을 확정하고 고침(1번은 별도 문제, 아래 참고).

**원인 (정확히 특정함, 내 파일이 아닌 곳에서 시작된 문제)**:
`app/graph/mappings.py`의 `resolve_cross_file_references()`(그래프 담당
팀원 파일)는 CALLS 호출 대상을 이름(`(language, name)`)으로 찾는데, 호출부의
리시버 타입을 알아낼 수 있으면(`receiver_type`) 그 타입 소속 메서드로 후보를
좁히지만, 알아낼 수 없으면(예: `self._session.get(...)`처럼 SQLAlchemy
`Session`처럼 이 코드베이스 밖의 타입에 대한 호출이라 `receiver_type`을
못 알아낸 경우) **같은 이름의 메서드 전부**를 후보로 남겨서 `"ambiguous":
True` 속성과 함께 전부에 CALLS 엣지를 만들어버림(mappings.py 599-626줄,
"하나로 못 좁히는 것보다 넓게라도 남기는 게 낫다"는 의도적 절충). `get`처럼
리포지토리 클래스마다 똑같이 존재하는 흔한 이름이 이 경로를 타면,
`ChatMessageStore.get()`이 자기 자신은 물론 `RepositoryStore.get()`,
`ChatSessionStore.get()`까지 전부 "호출"하는 것으로 그래프에 남게 됨 —
실제로는 전혀 사실이 아님. 이 `ambiguous` 속성은
`app/graph/repositories/code_graph.py`의 `SET relation += row.properties`로
Neo4j 관계에 그대로 저장되는 것까지 확인함.

**이미 절반은 막혀 있었다는 것도 확인함**: `app/ai/rag/nodes/evidence_enricher.py`
(내 파일)는 이미 `metadata.get("ambiguous") is True`인 CALLS 엣지를 답변
근거 텍스트 생성에서 제외하고 있었음 — 그래서 LLM이 쓰는 답변 문장에는 이
오류가 안 보였음. 하지만 그래프 **시각화** 경로(`app/graph/queries/traversal.py`,
역시 내 파일)는 같은 체크가 전혀 없어서, 근거 텍스트와 달리 화면에는 이
가짜 CALLS 관계가 그대로 새어나가고 있었음 — 텍스트 답변과 그래프 그림이
서로 다른 이야기를 하고 있었던 셈.

**수정 방향**: `mappings.py`의 해석 알고리즘 자체(그래프 담당 팀원 소유,
"넓게 남기기" 절충은 나름의 이유가 있어 보여서 안 건드림)는 그대로 두고,
이미 Neo4j에 저장돼 있는 `ambiguous` 신호를 그래프 시각화 쪽에서 한 번 더
걸러내는 방식으로 고침 — evidence_enricher.py와 완전히 동일한 기준을
적용해서 "답변 텍스트가 신뢰하지 않는 관계는 그래프도 안 보여준다"로
통일함. 전부 내 파일 안에서 끝나서 팀원 조율 불필요.

**수정한 파일:**
- `app/graph/queries/traversal.py` — `_is_ambiguous_call(relationship)` 신규
  (relationship의 `ambiguous` 속성이 True인지 확인). `_path_to_graph_dict()`의
  엣지 수집 루프에서 `CALLS`/`HTTP_CALLS` 타입이면서 ambiguous인 관계는
  건너뜀 — getter/setter 필터(0-16)와 마찬가지로 4개 traversal 함수
  (`calls_forward`/`calls_backward`/`shallow_neighborhood`/
  `changed_by_history`) 전부에 자동 적용됨(공통 변환 함수라서 별도 배선
  불필요).
- `tests/test_graph_traversal.py` — `FakeRelationship`이 이제 속성을 받을 수
  있도록 `dict` 상속으로 확장(`ambiguous=True` 같은 키워드 인자 지원, 기존
  테스트는 속성 없이 그대로 호출해서 영향 없음). 회귀 테스트 3개 추가:
  ambiguous CALLS 엣지 제외, 정상(비-ambiguous) CALLS 엣지는 그대로 유지,
  ambiguous HTTP_CALLS도 동일하게 제외.

**검증한 것:**
- 신규 테스트 3개 + `test_graph_traversal.py` 전체(16개) 통과.
- `pytest tests/` 전체(289개) 통과 — 회귀 없음.

**아직 안 한 것 / 참고:**
- 실 데이터(Neo4j)로는 검증 안 함 — fake 객체 재현 + 단위 테스트로만 확인.

---

## 0-18. 1번 스크린샷("PollCard가 호출하는 함수" → location 결과) 원인 확정 + 수정 (2026-08-26, 0-17 이어서)

0-17에서 별도 문제로 남겨뒀던 1번 스크린샷("PollCard가 호출하는 함수 알려줘"에
PollList 관련 노드 + COMMIT/CLASS가 섞이고, 메서드들이 서로 안 이어진 채
세로로 나열되던 그래프)을 이어서 진단·수정함.

**구조적으로 확정한 원인**: `calls_forward()`의 Cypher 쿼리(app/graph/queries/
traversal.py)를 다시 확인해보니, 이 쿼리엔애초에 Commit/Class를 가져오는
절이 하나도 없음(CALLS/HTTP_CALLS/HAS_VERSION/EXPOSES 관계만 탐) — 즉
COMMIT/CLASS 노드가 결과에 나온 시점에서, 그 그래프는 물리적으로
`calls_forward`가 만든 게 아니라는 뜻임. `app/adapters/qa_response_adapter.py`의
`_graph_from()`도 확인함: FLOW 의도(intent)면 `_filtered_flow_graph()`로
한 번 더 걸러지거나(calls/http_calls/exposes만 남음) 아예 빈 그래프로
나가지, `state["graph_results"]`를 원본 그대로 노출하는 경로는 FLOW가 아닌
다른 의도(EXPLANATION 등, location에 대응)일 때만 탐. 따라서 이 질문은
사실 FLOW가 아니라 LOCATION(EXPLANATION)으로 분류돼서 `shallow_neighborhood`
(관계 타입 제한 없이 1홉만 얕게 탐색 — CALLS뿐 아니라 HAS_VERSION/
INTRODUCED_IN/CONTAINS까지 전부 탐)가 실행된 것으로 100% 확정함.

**왜 잘못 분류됐는지**: `app/ai/generation/prompts.py`의
`QUESTION_CLASSIFICATION_PROMPT`를 다시 읽어보니, flow 항목의 예시가
"회원가입 요청이 들어오면 어떤 순서로 처리돼?"(처리 "순서")뿐이라, "PollCard가
호출하는 함수 알려줘"처럼 "무엇을 호출하는지 목록으로 묻는" 질문은 flow의
예시와 결이 달라 보여서 location의 "무슨 역할인지 묻는 질문" 쪽으로 새기
쉬운 구조였음. 게다가 프롬프트 마지막 줄에 "애매하면 location을
선택하세요"라는 명시적 기본값까지 있어서, 애매한 케이스가 전부 location
쪽으로 쏠리게 돼 있었음.

**수정 (`app/ai/generation/prompts.py`, 내 파일, 팀원 조율 불필요):**
- flow 항목에 "OO가 호출하는 함수/메서드가 뭐야", "OO는 어떤 API를 호출해?"
  같은 "무엇을 호출하는지" 묻는 질문도 flow라는 걸 명시하고, "PollCard가
  호출하는 함수 알려줘"를 실제 예시로 추가함.
- location 항목엔 "무엇을 호출하는지가 아니라 어디에 있는지/무슨 역할인지가
  핵심일 때만 location"이라고 경계를 명확히 함.
- 애매할 때의 기본값을 "무조건 location"에서 "핵심이 호출/실행이면 flow,
  위치/역할이면 location, 그래도 애매하면 location"으로 구체화함(완전
  제거는 안 함 — 진짜로 애매한 케이스의 안전한 기본값 자체는 유지).

**한계 (LLM 프롬프트 튜닝이라 결정론적으로 검증 불가)**: 이건 실제 Azure
OpenAI 분류 LLM 호출 결과를 바꾸는 수정이라, 이 세션에서 fake 객체로
단위 테스트할 수 있는 종류가 아님(question_classifier.py의 기존 테스트도
전부 Mock LLM 응답으로 QuestionClassifier 클래스의 매핑 로직만 검증하지,
실제 프롬프트 문구가 분류 정확도를 얼마나 바꾸는지는 검증 못 함). **다음에
실 데이터로 확인할 때 "PollCard가 호출하는 함수 알려줘"를 똑같이 다시
물어봐서 이번엔 flow로 분류되는지, calls_forward 결과(COMMIT/CLASS 없이
CALLS로 이어진 메서드들)가 나오는지 직접 확인 필요.**

**수정한 파일:**
- `app/ai/generation/prompts.py` — `QUESTION_CLASSIFICATION_PROMPT` 수정
  (위 내용).

**아직 안 한 것:**
- 실제 재질문으로 검증 안 함(위 한계 참고) — 다음에 꼭 확인.
- "PollCard"라는 이름 자체가 이 레포에 실제로 있는지(React 컴포넌트 구조상
  PollList 안에 인라인으로 poll 카드가 그려지고 별도 PollCard 컴포넌트가
  없을 가능성)는 확인 안 함 — 만약 없다면 분류가 flow로 맞게 고쳐져도
  벡터 검색이 여전히 가장 가까운 대체 대상(PollList)을 고를 것이므로, 이건
  "질문 분류" 문제와 별개로 "존재하지 않는 이름을 물었을 때 어떻게 안내할지"
  UX 문제로 남을 수 있음.
- `shallow_neighborhood` 자체가 (진짜 LOCATION 질문일 때도) COMMIT/CLASS를
  포함한 여러 관계 타입을 한 번에 섞어서 보여주는 구조라, 분류가 맞아도
  결과가 다소 산만할 수 있음 — 이번 수정 범위 밖, 필요하면 별도로 다룰 것.

---

## 0-19. 그래프 화면이 지저분해 보이는 문제 — FE 렌더링 버그 2건 발견 + 수정 (2026-08-26, RepoMind-FE)

**배경**: 0-13~0-18에서 백엔드(노드 타입/엣지 타입/분류 프롬프트)를 계속 고쳤는데도
사용자가 "그래프가 너무 지저분해 보인다"고 계속 얘기해서, 이번엔 FE 저장소
(`RepoMind-FE`, `src/features/graph/CodeFlowGraph.tsx` + `src/types/api.ts`)까지
직접 열어서 확인함. 백엔드가 최근 바꾼 노드/엣지 타입을 FE가 못 따라가고 있는
게 실제 원인 중 하나였음.

**발견한 버그 2건:**

1. **FLOW 그래프에서 API 엔드포인트 노드가 통째로 떨어져 나감.**
   `CodeFlowGraph.tsx`의 `projectFunctionCalls()`가 flow 그래프 엣지를
   `calls` / `http_calls` / `handled_by` 세 종류만 통과시키도록 필터링하고
   있었는데, 0-13에서 백엔드가 이 엣지 타입 이름을 `handled_by` → `exposes`로
   바꿨음. 즉 백엔드는 이제 `exposes`를 보내는데 FE는 여전히 옛날 이름
   `handled_by`만 찾고 있어서, exposes 엣지가 전부 조용히 걸러지고 그
   엣지로만 연결되던 API/엔드포인트 노드들이 떠 있는 것처럼 보였음.
2. **CLASS/METHOD/PACKAGE 등 노드 색이 안 입혀짐.**
   `GraphNodeType`(FE 타입 정의)과 `nodeColors` 매핑이 예전 7종류
   (`project`/`module`/`file`/`symbol`/`api`/`commit`/`document`)만 알고
   있었는데, 백엔드는 0-13 전후로 `class`/`interface`/`method`/
   `method_version`/`package`까지 노드 타입으로 보내고 있었음. FE가 모르는
   타입이 오면 색이 안 입혀져서(스타일 undefined) 눈에 튀는 이상한 노드로
   보임 — 스크린샷의 CLASS 노드가 이 케이스.

**수정한 파일 (RepoMind-FE):**
- `src/types/api.ts` — `GraphNodeType`에 `class`/`interface`/`method`/
  `method_version`/`package` 추가.
- `src/features/graph/CodeFlowGraph.tsx` — `nodeColors`에 위 5개 타입 색상
  추가, flow 그래프 엣지 필터를 `handled_by` → `exposes`로 수정.

**검증**: 이 세션에는 FE 빌드/테스트 환경이 없어서 코드 리뷰 수준으로만
확인함(문법·타입 일치 확인). 실제 화면에서 API 노드가 다시 이어지는지,
CLASS 노드에 색이 들어오는지는 앱 켜서 눈으로 재확인 필요.

**아직 안 한 것 (일부러 손 안 댐):**
- non-flow 그래프(LOCATION/IMPACT/HISTORY, 즉 `shallow_neighborhood` 등의
  결과)를 그리는 `projectFunctionCalls()`의 else 분기는 `calls` 엣지만
  그리고 `contains`/`implements`/`exposes`/`http_calls`/`changed_by`/
  `documented_by` 엣지는 전부 버림 — 그리고 flow 분기와 달리 "엣지가 하나도
  없는 노드"를 걸러내지도 않음. 그래서 COMMIT/CLASS처럼 calls가 아닌
  관계로만 연결된 노드는 이 경로를 타는 한 앞으로도 화면에 붕 떠 보일 것.
  이건 위 0-18에서 이미 "범위 밖"으로 남긴 `shallow_neighborhood`의 산만함
  문제와 같은 뿌리라서, 어떤 관계 타입까지 화면에 보여줄지는 디자인 판단이
  필요해 이번엔 안 건드림 — 필요하면 별도로 논의.

---

## 1. 지금 코드 상태 (이미 되어 있는 것 / 안 되어 있는 것)

- **Phase 1(배관) 완료**: `app/ai/rag/state.py`(QAState 스키마), `app/ai/rag/pipeline.py`(`build_graph()`, `run_qa_pipeline()`) 둘 다 실제로 짜여 있고, `scripts/check_pipeline_skeleton.py`로 그래프 흐름(병렬 분기 → join → 조건부 재시도 루프)이 정상 동작함을 이미 검증함. **이 두 파일은 건드릴 필요 없음** — 그대로 재사용.
- 내가 채울 노드 파일들(`question_analyzer.py`, `entity_resolver.py`, `vector_retriever.py`, `graph_retriever.py`, `evidence_fusion.py`, `evidence_validator.py`)은 전부 `NotImplementedError`만 던지는 스텁. docstring에 구현 메모가 이미 상세히 적혀 있음 — 코드 짤 때 그 docstring 그대로 따라가면 됨.
- **인프라 블로커 (2026-08-16 기준, 아직 안 풀렸을 수 있음 — 먼저 확인)**:
  - pgvector `CREATE EXTENSION`이 `team2db`에서 `azure_pg_admin` 권한 필요로 막혀 있음 → 실 데이터 벡터 검색 테스트 불가
  - Neo4j 실제 접속 정보(`.env`의 `NEO4J_URI`가 로컬 `neo4j://localhost:7687`로 되어 있는데 공유 서버 주소여야 할 가능성) 미확인
  - 이 두 개는 **내가 직접 풀 수 있는 게 아닐 수 있음**(관리자 조치/팀 확인 필요) — 로직 구현 자체는 이것과 무관하게 먼저 진행 가능하니 막혀 있어도 3~7번 순서대로 코드는 계속 짜면 됨.

---

## 2. 순서 제안 (의존성 기준 — 이 순서대로 하면 막히지 않음)

기존 체크리스트(Phase 2~3)와 같은 순서지만, 내 파트만 뽑아서 더 촘촘하게 나눔.

### Step 1 — `CodeChunkRepository`에 유사도 검색 메서드 추가 ✅ 완료 (mock 검증 완료)

파일: `app/repositories/code_chunk.py`

지금 이 클래스엔 저장(`upsert_chunks`)만 있고 조회가 없음. 아래 메서드를
새로 추가:

```python
def search_similar(
    self,
    query_embedding: list[float],
    github_repository_id: int,
    top_k: int = 5,
) -> list[CodeChunk]:
    """pgvector 코사인 거리(<=>) 기준 top-k 유사 청크 조회."""
    statement = (
        select(CodeChunk)
        .where(CodeChunk.github_repository_id == github_repository_id)
        .order_by(CodeChunk.embedding.cosine_distance(query_embedding))
        .limit(top_k)
    )
    return list(self._session.scalars(statement))
```

- `pgvector.sqlalchemy.Vector` 컬럼은 `.cosine_distance()` / `.l2_distance()` 등의
  헬퍼를 지원함(이미 `Vector(1536)`으로 매핑되어 있으니 바로 씀).
- DB 연결/pgvector 확장이 아직 안 풀렸어도 이 메서드는 코드로만 작성 가능 —
  실제 실행 검증만 나중으로 미루면 됨.
- 단위 테스트는 `tests/` 아래 기존 `code_chunk` 관련 테스트 있는지 확인하고
  같은 패턴으로 추가(세션 mock 또는 sqlite 테스트 DB — 단, sqlite는 pgvector
  타입을 지원 안 하니 이 메서드 자체의 단위 테스트는 Postgres 대상으로만
  의미 있을 수 있음. 통합 테스트 성격으로 분류할 것).

### Step 2 — `vector_retriever.py` 구현 ✅ 완료 (mock 검증 완료) — ⚠️ 2026-08-22: `method_node_id` 반영 필요, 0-2 참고

파일: `app/ai/rag/nodes/vector_retriever.py`

기존 패턴은 `app/api/v1/embeddings.py`의 `get_embedding_service()`와
`app/services/chunk_import.py`를 그대로 참고하면 됨(이 프로젝트는 별도
DI 프레임워크 없이, 매 호출 시점에 Flask `current_app.config`로 클라이언트를
직접 만드는 패턴을 씀):

```python
from flask import current_app

from app.ai.rag.state import QAState
from app.clients.azure_openai import create_azure_openai_client
from app.extensions import db
from app.repositories.code_chunk import CodeChunkRepository
from app.services.embedding import EmbeddingService

TOP_K = 5


def search_vector_evidence(state: QAState) -> dict:
    deployment = current_app.config["AZURE_OPENAI_EMBEDDING_DEPLOYMENT"]
    client = create_azure_openai_client(current_app.config)
    embedding_service = EmbeddingService(client, deployment)

    query_embedding = embedding_service.embed(state["question"])

    repository = CodeChunkRepository(db.session)
    hits = repository.search_similar(
        query_embedding, state["github_repository_id"], top_k=TOP_K
    )

    return {
        "vector_results": [
            {
                "graph_node_id": hit.graph_node_id,
                "text": hit.text,
                "similarity": 0.0,  # 필요하면 search_similar가 distance도 같이 반환하도록 확장
                "path": hit.path,
                "class_name": hit.class_name,
                "method_name": hit.method_name,
                "commit_hash": hit.commit_hash,
            }
            for hit in hits
        ]
    }
```

- 반환값은 **state 전체가 아니라 자기 책임 필드만 담은 dict**여야 함 —
  `check_pipeline_skeleton.py`의 더미 노드들이 이미 그 패턴으로 되어 있으니
  그대로 따라가면 됨(LangGraph가 알아서 병합).
- `similarity`가 실제로 필요하면 `search_similar`가 `(CodeChunk, distance)` 튜플을
  반환하도록 Step 1을 살짝 바꿔도 됨 — `evidence_validator`가 신뢰도 판단에
  쓸 수 있어서 있는 게 좋음.
- pgvector가 아직 안 열려 있으면 이 함수는 짜놓고 실행은 나중에 — 대신
  `tests/`에 repository를 mock으로 갈아끼우는 단위 테스트를 만들어서 로직만
  먼저 검증하는 걸 추천.

### Step 3 — Neo4j 탐색 Cypher 쿼리 작성 + `graph_retriever.py` 구현 ✅ 완료 (mock 검증 완료) — ⚠️ 2026-08-22: 4개 함수 전부 재작성 필요, 0-2 참고

새 파일: `app/graph/queries/traversal.py` (지금 `app/graph/queries/`엔
`.gitkeep`만 있음)

`question_kind`별로 함수 4개:

```python
from app.clients.neo4j import Neo4jClient


def calls_forward(client: Neo4jClient, start_node_id: str, depth: int = 3) -> dict:
    """flow: CALLS 관계를 depth까지 순방향 탐색."""
    query = f"""
    MATCH path = (start {{key: $start_node_id}})-[:CALLS*1..{depth}]->(end)
    RETURN path
    """
    result = client.execute_query(query, {"start_node_id": start_node_id})
    return _to_graph_dict(result)


def calls_backward(client: Neo4jClient, start_node_id: str, depth: int = 3) -> dict:
    """impact: CALLS 역방향 — 누가 이 메서드를 호출하는지."""
    ...


def shallow_neighborhood(client: Neo4jClient, start_node_id: str, depth: int = 2) -> dict:
    """location: 얕은 depth만."""
    ...


def changed_by_history(client: Neo4jClient, start_node_id: str) -> dict:
    """intent: CHANGED_BY -> REFERENCES/RESOLVES -> Issue.
    ⚠️ CHANGED_BY 엣지가 아직 그래프에 없음 — Phase 5(별도 배치 작업) 완료
    전까지는 빈 결과만 반환하도록 방어적으로 구현해둘 것.
    """
    ...
```

- `depth`를 f-string으로 Cypher 안에 직접 넣는 건 가변 길이 경로(`*1..N`)를
  파라미터 바인딩으로 못 넣는 Cypher 특성상 불가피함 — 대신 `depth`는
  **사용자 입력이 아니라 코드 상수**이므로 인젝션 위험 없음(question 텍스트를
  절대 여기 직접 넣지 말 것).
- `Neo4jClient.execute_query()`는 이미 있음(`app/clients/neo4j.py`) — 새로
  만들 필요 없이 그대로 씀.
- 결과를 `app/dtos/chat.py`의 `GraphData`(nodes/edges) 형태와 호환되게 변환하는
  `_to_graph_dict()` 헬퍼도 이 파일에 같이 둘 것 — Neo4j 드라이버가 주는
  `Record`/`Path` 객체를 dict로 변환하는 로직.

`graph_retriever.py`:

```python
from flask import current_app

from app.ai.rag.state import QAState
from app.clients.neo4j import Neo4jClient
from app.graph.queries import traversal


def search_graph_evidence(state: QAState) -> dict:
    vector_results = state.get("vector_results", [])
    if not vector_results:
        return {"graph_results": {"nodes": [], "edges": []}}

    start_node_id = vector_results[0]["graph_node_id"]  # 가장 유사도 높은 결과를 시작점으로
    question_kind = state.get("question_kind", "location")

    with Neo4jClient.from_config(current_app.config) as client:
        if question_kind == "flow":
            result = traversal.calls_forward(client, start_node_id)
        elif question_kind == "impact":
            result = traversal.calls_backward(client, start_node_id)
        elif question_kind == "intent":
            result = traversal.changed_by_history(client, start_node_id)
        else:  # location
            result = traversal.shallow_neighborhood(client, start_node_id)

    return {"graph_results": result}
```

- **주의**: `Neo4jClient.from_config()`는 매번 새 driver를 만듦(연결 핸드셰이크
  포함). 스크립트류(`import_code_graph.py`)는 1회성이라 문제없지만, 매 API
  요청마다 이걸 새로 만드는 건 낭비임. MVP에서는 일단 이렇게 가고, 나중에
  `app/extensions.py`에 Neo4j client를 앱 전역으로 등록하는 걸 팀에 제안하는
  게 좋음(지금은 `db`/`migrate`만 등록되어 있고 Neo4j는 없음) — **이건 내
  파트 범위를 넘는 인프라 개선이라 팀과 상의 후 진행**.
- `entity_resolver`를 스킵하는 MVP 경로라면 `state["entity_candidates"]`는
  안 쓰고 `vector_results`의 `graph_node_id`만으로 시작점을 잡으면 됨(설계
  문서 4.4에 이미 그렇게 하라고 적혀 있음).

### Step 4 — `entity_resolver.py`: 일단 스킵(pass-through)으로 구현 ✅ 완료 (mock 검증 완료)

설계 문서에 "MVP엔 없어도 큰 지장 없음"이라고 명시돼 있으므로, 지금은
아래처럼 **빈 리스트를 반환하는 최소 구현**만 해두고 넘어가는 걸 추천:

```python
def resolve_entities(state: QAState) -> dict:
    return {"entity_candidates": []}
```

시간이 남으면 나중에 문자열 부분일치 매칭 정도로 보강. 지금 우선순위는
아님 — Step 2/3(실제 검색 로직)을 먼저 끝내는 게 훨씬 중요함.

### Step 5 — `evidence_fusion.py` 구현 (LLM 불필요, 순수 로직) ✅ 완료 (mock 검증 완료)

파일: `app/ai/rag/nodes/evidence_fusion.py`

```python
def fuse_evidence(state: QAState) -> dict:
    vector_results = state.get("vector_results", [])
    graph_results = state.get("graph_results", {})

    evidence = []
    for hit in vector_results:
        evidence.append({
            "id": hit["graph_node_id"],
            "type": "code",
            "title": hit.get("method_name") or hit.get("class_name") or hit["path"],
            "location": f"{hit['path']}",
            "description": hit["text"][:200],
            "excerpt": hit["text"],
        })
    # graph_results의 nodes/edges 중 근거로 쓸 만한 것도 evidence 리스트에 합류
    # (예: PR/Issue/Commit 노드가 있으면 type="commit"/"itsm"로 매핑)
    ...
    # 중복 제거: graph_node_id 기준
    seen = set()
    deduped = []
    for item in evidence:
        if item["id"] in seen:
            continue
        seen.add(item["id"])
        deduped.append(item)

    return {"evidence": deduped}
```

- `app.dtos.chat.Evidence(id, type, title, location, description, excerpt)`
  구조와 필드명을 맞추는 게 핵심 — 나중에 `response_composer`가 이걸 거의
  그대로 `Evidence(**item)`로 변환할 수 있어야 함.

### Step 6 — `evidence_validator.py` 구현 (휴리스틱으로 시작) ✅ 완료 (mock 검증 완료)

```python
from app.ai.rag.state import MAX_RETRIES, QAState


def validate_evidence_sufficiency(state: QAState) -> dict:
    evidence = state.get("evidence", [])
    retry_count = state.get("retry_count", 0) + 1

    is_sufficient = len(evidence) > 0  # 가장 단순한 휴리스틱부터

    return {"is_sufficient": is_sufficient, "retry_count": retry_count}
```

- **`retry_count`를 반드시 여기서 증가시켜야 함** — `pipeline.py`의
  `_route_after_validation()`이 이 값으로 무한 루프를 막음. 빼먹으면
  실서비스에서 무한 루프 위험.
- 휴리스틱을 "evidence 개수"보다 정교하게 하고 싶으면(예: similarity 임계값)
  Step 2에서 `similarity` 값을 실제로 채워야 여기서 쓸 수 있음 — Step 2/6이
  서로 연결되어 있으니 순서 유의.

### Step 7 — `question_analyzer.py` 구현 (LLM 호출 — LangChain 패턴, 2026-08-23 확정) ⬜ 남은 유일한 단계

원래는 `EmbeddingService`처럼 SDK를 직접 호출하는 `ChatCompletionService`를
새로 만들 계획이었는데, 팀원의 `response_composer.py`(`app/ai/answer_generator.py`)가
이미 LangChain(`ChatPromptTemplate | AzureChatOpenAI | StrOutputParser`) 방식으로
구현돼 있어서 **같은 패턴으로 통일하기로 팀과 확정함(2026-08-23)**. 별도
공용 서비스 클래스를 새로 안 만들어도 되고, `answer_generator.py` 구조를
그대로 참고해서 구현하면 됨.

제안 구현 (파일: `app/ai/question_classifier.py`, `answer_generator.py`와
동일한 패턴 — `create_azure_answer_generator()` 옆에 나란히 두는 걸 추천):

```python
from langchain_core.output_parsers import StrOutputParser
from langchain_core.prompts import ChatPromptTemplate
from langchain_openai import AzureChatOpenAI

from app.dtos.question import QuestionKind


def create_azure_question_classifier(config):
    llm = AzureChatOpenAI(
        azure_endpoint=config["AZURE_OPENAI_ENDPOINT"],
        api_key=config["AZURE_OPENAI_API_KEY"],
        azure_deployment=config["AZURE_OPENAI_NANO_DEPLOYMENT"],
        temperature=0,
    )
    prompt = ChatPromptTemplate.from_messages(
        [
            ("system", QUESTION_CLASSIFICATION_PROMPT),
            ("human", "{question}"),
        ]
    )
    return prompt | llm | StrOutputParser()
```

`question_analyzer.py`:

```python
def classify_question(state: QAState) -> dict:
    if state.get("question_kind"):
        return {}  # 프론트가 이미 넘겨줌 — 스킵

    classifier = create_azure_question_classifier(current_app.config)
    raw = classifier.invoke({"question": state["question"]})
    kind = raw.strip().lower()
    if kind not in {k.value for k in QuestionKind}:
        kind = QuestionKind.LOCATION  # 방어적 fallback

    return {"question_kind": QuestionKind(kind)}
```

- `app/ai/generation/prompts.py`의 `QUESTION_CLASSIFICATION_PROMPT`도 이때
  같이 채워야 함 — "intent/impact/location/flow 중 정확히 하나만, 다른 말
  없이 그 단어만 출력하라"는 지시를 명확히 넣을 것(파싱 안정성을 위해).
- ~~`app/config.py`에 `AZURE_OPENAI_DEPLOYMENT`/`AZURE_OPENAI_NANO_DEPLOYMENT`
  추가 필요~~ — **이미 팀원이 추가해둠**(0-4 참고), 이 단계에서 더 손댈 것
  없음.

### Step 8 — 팀원(Response Composer)에게 넘기는 계약 재확인

내 파트가 끝나는 시점의 `state`는 이 모양이어야 함:

```python
{
    "question": "...",
    "question_kind": "flow",          # Step 7
    "github_repository_id": 123,
    "evidence": [...],                 # Step 5, Evidence dto 호환
    "is_sufficient": True,             # Step 6
    "retry_count": 1,                  # Step 6
    "vector_results": [...],           # 디버깅/컨텍스트용, 참고만
    "graph_results": {...},            # GraphData 호환 — response_composer가 최종 답변의 graph 필드에 그대로 쓸 수 있음
}
```

`response_composer`는 이걸 받아서 LLM으로 `claims`/`summary`/`confidence`를
채우고, `graph`는 `state["graph_results"]`를 거의 그대로 `GraphData`로
변환하면 됨 — 이 계약을 팀원과 한 번 확인해두면 통합 단계(Phase 6)에서
어긋날 일이 없음.

---

## 3. 테스트 전략

1. **로직 단위 테스트부터**: 실 DB/Neo4j 연결 없이도 `evidence_fusion.py`,
   `evidence_validator.py`, `entity_resolver.py`(스킵 버전)는 순수 함수라
   바로 단위 테스트 가능. `tests/` 아래 기존 테스트 구조 참고해서 추가.
2. **`scripts/check_pipeline_skeleton.py` 업데이트**: 지금은 7개 노드를 전부
   monkeypatch한 더미로 돌리는 스크립트임. 내 파트 노드를 하나씩 실제 구현으로
   바꿀 때마다, 그 노드의 monkeypatch만 빼고 실제 함수를 쓰도록 스크립트를
   조금씩 고쳐가면 "배관은 그대로 두고 로직만 검증"하는 점진적 테스트가
   가능함(단, Flask app context가 필요해지므로 `with app.app_context():`로
   감싸야 함 — 지금 스크립트엔 없음, 추가 필요).
3. **인프라 블로커 풀리면**: `scripts/import_chunks.py` 재실행(체크리스트
   Phase 0)으로 실 데이터 적재 → `vector_retriever.py`를 실제 질문으로 호출해서
   top-k가 그럴듯한지 육안 확인 → `graph_retriever.py`도 동일하게.
4. **end-to-end**: `app/api/v1/chat.py`는 아직 mock을 쓰고 있어서(Phase 6,
   내 파트 밖) 내 파트만으로는 API 레벨 테스트는 안 됨. 대신
   `run_qa_pipeline()`을 직접 파이썬 셸/스크립트에서 호출해서 `state["evidence"]`
   까지 잘 나오는지 확인하는 걸로 충분함.

---

## 4. 우선순위 요약 (시간 없을 때 이 순서로 쳐내기)

**(2026-08-22 갱신 — 0-2 참고, 지금 시점 최신 순서는 이쪽)**

1. rebase 마무리(`git rebase --continue`)
2. Step 2/3 버그 수정 — `method_node_id` 반영, `calls_backward` 빈 결과 버그
   수정 (mock 재검증)
3. `changed_by_history` 재작성 — `CHANGED_BY` 배치 없이 기존
   `HAS_VERSION`/`INTRODUCED_IN`/`DELETED_IN`으로 바로 구현
4. ~~Step 7 (질문 분류)~~ (2026-08-23: 구현 완료 + 전체 파이프라인 실 데이터
   테스트까지 통과, 0-7 참고 — **내 파트 전체(Step 1~7) 완료**)
5. `scripts/link_changed_by.py`는 보류(당장 손 안 댐, 그래프 담당자 승인 필요)

<details>
<summary>2026-08-19 시점 원래 우선순위(참고용, 접어둠)</summary>

1. Step 1~2 (벡터 검색) — 이미 데이터 적재 로직은 완성돼 있어서 가장 빨리
   실제 결과를 볼 수 있는 경로
2. Step 5~6 (근거 통합/검증) — LLM/외부 인프라 의존 없는 순수 로직이라
   막힐 일이 없음
3. Step 3 (그래프 탐색) — Neo4j 연결 확인되는 대로
4. Step 4 (entity resolver) — pass-through로 최소 구현만 해도 무방
5. Step 7 (질문 분류) — 팀원과 `ChatCompletionService` 조율 먼저 필요해서 가장
   나중이어도 됨(question_kind는 프론트가 넘겨줄 수도 있어서 급하지 않음 —
   `ChatRequest.question_kind`가 오면 이 노드는 사실상 스킵되는 경로가 이미
   있음)

</details>

---

## 5. 협의/확인이 필요한 항목 (혼자 결정하지 말고 팀에 확인)

- ~~`ChatCompletionService`를 내가 만들지, response_composer 담당자가 만들지~~
  (2026-08-23 해결: LangChain 패턴으로 통일하기로 확정, 0-5 참고 — 더 이상
  협의 필요 없음)
- ~~intent/impact 질문에서 `CHANGE_HISTORY`/`DEPENDENCY` 시각화 빌더가 아직
  없어서 `visualization`이 항상 `None`으로 나옴~~ (2026-08-24 해결: `/chat` 연결
  풀 받은 뒤 확인 — `QAResponseAdapter._graph_from()`이 `visualization`이
  `None`이면 `state["graph_results"]`로 폴백해서 최소한의 그래프 데이터는
  응답에 실림. 0-8 참고. 전용 빌더 자체는 여전히 CALL_FLOW만 있음, 폴백으로
  당장 급한 불은 꺼진 상태)
- **(신규, 0-7)** `changed_by_history` 그래프 쿼리가 찾는 `DELETED_IN` 관계가
  현재 Neo4j에 하나도 없음(경고만 뜨고 에러는 아님) — 그래프 담당자에게 의도된
  상태인지 확인 필요
- ~~`evidence_fusion.py`의 `state["evidence"]`가 어디서도 안 읽힘~~ (2026-08-24
  해결: 새로 생긴 `app/adapters/qa_response_adapter.py`(`QAResponseAdapter`)가
  `state["evidence"]`를 읽어서 `ChatResponseData.evidence`/`confidence`/
  `claims.evidenceIds`를 채움 — 더 이상 죽은 코드 아님. 0-8 참고)
- ~~최종 응답 DTO(`QueryResponse`)에 구조화된 근거 목록이 빠진 것~~ (2026-08-24
  해결: `QAResponseAdapter`가 `QueryResponse`(answer/intent/visualization)를
  프론트용 `ChatResponseData`(summary/claims/evidence/confidence/graph/
  uncertainties/suggestedQuestions)로 변환해서 채움 — `app/dtos/chat.py`
  참고, 0-8 참고)
- ~~세션 ↔ 레포 매핑이 아직 없어서...~~ (2026-08-23 rebase로 팀원이 `ChatSession`/`ChatMessage`
  모델 + `app/api/v1/sessions.py`(세션 생성/조회) 구현해서 들어옴 — **단, 이 API의
  `repo_id`는 `github_repository_id`(int)가 아니라 내부 Postgres `Repository.id`
  (UUID)임.** 나중에 실제 "질문 보내기" API(`/chat`, 아직 mock)가 이 세션 위에
  만들어질 때 `run_qa_pipeline()`에 넘길 `github_repository_id`를 얻으려면
  `ChatSession.repository_id`(UUID)로 `Repository`를 한 번 더 조회해서
  `github_repository_id`를 꺼내야 함 — 내 코드 변경 사항은 없음, `/chat` 담당자가
  알아야 할 연결고리라 기록만 해둠
- Neo4j client를 앱 전역 리소스로 등록할지(현재 `app/extensions.py`엔 없음) — 인프라 개선이라 별도 논의
- ~~`CHANGED_BY` 엣지(Method↔Commit)는 그래프 담당자 별도 작업이었는데...~~
  (2026-08-22: 0-2 참고 — `HAS_VERSION`/`INTRODUCED_IN`/`DELETED_IN`으로 대체
  가능해져서 더 이상 그래프 담당자 승인이 급하게 필요하지 않음)
- Postgres에 Method↔Commit 연관 테이블을 별도로 두기로 한 논의가 있었는지 —
  우선순위 낮아짐(위와 같은 이유)
- **(신규, 2026-08-22)** `docs/langgraph_pipeline.md` L97-100이 "Method 노드의
  start_line/end_line"이라고 되어 있는데 실제로는 MethodVersion으로 이동함 —
  그래프 스키마 소유자에게 문서 업데이트 확인 필요
- **(신규, 2026-08-22)** `search_similar()`가 같은 method에 대해 여러 버전
  row를 중복 반환할 가능성 — `chunk_import.py` 담당자에게 재임포트 시 과거
  버전 정리 정책 확인 필요

---

## 6. Definition of Done (내 파트 기준)

- [x] `CodeChunkRepository.search_similar()` 추가 — mock 검증 완료, 실 데이터 검증은 pgvector 열리면
- [x] `app/graph/queries/traversal.py` 4개 탐색 함수 작성 — mock 검증 완료(⚠️ 2026-08-22: MethodVersion 스키마 반영 위해 재작성 필요, 0-2 참고)
- [x] `vector_retriever.py` / `graph_retriever.py` / `entity_resolver.py` / `evidence_fusion.py` / `evidence_validator.py` 전부 `NotImplementedError` 제거
- [x] **(신규)** `method_node_id` 반영 + `calls_backward` 버그 수정 + `changed_by_history` 재작성 — mock 검증 완료(0-2 참고), 실 데이터 검증은 0-3 가이드대로
- [ ] `question_analyzer.py` + `ChatCompletionService` + `QUESTION_CLASSIFICATION_PROMPT` 구현
- [ ] `app/config.py`에 `AZURE_OPENAI_DEPLOYMENT`/`AZURE_OPENAI_NANO_DEPLOYMENT` 추가 (Step 7과 같이 진행)
- [ ] `run_qa_pipeline()`을 직접 호출해서 `state["evidence"]`/`question_kind`/`is_sufficient`가 팀원과 합의한 형태로 채워지는지 확인 (Step 7 끝난 뒤)
- [ ] `docs/langgraph_pipeline_checklist.md`의 해당 항목(Phase 2, Phase 3 일부)에 체크 반영
- [x] (추가, 보류) CHANGED_BY 배치 작업 구현 — 실행 불필요해짐(0-2 참고), 코드는 남겨둠

---

## 7. CHANGED_BY 배치 작업 (추가 구현, 원래 계획엔 없었음) — ⚠️ 2026-08-22: 우선순위 낮음, 0-2 참고

> **업데이트(2026-08-22)**: 팀원이 머지한 MethodVersion 스키마
> (`HAS_VERSION`/`INTRODUCED_IN`/`DELETED_IN`)가 이 배치 작업의 목적을 이미
> 충족함. 아래 내용은 실행하지 않고 보류. 코드는 무해하게 남겨두되(아무 데도
> 안 걸려 있음), 되살릴 경우 `_methods_in_file()`의 줄 번호 조회 부분을
> `Method` 대신 `MethodVersion.startLine`/`endLine`로 고쳐야 함.

2026-08-19에 Step 3를 진행하다가 나온 파생 작업. `intent` 질문 유형이 쓸
Method↔Commit 연결을 만드는 배치 스크립트를 별도로 구현함.

**배경**: 코드 그래프와 GitHub 이력 그래프가 `file_key()`로 File 노드를
공유해서 `(Commit)-[:CHANGED]->(File)-[:DECLARES]->(Class)-[:CONTAINS]->(Method)`
경로는 이미 있음(파일 단위, 부정확). Postgres `commit_file_change_hunks`에
커밋별 정확한 변경 줄 범위(`new_start_line`/`new_line_count`)가 이미 있으니,
이걸 Method의 `start_line`/`end_line`과 겹침 비교해서 메서드 단위로 정밀하게
직결하는 `CHANGED_BY` 관계를 추가하는 게 목적.

**구현한 파일**:
- `app/repositories/commit_file_change.py` — `list_for_repository()` 추가(레포의
  모든 커밋 파일 변경 이력 + hunks 조회, 읽기 전용). 기존 `upsert_changes`/`_find`는
  안 건드림.
- `app/graph/repositories/code_graph.py` — `link_changed_by()` 추가. 기존
  `save()`/`ALLOWED_RELATIONSHIP_TYPES` 검증 로직은 안 건드림(CHANGED_BY는
  의도적으로 그 목록에 안 넣음 — 별도 상수 `CHANGED_BY_RELATIONSHIP_TYPE`).
  `MATCH`로 기존 Method/Commit 노드가 실제로 있을 때만 관계 생성(새 노드 안
  만듦), `MERGE`라 재실행해도 안전.
- `scripts/link_changed_by.py` (신규) — 실행 스크립트. `--dry-run` 플래그로
  실제 쓰기 전에 몇 건 나올지 미리 확인 가능.

**⚠️ 어디에도 연결 안 함**: 파이프라인(`app/ai/rag/*`), `qa_service.py`, 다른
임포트 스크립트 전부 이 코드를 모름.

**실행 전 확인 필요 (지금은 실행 계획 자체가 보류 상태)**:
1. `scripts/import_github_history.py`가 대상 레포에 대해 실행돼서 Commit
   노드가 그래프에 있는지
2. `python scripts/link_changed_by.py --github-repository-id <ID> --dry-run`으로
   몇 건 나오는지 먼저 확인
3. **그래프 담당자에게 알리고 승인받은 뒤에만** `--dry-run` 없이 실제 실행
   (공유 Neo4j에 새 관계 타입을 써넣는 작업이라서)
4. Postgres에 별도 연관 테이블이 필요하다는 논의가 있었는지 팀에 재확인 —
   있었다면 이 배치 스크립트가 Neo4j 엣지 외에 그 테이블에도 써야 함(현재는
   Neo4j 엣지만 씀)
