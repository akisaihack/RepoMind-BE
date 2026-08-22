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

### 3단계 — 남은 것

- 위 테스트 다 정상이면 Step 1~6은 실 데이터 기준으로도 완료로 확정
- Step 7(`question_analyzer.py`)만 남음 — 이건 별도로 진행(팀원과
  `ChatCompletionService` 먼저 조율)
- `scripts/link_changed_by.py`는 계속 보류(0-2 참고, 지금은 불필요)

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

### Step 7 — `question_analyzer.py` 구현 (LLM 호출 필요 — 공용 서비스 신규 작성) ⬜ 남은 유일한 단계

가장 마지막에 하는 이유: `EmbeddingService`에 대응하는 `ChatCompletionService`
같은 게 아직 없어서(설계 문서 2.4 참고) 새로 만들어야 함. **이 서비스는
`response_composer.py`(팀원 파트)도 필요로 하는 공용 자원** — 먼저 만드는
사람이 만들고 인터페이스를 공유하는 게 나음. 중복 구현 방지를 위해
**팀원과 먼저 짧게 맞추고 시작할 것**(누가 만들지, 시그니처는 어떻게 할지).

제안 시그니처 (파일: `app/services/chat_completion.py`, `EmbeddingService`와
동일한 클래스 패턴):

```python
class ChatCompletionService:
    def __init__(self, client: AzureOpenAI, deployment: str) -> None:
        ...

    def complete(self, system_prompt: str, user_message: str) -> str:
        response = self._client.chat.completions.create(
            model=self._deployment,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_message},
            ],
            temperature=0,
        )
        return response.choices[0].message.content
```

`question_analyzer.py`:

```python
def classify_question(state: QAState) -> dict:
    if state.get("question_kind"):
        return {}  # 프론트가 이미 넘겨줌 — 스킵

    deployment = current_app.config["AZURE_OPENAI_NANO_DEPLOYMENT"]
    client = create_azure_openai_client(current_app.config)
    service = ChatCompletionService(client, deployment)

    raw = service.complete(QUESTION_CLASSIFICATION_PROMPT, state["question"])
    kind = raw.strip().lower()
    if kind not in {"intent", "impact", "location", "flow"}:
        kind = "location"  # 방어적 fallback

    return {"question_kind": kind}
```

- `app/ai/generation/prompts.py`의 `QUESTION_CLASSIFICATION_PROMPT`도 이때
  같이 채워야 함 — "intent/impact/location/flow 중 정확히 하나만, 다른 말
  없이 그 단어만 출력하라"는 지시를 명확히 넣을 것(파싱 안정성을 위해).
- **⚠️ 놓치기 쉬운 부분**: `app/config.py`의 `BaseConfig`에 지금
  `AZURE_OPENAI_EMBEDDING_DEPLOYMENT`만 등록되어 있고
  `AZURE_OPENAI_DEPLOYMENT`/`AZURE_OPENAI_NANO_DEPLOYMENT`는 **없음**. `.env`에
  값이 있어도 `current_app.config.get("AZURE_OPENAI_NANO_DEPLOYMENT")`가
  `None`을 반환함 — Flask의 `app.config.from_object()`는 Config 클래스에
  명시된 속성만 가져오기 때문. 아래 두 줄을 `BaseConfig`에 추가해야 함:
  ```python
  AZURE_OPENAI_DEPLOYMENT = os.getenv("AZURE_OPENAI_DEPLOYMENT")
  AZURE_OPENAI_NANO_DEPLOYMENT = os.getenv("AZURE_OPENAI_NANO_DEPLOYMENT")
  ```

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
4. Step 7 (질문 분류) — 팀원과 `ChatCompletionService` 조율 먼저 필요
5. `scripts/link_changed_by.py`는 보류(당장 손 안 댐)

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

- `ChatCompletionService`를 내가 만들지, response_composer 담당자가 만들지 — 중복 구현 방지
- 세션 ↔ 레포 매핑(`SessionCreateRequest.repo_id` → `github_repository_id`)이 아직 없어서, 지금은 `run_qa_pipeline()`을 테스트할 때 `github_repository_id`를 하드코딩해서 넘겨야 함 — 이건 `qa_service.py` 담당자(팀원 or 별도 담당) 몫이지만 내 노드들의 입력값이라 진행 상황 공유는 필요
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
