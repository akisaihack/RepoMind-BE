from app.ai.rag.nodes.evidence_validator import validate_evidence_sufficiency


def test_rejects_evidence_when_selected_target_misses_exact_symbol() -> None:
    result = validate_evidence_sufficiency(
        {
            "evidence": [{"id": "commit:1"}],
            "symbol_results": [{"method_node_id": "method:requestExport"}],
            "selected_target": {"method_node_id": "method:unrelatedTest"},
            "retry_count": 0,
        }
    )

    assert result["is_sufficient"] is False
    assert result["evidence_validation_reason"] == "explicit_symbol_mismatch"


def test_accepts_evidence_for_selected_exact_symbol() -> None:
    result = validate_evidence_sufficiency(
        {
            "evidence": [{"id": "commit:1"}],
            "symbol_results": [{"method_node_id": "method:requestExport"}],
            "selected_target": {"method_node_id": "method:requestExport"},
            "retry_count": 0,
        }
    )

    assert result["is_sufficient"] is True
    assert result["evidence_validation_reason"] is None
