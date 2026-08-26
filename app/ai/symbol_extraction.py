"""질문에서 저장소 심볼과 대조할 식별자 후보를 추출한다."""

import re

_IDENTIFIER = r"[A-Za-z_$][A-Za-z0-9_$]*"
_CONTEXT_PATTERN = re.compile(
    rf"(?P<name>{_IDENTIFIER})(?:\(\))?\s*(?:함수|메서드|클래스|필드|변수)"
)
_QUALIFIED_PATTERN = re.compile(rf"(?P<owner>{_IDENTIFIER})\.(?P<member>{_IDENTIFIER})")
_IDENTIFIER_PATTERN = re.compile(_IDENTIFIER)
_COMMON_WORDS = {
    "API",
    "AI",
    "DB",
    "GET",
    "HTTP",
    "Issue",
    "LLM",
    "POST",
    "PR",
    "PullRequest",
    "URL",
}


def extract_symbol_candidates(question: str) -> list[str]:
    """자연어 질문에서 코드 이름일 가능성이 높은 후보를 우선순위대로 반환한다."""
    candidates: list[str] = []

    for match in _CONTEXT_PATTERN.finditer(question):
        candidates.append(match.group("name"))
    for match in _QUALIFIED_PATTERN.finditer(question):
        candidates.extend((match.group("member"), match.group("owner")))
    for token in _IDENTIFIER_PATTERN.findall(question):
        if _looks_like_code_identifier(token):
            candidates.append(token)

    return list(dict.fromkeys(candidates))


def _looks_like_code_identifier(token: str) -> bool:
    if token in _COMMON_WORDS or len(token) < 2:
        return False
    return "_" in token or "$" in token or any(character.isupper() for character in token[1:])


__all__ = ["extract_symbol_candidates"]
