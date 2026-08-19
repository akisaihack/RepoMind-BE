import uuid
from unittest.mock import MagicMock, patch

from app.dtos.analysis import AnalysisRequest
from app.jobs.dispatcher import ThreadAnalysisJobDispatcher


def test_thread_dispatcher_dispatches(app):
    dispatcher = ThreadAnalysisJobDispatcher(app)
    request = AnalysisRequest(
        repository_id=uuid.uuid4(),
        repository_url="https://github.com/test/repo",
        branch="main",
    )
    
    with patch("threading.Thread") as mock_thread_cls:
        mock_thread = MagicMock()
        mock_thread_cls.return_value = mock_thread
        
        dispatcher.dispatch(request)
        
        mock_thread_cls.assert_called_once()
        mock_thread.start.assert_called_once()
