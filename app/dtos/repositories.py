"""Data Transfer Objects for Repository Management API."""

from dataclasses import dataclass
from typing import Literal


@dataclass
class RepositoryCreateRequest:
    """
    레포지토리 분석 요청 데이터 규격.
    
    <pre>
        사용자가 분석을 원하는 GitHub 레포지토리 URL을 전달합니다.
    </pre>
    
    @param repo_url GitHub 레포지토리 URL (예: https://github.com/owner/repo)
    @param branch 기준 브랜치 (선택 사항, 기본값: main)
    """
    repo_url: str
    branch: str = "main"


@dataclass
class RepositoryStatusResponse:
    """
    레포지토리 분석 상태 응답 데이터.
    
    <pre>
        프론트엔드에서 로딩바 등을 처리하기 위해 폴링(Polling)할 때 사용됩니다.
    </pre>
    
    @param repo_id 발급된 고유 레포지토리 ID
    @param status 현재 분석 상태 (pending, indexing, completed, failed)
    @param progress_percent 분석 진행률 (0~100)
    @param file_count 분석 대상 파일 수
    """
    repo_id: str
    status: Literal["pending", "indexing", "completed", "failed"]
    progress_percent: int
    file_count: int


@dataclass
class RepositoryInfo:
    """단일 레포지토리 요약 정보."""
    repo_id: str
    name: str
    repo_url: str
    status: Literal["pending", "indexing", "completed", "failed"]


@dataclass
class RepositoryListResponse:
    """
    등록된 전체 레포지토리 목록 응답 데이터.
    
    @param repositories 레포지토리 정보 배열
    """
    repositories: list[RepositoryInfo]
