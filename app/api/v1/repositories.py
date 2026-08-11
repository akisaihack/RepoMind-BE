"""Repository management API endpoints."""

from dataclasses import asdict

from flask import Blueprint, jsonify, request

from app.dtos.repositories import RepositoryCreateRequest
from app.sample.mock_repositories import (
    get_mock_repository_creation_status,
    get_mock_repository_list,
    get_mock_repository_status,
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
    _ = RepositoryCreateRequest(
        repository_url=data.get("repository_url", ""),
        branch=data.get("branch", "main")
    )
    
    # TODO: 실제 GitHub 연동 및 백그라운드 파이프라인 트리거 로직 추가 예정
    response_data = get_mock_repository_creation_status()
    
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
    response_data = get_mock_repository_status(repo_id)
    
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
    response_data = get_mock_repository_list()
    
    return jsonify({
        "success": True,
        "data": asdict(response_data)
    }), 200
