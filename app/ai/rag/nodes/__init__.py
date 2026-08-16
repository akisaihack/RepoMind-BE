"""LangGraph 파이프라인의 개별 노드 함수 모음.

각 노드는 QAState(app/ai/rag/state.py)를 입력받아, 자기 책임인 필드만 채운
새 State(또는 dict)를 반환하는 순수 함수 형태로 작성한다 (LangGraph 노드
함수 규약). 노드 목록과 각 역할은 docs/langgraph_pipeline.md의 4번 섹션 참고.
"""
