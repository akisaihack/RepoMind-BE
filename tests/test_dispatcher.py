import logging
import uuid

from app.dtos.analysis import AnalysisRequest
from app.jobs.dispatcher import NoOpAnalysisJobDispatcher


def test_noop_dispatcher_logs_info(caplog):
    dispatcher = NoOpAnalysisJobDispatcher()
    request = AnalysisRequest(
        repository_id=uuid.uuid4(),
        repository_url="https://github.com/test/repo",
        branch="main"
    )
    
    with caplog.at_level(logging.INFO):
        dispatcher.dispatch(request)
        
    assert "분석 요청을 기록했습니다. URL=https://github.com/test/repo" in caplog.text
    assert "브랜치=main" in caplog.text
