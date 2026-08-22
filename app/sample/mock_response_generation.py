"""Independent mock input for response-generation development and tests."""

from app.dtos.response_generation import (
    QueryIntent,
    ResponseGenerationInput,
    RetrievedContext,
    VisualizationType,
)


def get_mock_response_generation_input() -> ResponseGenerationInput:
    repeated_relation = {
        "source": {
            "id": "method:1",
            "name": "CancelController.cancel",
            "type": "CONTROLLER",
        },
        "relation": "CALLS",
        "target": {
            "id": "method:2",
            "name": "CancelService.cancel",
            "type": "SERVICE",
        },
    }
    return ResponseGenerationInput(
        question="결제 취소 요청은 어떤 순서로 처리돼?",
        intent=QueryIntent.FLOW,
        target="CancelController.cancel",
        visualization_required=True,
        visualization_type=VisualizationType.CALL_FLOW,
        context=RetrievedContext(
            code=[{"path": "app/cancel.py", "symbol": "CancelController.cancel"}],
            graph=[
                repeated_relation,
                repeated_relation,
                {
                    "source": repeated_relation["target"],
                    "relation": "CALLS",
                    "target": {
                        "id": "method:3",
                        "name": "PaymentService.cancel",
                        "type": "SERVICE",
                    },
                },
            ],
        ),
    )


__all__ = ["get_mock_response_generation_input"]
