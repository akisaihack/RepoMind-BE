# LangGraph 파이프라인 구현 체크리스트

> `docs/langgraph_pipeline.md`(설계 문서)를 실행 순서대로 쪼갠 작업
> 목록. 진행하면서 체크(`[x]`)해나가면 됨. 완료 표시된 항목은 2026-08-16
> 기준으로 이미 확인/완료된 것.

---

## Phase 0 — 지금 막혀있는 인프라 블로커부터 해결

파이프라인 코드를 아무리 잘 짜도 이게 안 풀리면 실 데이터로 테스트 자체가
불가능함. 최우선.

- [ ] **pgvector `CREATE EXTENSION` 권한 요청** — `team2db`에서 `azure_pg_admin`
      권한 필요. Azure Portal에서 Server Parameters의 `azure.extensions`에
      `VECTOR` 허용 여부 확인 + 관리자 계정으로 `CREATE EXTENSION IF NOT EXISTS
      vector;` 1회 실행 요청. (담당: 인프라 관리자에게 요청)
- [ ] 확장 활성화 확인되면 `flask --app wsgi db upgrade`로 `code_chunks`
      테이블 실제 생성 확인 (pgAdmin/DBeaver에서 `team2` 스키마 아래 확인)
- [ ] `python scripts/import_chunks.py --github-repository-id 123231656 --repository-path "D:\PJ\repomind-testdata\spring-security-react-ant-design-polls-app\polling-app-server" --commit-hash 362fad90cab17e76453b3b9e273c594de6ee3d7f` 재실행해서 실제 데이터 적재 완료
- [ ] Neo4j 실제 접속 정보(호스트/포트/비밀번호) 확인 — `.env`의
      `NEO4J_URI=neo4j://localhost:7687`가 Postgres 때처럼 로컬이 아니라
      실제 공유 서버 주소여야 할 가능성 높음. Neo4j Browser(`http://호스트:7474`)로
      접속 테스트
- [ ] `python scripts/import_code_graph.py --github-repository-id 123231656 --repository-path "D:\PJ\repomind-testdata\spring-security-react-ant-design-polls-app\polling-app-server" --skip-repository-validation` 실행해서 Neo4j에 코드 그래프(Class/Method 노드 등) 실제 적재 확인

---

## Phase 1 — 파이프라인 배관(plumbing) 먼저 검증

노드 내용을 채우기 전에, 그래프 구조 자체가 맞게 연결되는지부터 확인.

- [x] `app/ai/rag/state.py` — `QAState` 스키마 작성 완료
- [x] `app/ai/rag/pipeline.py`의 `build_graph()` 실제 구현 완료
      - 노드 7개 등록, `add_edge`/`add_conditional_edges`로 설계한 흐름 그대로 연결
      - `_route_after_validation()`에 `retry_count >= MAX_RETRIES` 체크 포함(무한 루프 방지)
      - `run_qa_pipeline()`도 초기 state 구성 + `compiled.invoke()`까지 구현 완료
      - `scripts/check_pipeline_skeleton.py` 신규 작성 — nodes/*.py를 임시
        monkeypatch해서 그래프 구조만 검증하는 스크립트(nodes/*.py 본체는
        안 건드림, 여전히 NotImplementedError 상태)
- [x] `pip install -e '.[dev,postgres]'`로 `langgraph` 설치 확인,
      `python scripts/check_pipeline_skeleton.py` 실행 완료 — 두 시나리오
      모두 `response_composer`까지 정상 도달 확인(2026-08-16)
      - 시나리오1(즉시 충분): `question_analyzer -> entity_resolver ->
        graph_retriever -> vector_retriever -> evidence_fusion ->
        evidence_validator -> response_composer`, retry_count=1
      - 시나리오2(재시도 소진): validator를 두 번 거쳐 retry_count=2에서
        `MAX_RETRIES` 도달로 강제 종료 → response_composer 정상 도달
      - ⚠️ 우려했던 위험(재시도 때 graph_retriever가 안 돌아서
        evidence_fusion이 join 못 할까봐)은 실제로는 발생하지 않음 —
        LangGraph가 vector_retriever 쪽 업데이트만으로도 evidence_fusion을
        재실행시켜줌. `pipeline.py` retry 분기는 지금 구조(vector_retriever로만
        복귀) 그대로 유지, 수정 불필요

Phase 1 완료.

---

## Phase 2 — Retriever 노드가 의존하는 신규 조회 로직 먼저 작성

노드 함수 자체보다, 노드가 호출할 "저장소 조회 메서드"와 "Cypher 쿼리"가
없으면 구현이 불가능하므로 이것부터.

- [ ] `app/repositories/code_chunk.py`에 유사도 검색 메서드 추가
      (`search_similar(query_embedding, github_repository_id, top_k)`,
      pgvector `<=>` 연산자 사용)
- [ ] Neo4j 탐색 Cypher 쿼리 함수 작성 (신규 파일 예: `app/graph/queries/traversal.py`)
      - `flow` 질문용: `CALLS` depth N 순방향 탐색
      - `impact` 질문용: `CALLS` 역방향 탐색
      - `location` 질문용: depth 1~2 얕은 탐색
      - `intent` 질문용: `CHANGED_BY` → `REFERENCES`/`RESOLVES` → `Issue`
        (⚠️ Phase 5의 `CHANGED_BY` 엣지가 먼저 있어야 동작함)

---

## Phase 3 — 노드 구현 (제안 순서대로)

앞서 합의한 순서: 이미 있는 데이터로 바로 테스트 가능한 것부터.

- [ ] `nodes/vector_retriever.py` — `search_vector_evidence()` 구현
      (Phase 0 데이터 적재 + Phase 2 검색 메서드 필요)
- [ ] `nodes/graph_retriever.py` — `search_graph_evidence()` 구현
      (Phase 0 Neo4j 적재 + Phase 2 Cypher 쿼리 필요)
- [ ] `nodes/question_analyzer.py` — `classify_question()` 구현
      (독립적, LLM 호출 서비스 필요 → Phase 4 먼저 참고)
- [ ] `nodes/entity_resolver.py` — `resolve_entities()` 구현
      (우선순위 낮음, 시간 없으면 스킵하고 vector_retriever 결과만으로
      진행 가능)
- [ ] `nodes/evidence_fusion.py` — `fuse_evidence()` 구현 (LLM 불필요, 로직만)
- [ ] `nodes/evidence_validator.py` — `validate_evidence_sufficiency()` 구현
      (처음엔 휴리스틱으로 — 예: evidence 0개면 무조건 부족)
- [ ] `nodes/response_composer.py` — `compose_answer()` 구현
      (Phase 4 LLM 서비스 + `app/ai/generation/prompts.py` 프롬프트 필요)

---

## Phase 4 — LLM 호출 서비스 + 프롬프트 작성

Question Analyzer, Response Composer가 공통으로 필요로 함.

- [ ] `EmbeddingService`와 같은 패턴으로 `ChatCompletionService` 신규 작성
      (Azure OpenAI 채팅 완성 API 호출, `.env`의 `AZURE_OPENAI_DEPLOYMENT`/
      `AZURE_OPENAI_NANO_DEPLOYMENT` 사용)
- [ ] `app/ai/generation/prompts.py`의 `QUESTION_CLASSIFICATION_PROMPT` 작성
      (출력값이 `intent`/`impact`/`location`/`flow` 중 하나로 강제되게)
- [ ] `app/ai/generation/prompts.py`의 `RESPONSE_COMPOSITION_PROMPT` 작성
      (claims[].kind를 `fact`/`stated_intent`/`inference`로 구분하도록 강제,
      "근거 없으면 확정적으로 표현하지 않는다" 원칙 포함)

---

## Phase 5 — 별도 병행 작업 (그래프 데이터 보강)

파이프라인 코드는 아니지만, `intent`/`impact` 질문 유형이 동작하려면 반드시
필요한 선행 작업.

- [ ] `Symbol/Method -[:CHANGED_BY]-> Commit` 엣지 생성 배치 작업
      - PostgreSQL `commit_file_change_hunks`의 `new_start_line`/`new_line_count`와
        Neo4j Method 노드의 `start_line`/`end_line` 겹침 비교
      - 겹치면 해당 Method 노드 → Commit 노드로 `CHANGED_BY` 엣지 생성
      - (담당/파일 위치 미정 — 그래프 담당자와 상의 필요)

---

## Phase 6 — 통합 (mock 제거)

- [ ] `app/services/qa_service.py`의 `QAService.ask()` 완성
      - 세션↔레포 매핑 로직 필요 (`SessionCreateRequest.repo_id`가
        `github_repository_id`로 이어지도록 — 현재 인메모리 mock이라
        실제 연동 방식 결정 필요)
      - `run_qa_pipeline()` 호출 → `ChatResponseData`로 변환해 반환
- [ ] `app/api/v1/chat.py`의 `get_mock_chat_response()` 호출을
      `QAService().ask(session_id, req)` 호출로 교체 (mock 완전 제거)

---

## Phase 7 — 검증

- [ ] "로그인 프로세스 흐름을 알려줘" (flow) 질문으로 end-to-end 테스트
- [ ] "왜 논리 삭제로 구현했어?" 같은 intent 질문으로 테스트 (Phase 5
      완료 후에만 의미 있는 답변 가능)
- [ ] 응답이 `app/sample/mock_chat.py`의 mock 구조와 완전히 같은 형태인지
      확인 (프론트가 그대로 렌더링 가능한지)
- [ ] 근거 없는 질문에 "확정 어려움" + `uncertainties` 채워지는지 확인
      (환각 방지 원칙이 실제로 지켜지는지)
