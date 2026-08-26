"""Mock data for Chat API."""

from app.dtos.chat import ChatResponseData, Claim, Evidence, GraphData, GraphNode, GraphEdge, Confidence

def get_mock_chat_response() -> ChatResponseData:
    """
    프론트엔드 연동 테스트를 위한 가짜(Mock) 응답 데이터를 생성.
    
    <pre>
        실제 DB(Neo4j, pgvector)나 LLM 호출 없이
        고정된 회원 탈퇴 예시(Graph, Evidence 등) 데이터를 반환함.
    </pre>
    
    @return 테스트 용도로 하드코딩된 ChatResponseData 객체
    """
    mock_nodes = [
        GraphNode(id="withdraw-api", type="api", label="DELETE /members/me", detail="MemberController.withdraw"),
        GraphNode(id="member-service", type="symbol", label="MemberService.withdraw", detail="회원 탈퇴 유스케이스"),
        GraphNode(id="member-policy", type="symbol", label="MemberPolicy.validateWithdrawal", detail="탈퇴 가능 여부 검증")
    ]
    
    mock_edges = [
        GraphEdge(id="edge-api-service", source="withdraw-api", target="member-service", type="calls", label="CALLS"),
        GraphEdge(id="edge-service-policy", source="member-service", target="member-policy", type="calls", label="CALLS")
    ]
    
    mock_evidence = [
        Evidence(
            id="member-controller", type="code", title="회원 탈퇴 API", 
            location="src/member/MemberController.java:84", 
            description="DELETE 요청을 받아 MemberService.withdraw를 호출합니다.", 
            excerpt='@DeleteMapping("/members/me")'
        ),
        Evidence(
            id="member-service", type="code", title="회원 탈퇴 처리", 
            location="src/member/MemberService.java:126", 
            description="정책 검증 후 회원의 deletedAt을 갱신합니다."
        )
    ]
    
    mock_claims = [
        Claim(
            id="flow-fact", kind="fact", title="주요 실행 순서", 
            content="DELETE /members/me → MemberService.withdraw → MemberPolicy.validateWithdrawal 순서입니다.", 
            evidenceIds=["member-controller", "member-service"]
        )
    ]
    
    return ChatResponseData(
        questionKind="flow",
        summary="요청은 MemberController에서 시작해 MemberService의 유스케이스와 MemberPolicy 검증을 거칩니다.",
        claims=mock_claims,
        evidence=mock_evidence,
        confidence=Confidence(level="high", reason="컨트롤러 진입점과 주요 메서드 호출 관계를 코드에서 확인했습니다."),
        graph=GraphData(nodes=mock_nodes, edges=mock_edges),
        suggestedQuestions=["왜 논리 삭제로 구현되어 있어?", "이 로직을 수정하면 영향 범위가 어떻게 돼?"]
    )
