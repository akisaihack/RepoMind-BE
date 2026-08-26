"""검색 후보와 사용자용 답변 근거 분리 테스트."""

from app.ai.rag.nodes.evidence_fusion import _code_location, fuse_evidence


def _hit(
    method: str,
    *,
    graph_node_id: str | None = None,
    method_node_id: str | None = None,
    path: str = "src/AuthController.java",
    text: str | None = None,
    param_signature: str = "()",
) -> dict:
    return {
        "graph_node_id": graph_node_id or f"version:{method}",
        "method_node_id": method_node_id or f"method:{method}",
        "text": text or f"void {method}() {{}}",
        "similarity": 0.9,
        "path": path,
        "class_name": "AuthController",
        "method_name": method,
        "param_signature": param_signature,
        "start_line": 10,
        "end_line": 20,
        "api_http_method": None,
        "api_path": None,
        "commit_hash": "abc123",
    }


def test_keeps_selected_and_graph_connected_code_but_excludes_search_only_candidates() -> None:
    authenticate = _hit("authenticateUser")
    generate_token = _hit("generateToken", method_node_id="method:generateToken")
    register = _hit("registerUser")
    state = {
        "question": "로그인 호출 흐름",
        "github_repository_id": 1,
        "question_kind": "flow",
        "vector_results": [register, authenticate, generate_token],
        "selected_target": {
            "graph_node_id": "version:authenticateUser",
            "method_node_id": "method:authenticateUser",
        },
        "graph_results": {
            "nodes": [
                {
                    "id": "version:authenticateUser",
                    "type": "symbol",
                    "label": "코드 버전 (L10-20)",
                },
                {
                    "id": "method:generateToken",
                    "type": "symbol",
                    "label": "JwtTokenProvider.generateToken",
                },
                {
                    "id": "method:getId",
                    "type": "symbol",
                    "label": "UserPrincipal.getId",
                },
            ],
            "edges": [],
        },
    }

    result = fuse_evidence(state)["evidence"]

    assert [item["title"] for item in result] == [
        "AuthController.authenticateUser()",
        "AuthController.generateToken()",
    ]
    assert result[0]["location"] == "src/AuthController.java · Line 10"
    assert all("registerUser" not in item["title"] for item in result)
    assert all(item["title"] != "코드 버전 (L10-20)" for item in result)
    assert all(item["title"] != "UserPrincipal.getId" for item in result)
    assert all(item["id"].startswith("evidence:code:") for item in result)
    assert all("version:" not in item["id"] for item in result)


def test_merges_method_version_into_user_friendly_history_code_evidence() -> None:
    method_key = (
        "123:class:src/AuthController.java:com.example.AuthController:"
        "method:authenticateUser:(LoginRequest)"
    )
    state = {
        "question": "authenticateUser 변경 이력",
        "github_repository_id": 123,
        "question_kind": "intent",
        "vector_results": [],
        "selected_target": {"method_node_id": method_key},
        "graph_results": {
            "nodes": [
                {
                    "id": method_key,
                    "type": "symbol",
                    "label": "AuthController.authenticateUser",
                    "metadata": {},
                },
                {
                    "id": "version:authenticate",
                    "type": "symbol",
                    "label": "코드 버전 (L23-36)",
                    "detail": method_key,
                    "metadata": {
                        "node_type": "MethodVersion",
                        "method_key": method_key,
                        "source_code": "String jwt = generateToken(authentication);",
                        "start_line": 23,
                        "end_line": 36,
                        "content_hash": "content-hash",
                    },
                },
                {
                    "id": "commit:abc123",
                    "type": "commit",
                    "label": "abc12345",
                    "metadata": {
                        "node_type": "Commit",
                        "sha": "abc123456789",
                        "message": "feat: JWT 로그인 추가",
                        "author": "Developer",
                        "committed_at": "2026-08-01T11:00:00Z",
                    },
                },
            ],
            "edges": [],
        },
    }

    result = fuse_evidence(state)["evidence"]

    assert [item["id"].split(":")[:2] for item in result] == [
        ["evidence", "code"],
        ["evidence", "commit"],
    ]
    code_evidence, commit_evidence = result
    assert code_evidence["title"] == "AuthController.authenticateUser(LoginRequest)"
    assert code_evidence["location"] == "src/AuthController.java · Line 23"
    assert code_evidence["excerpt"] == "String jwt = generateToken(authentication);"
    assert code_evidence["startLine"] == 23
    assert code_evidence["endLine"] == 36
    assert code_evidence["excerptStartLine"] == 23
    assert code_evidence["excerptEndLine"] == 23
    assert not code_evidence["hasMoreBefore"]
    assert not code_evidence["hasMoreAfter"]
    assert {key: value for key, value in commit_evidence.items() if key != "id"} == {
        "type": "commit",
        "title": "feat: JWT 로그인 추가",
        "location": "abc123456789",
        "description": "Developer · 2026-08-01T11:00:00Z",
        "excerpt": None,
    }


def test_deduplicates_vector_and_history_version_by_stable_id() -> None:
    hit = _hit("authenticateUser", graph_node_id="version:authenticate")
    state = {
        "question": "변경 이력",
        "github_repository_id": 1,
        "question_kind": "intent",
        "vector_results": [hit],
        "selected_target": {
            "graph_node_id": "version:authenticate",
            "method_node_id": "method:authenticateUser",
        },
        "graph_results": {
            "nodes": [
                {
                    "id": "version:authenticate",
                    "metadata": {
                        "node_type": "MethodVersion",
                        "method_key": (
                            "1:class:src/AuthController.java:com.example.AuthController:"
                            "method:authenticateUser:()"
                        ),
                        "source_code": "void authenticateUser() {}",
                        "start_line": 10,
                        "end_line": 20,
                    },
                }
            ],
            "edges": [],
        },
    }

    result = fuse_evidence(state)["evidence"]

    assert len(result) == 1
    assert result[0]["title"] == "AuthController.authenticateUser()"


def test_exposes_pull_request_and_issue_as_intent_evidence() -> None:
    state = {
        "question": "왜 중복 투표 검증을 추가했어?",
        "github_repository_id": 1,
        "question_kind": "intent",
        "vector_results": [],
        "graph_results": {
            "nodes": [
                {
                    "id": "pr:42",
                    "metadata": {
                        "node_type": "PullRequest",
                        "number": 42,
                        "title": "중복 투표 방지",
                        "body": "동일 사용자의 두 번째 투표를 거부합니다.",
                        "state": "closed",
                        "url": "https://github.com/org/repo/pull/42",
                    },
                },
                {
                    "id": "issue:35",
                    "metadata": {
                        "node_type": "Issue",
                        "number": 35,
                        "title": "중복 투표 허용 문제",
                        "body": "한 사용자가 여러 번 투표할 수 있습니다.",
                        "state": "closed",
                        "url": "https://github.com/org/repo/issues/35",
                        "labels": ["bug"],
                    },
                },
            ],
            "edges": [
                {"source": "pr:42", "target": "issue:35", "type": "REFERENCES"},
                {"source": "pr:42", "target": "issue:35", "type": "RESOLVES"},
            ],
        },
    }

    result = fuse_evidence(state)["evidence"]

    assert [item["type"] for item in result] == ["itsm", "itsm"]
    assert result[0]["title"] == "Pull Request #42: 중복 투표 방지"
    assert result[0]["excerpt"] == "동일 사용자의 두 번째 투표를 거부합니다."
    assert result[1]["title"] == "Issue #35: 중복 투표 허용 문제"
    assert result[1]["description"] == "해결한 이슈 · closed"


def test_formats_single_source_line_without_a_range() -> None:
    assert _code_location("src/User.java", 93, 93) == "src/User.java · Line 93"


def test_removes_embedding_metadata_and_limits_a_long_method_to_relevant_lines() -> None:
    source_lines = [
        "// package: com.example",
        "// class: AuthController",
        "// method: authenticateUser(LoginRequest)",
        "void authenticateUser(LoginRequest request) {",
    ]
    source_lines.extend(f"    step{number}();" for number in range(1, 24))
    source_lines.extend(
        [
            "    validateCredentials(request);",
            "    issueAccessToken();",
            *[f"    afterStep{number}();" for number in range(1, 26)],
            "}",
        ]
    )
    hit = _hit(
        "authenticateUser",
        text="\n".join(source_lines),
        param_signature="(LoginRequest)",
    )
    state = {
        "question": "validateCredentials 호출은 어디서 해?",
        "github_repository_id": 1,
        "question_kind": "location",
        "vector_results": [hit],
        "selected_target": {"graph_node_id": hit["graph_node_id"]},
        "graph_results": {"nodes": [], "edges": []},
    }

    evidence = fuse_evidence(state)["evidence"][0]

    assert evidence["title"] == "AuthController.authenticateUser(LoginRequest)"
    assert "// package:" not in evidence["excerpt"]
    assert "// class:" not in evidence["excerpt"]
    assert "// method:" not in evidence["excerpt"]
    assert "validateCredentials(request);" in evidence["excerpt"]
    assert evidence["fullExcerpt"].endswith("}")
    assert len(evidence["excerpt"].splitlines()) == 30
    assert evidence["excerptStartLine"] == 24
    assert evidence["excerptEndLine"] == 53
    assert evidence["hasMoreBefore"]
    assert evidence["hasMoreAfter"]


def test_returns_full_source_only_for_a_user_request_for_full_code() -> None:
    source = "\n".join(f"line{number}" for number in range(40))
    hit = _hit("authenticateUser", text=source)
    state = {
        "question": "show the authenticateUser full code",
        "github_repository_id": 1,
        "question_kind": "location",
        "vector_results": [hit],
        "selected_target": {"graph_node_id": hit["graph_node_id"]},
        "graph_results": {"nodes": [], "edges": []},
    }

    evidence = fuse_evidence(state)["evidence"][0]

    assert evidence["excerpt"] == source
    assert evidence["fullExcerpt"] == source
    assert not evidence["hasMoreBefore"]
    assert not evidence["hasMoreAfter"]


def test_uses_korean_question_intent_to_find_a_relevant_code_statement() -> None:
    source_lines = ["def process():"]
    source_lines.extend(f"    preliminary_step_{number}()" for number in range(35))
    source_lines.append("    repository.upsert(record)")
    source_lines.extend(f"    final_step_{number}()" for number in range(30))
    hit = _hit("process", text="\n".join(source_lines))
    state = {
        "question": "분석 결과를 저장하는 부분은 어디야?",
        "github_repository_id": 1,
        "question_kind": "location",
        "vector_results": [hit],
        "selected_target": {"graph_node_id": hit["graph_node_id"]},
        "graph_results": {"nodes": [], "edges": []},
    }

    evidence = fuse_evidence(state)["evidence"][0]

    assert "repository.upsert(record)" in evidence["excerpt"]
    assert evidence["hasMoreBefore"]
    assert evidence["hasMoreAfter"]


def test_limits_default_flow_evidence_to_five_items() -> None:
    hits = [_hit(f"method{index}") for index in range(6)]
    state = {
        "question": "호출 흐름",
        "github_repository_id": 1,
        "question_kind": "flow",
        "vector_results": hits,
        "selected_target": {"graph_node_id": hits[0]["graph_node_id"]},
        "graph_results": {
            "nodes": [{"id": hit["graph_node_id"]} for hit in hits],
            "edges": [],
        },
    }

    evidence = fuse_evidence(state)["evidence"]

    assert len(evidence) == 5


def test_excludes_commit_without_a_message() -> None:
    state = {
        "question": "변경 이력",
        "github_repository_id": 1,
        "question_kind": "intent",
        "vector_results": [],
        "graph_results": {
            "nodes": [
                {
                    "id": "commit:empty",
                    "metadata": {"node_type": "Commit", "sha": "abc123"},
                }
            ],
            "edges": [],
        },
    }

    assert fuse_evidence(state)["evidence"] == []
