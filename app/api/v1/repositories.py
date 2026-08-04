"""Repository management API endpoints."""

import uuid
from flask import Blueprint, jsonify, request
from dataclasses import asdict

from app.dtos.repositories import (
    RepositoryCreateRequest,
    RepositoryStatusResponse,
    RepositoryInfo,
    RepositoryListResponse,
)

repositories_bp = Blueprint("repositories", __name__)


@repositories_bp.post("/")
def create_repository():
    """
    신규 GitHub 레포지토리 등록 및 분석 요청 처리.
    
    <pre>
        GitHub URL을 받아 백그라운드 분석 큐에 등록하고 repo_id를 반환합니다.
        (현재는 프론트엔드 연동을 위한 Mock 응답 반환)
    </pre>
    """
    data = request.get_json() or {}
    req = RepositoryCreateRequest(
        repo_url=data.get("repo_url", ""),
        branch=data.get("branch", "main")
    )
    
    # TODO: 실제 GitHub 연동 및 백그라운드 파이프라인 트리거 로직 추가 예정
    mock_repo_id = f"repo_{uuid.uuid4().hex[:8]}"
    
    response_data = RepositoryStatusResponse(
        repo_id=mock_repo_id,
        status="indexing",
        progress_percent=15,
        file_count=0
    )
    
    return jsonify({
        "success": True,
        "data": asdict(response_data)
    }), 201


@repositories_bp.get("/<repo_id>")
def get_repository_status(repo_id: str):
    """
    특정 레포지토리의 분석 진행 상태 조회 (Polling 용도).
    
    <pre>
        프론트엔드 로딩 처리를 위해 현재 진행률과 상태를 반환합니다.
        (현재는 무조건 완료(completed) 상태를 반환하도록 Mocking)
    </pre>
    """
    # TODO: 실제 DB에서 repo_id로 상태 조회 로직 추가 예정
    response_data = RepositoryStatusResponse(
        repo_id=repo_id,
        status="completed",
        progress_percent=100,
        file_count=142
    )
    
    return jsonify({
        "success": True,
        "data": asdict(response_data)
    }), 200


@repositories_bp.get("/")
def list_repositories():
    """
    분석 완료되었거나 진행 중인 레포지토리 목록 조회.
    """
    # TODO: 실제 DB에서 전체 목록 조회 로직 추가 예정
    response_data = RepositoryListResponse(
        repositories=[
            RepositoryInfo(
                repo_id="repo_example1",
                name="spring-security-react-ant-design-polls-app",
                repo_url="https://github.com/callicoder/spring-security-react-ant-design-polls-app",
                status="completed"
            )
        ]
    )
    
    return jsonify({
        "success": True,
        "data": asdict(response_data)
    }), 200
