import uuid
import logging
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
        
    assert "Dispatched analysis job for repo 'https://github.com/test/repo'" in caplog.text
    assert "branch: main" in caplog.text
