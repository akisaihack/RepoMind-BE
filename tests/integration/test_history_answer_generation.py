"""Opt-in Azure OpenAI validation for structured development-history answers."""

import os

import pytest

from app import create_app
from app.ai.answer_generator import create_azure_answer_generator
from app.dtos.response_generation import (
    QueryIntent,
    ResponseGenerationInput,
    RetrievedContext,
)

pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(
        os.getenv("RUN_LLM_INTEGRATION_TESTS") != "1",
        reason="set RUN_LLM_INTEGRATION_TESTS=1 to call configured Azure OpenAI",
    ),
]


def test_generates_grounded_history_claims_with_real_llm() -> None:
    app = create_app()
    input_data = ResponseGenerationInput(
        question="authenticateUser 메서드에 어떤 변경이 있었어?",
        intent=QueryIntent.HISTORY,
        target="AuthController.authenticateUser",
        context=RetrievedContext(
            history=[
                {
                    "method": "AuthController.authenticateUser",
                    "change_type": "modified",
                    "version": {
                        "node_id": "version:2",
                        "method_key": "method:authenticate",
                        "symbol": "AuthController.authenticateUser(LoginRequest)",
                        "source_code": "validateToken(jwt);\nauthenticate();",
                        "start_line": 20,
                        "end_line": 25,
                        "content_hash": "hash-2",
                        "evidence_id": "evidence:code:version2",
                    },
                    "commit": {
                        "node_id": "commit:2",
                        "sha": "def456",
                        "message": "fix: JWT 검증 추가",
                        "author": "Developer",
                        "committed_at": "2026-08-10T10:00:00Z",
                        "evidence_id": "evidence:commit:def456",
                    },
                    "diff": {
                        "previous_commit_sha": "abc123",
                        "previous_content_hash": "hash-1",
                        "added_lines": ["validateToken(jwt);"],
                        "removed_lines": [],
                    },
                }
            ],
            evidence=[
                {
                    "id": "evidence:code:version2",
                    "type": "code",
                    "title": "AuthController.authenticateUser(LoginRequest)",
                    "location": "AuthController.java · Line 20–25",
                    "description": "JWT 검증이 포함된 코드 버전",
                },
                {
                    "id": "evidence:commit:def456",
                    "type": "commit",
                    "title": "fix: JWT 검증 추가",
                    "location": "def456",
                    "description": "Developer · 2026-08-10T10:00:00Z",
                },
            ],
        ),
    )

    with app.app_context():
        answer = create_azure_answer_generator(app.config).generate(input_data)

    assert answer.summary.strip()
    assert answer.claims
    allowed = {"evidence:code:version2", "evidence:commit:def456"}
    assert all(set(claim.evidence_ids) <= allowed for claim in answer.claims)
