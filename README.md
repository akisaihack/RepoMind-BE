# RepoMind Backend

Python 3.12와 Flask 3.1 기반의 RepoMind 백엔드 초기 프로젝트입니다. Application Factory와
Blueprint 구조를 사용하며, 향후 기능은 API 버전별 모듈 아래에 확장할 수 있습니다.

## 요구 환경

- Python 3.12
- Docker 및 Docker Compose

## 설치 및 실행

```bash
python3.12 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
pip install -e '.[dev]'
cp .env.example .env
flask --app wsgi run --debug
```

서버 실행 후 `GET http://localhost:8000/api/v1/health`로 상태를 확인할 수 있습니다.

```json
{
  "success": true,
  "data": {
    "status": "healthy"
  }
}
```

Flask에서 설정된 `DATABASE_URL`로 실제 쿼리가 실행되는지 확인하려면 다음 API를 호출합니다.

```bash
curl http://127.0.0.1:8000/api/v1/health/db
```

연결에 성공하면 다음 응답을 반환합니다.

```json
{
  "success": true,
  "data": {
    "status": "healthy",
    "database": "connected"
  }
}
```

DB에 연결할 수 없으면 API key나 DB 접속 문자열을 노출하지 않고 HTTP `503`과
`DATABASE_UNAVAILABLE` 오류를 반환합니다.

`.env`의 `APP_ENV`는 `development`, `testing`, `production` 중 하나를 사용합니다. 로컬
PostgreSQL에 연결하려면 PostgreSQL 드라이버를 포함해 설치합니다.

```bash
pip install -e '.[dev,postgres]'
```

## PostgreSQL 및 pgvector

로컬 개발 DB는 PostgreSQL 16과 pgvector가 포함된 Docker 이미지로 실행합니다. `.env`의
`POSTGRES_*` 값은 Compose 컨테이너 초기화에 사용되며 `DATABASE_URL`의 사용자, 비밀번호,
포트, DB 이름과 동일해야 합니다. 기본 로컬 포트는 `5433`입니다. 기존 `.env`를 사용 중이라면
아래 항목을 직접 추가하거나 동일한 형식으로 변경합니다.

```dotenv
POSTGRES_DB=repomind
POSTGRES_USER=repomind
POSTGRES_PASSWORD=repomind_dev_password
POSTGRES_PORT=5433
DATABASE_URL=postgresql+psycopg://repomind:repomind_dev_password@localhost:5433/repomind
```

DB를 백그라운드에서 실행합니다.

```bash
docker compose up -d
```

컨테이너와 health 상태를 확인합니다.

```bash
docker compose ps
```

로그를 계속 확인하려면 다음 명령을 사용하며, 종료는 `Ctrl+C`입니다.

```bash
docker compose logs -f postgres
```

`vector` 확장이 활성화되었는지 확인합니다.

```bash
docker compose exec postgres sh -c \
  'psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -c "SELECT extname, extversion FROM pg_extension WHERE extname = '\''vector'\'';"'
```

컨테이너를 종료하고 제거합니다. named volume의 데이터는 유지됩니다.

```bash
docker compose down
```

`init.sql`은 named volume이 처음 생성될 때만 실행됩니다. `docker compose down -v`는 DB 데이터를
담은 volume까지 삭제하므로 데이터 초기화가 명확히 필요한 경우가 아니면 사용하지 마세요.

## Neo4j

Neo4j Community Edition은 PostgreSQL과 같은 Compose 구성으로 실행됩니다. `.env`에 다음 항목을 추가합니다. 
Community Edition Docker 이미지의 초기 사용자명은 `neo4j`로
고정되므로 `NEO4J_USERNAME`은 변경하지 않습니다.

```dotenv
NEO4J_URI=neo4j://localhost:7687
NEO4J_USERNAME=neo4j
NEO4J_PASSWORD=repomind_neo4j_dev_password
NEO4J_HTTP_PORT=7474
NEO4J_BOLT_PORT=7687
```

PostgreSQL과 Neo4j를 함께 실행하고 상태를 확인합니다.

```bash
docker compose up -d
docker compose ps
```

Neo4j 로그만 확인하려면 다음 명령을 사용합니다.

```bash
docker compose logs -f neo4j
```

브라우저에서 [Neo4j Browser](http://localhost:7474)에 접속하고 `.env`의 사용자명과 비밀번호로
로그인합니다. Bolt 연결 주소는 `neo4j://localhost:7687`입니다.

Flask 설정과 Python 드라이버로 연결을 확인합니다.

```bash
python - <<'PY'
from app import create_app
from app.clients.neo4j import Neo4jClient

app = create_app()
with Neo4jClient.from_config(app.config) as client:
    client.verify_connectivity()
print("Neo4j connection: OK")
PY
```

위 연결 확인은 그래프나 데이터를 생성하지 않습니다.

## GitHub 개발 이력 수집

`.env`에 GitHub 토큰과 대상 저장소를 설정합니다.

```dotenv
GITHUB_TOKEN=your-personal-access-token
GITHUB_REPOSITORY_OWNER=your-organization-or-username
GITHUB_REPOSITORY_NAME=your-repository
```

수집 결과를 확인합니다.

```bash
python scripts/check_github_collection.py
```

저장소, 브랜치, Issue, Pull Request, Commit 및 변경 파일 정보를 수집합니다. 위 확인 스크립트의
결과는 PostgreSQL이나 Neo4j에 저장하지 않고 실행 중 DTO 형태로만 관리합니다.

### GitHub 개발 이력 저장

PostgreSQL 테이블과 Neo4j 제약조건을 준비한 뒤 개발 이력을 저장합니다.

```bash
flask --app wsgi db upgrade
python scripts/init_neo4j_schema.py
python scripts/import_github_history.py
```

파일별 patch와 변경 라인 구간은 PostgreSQL에 저장하고, Repository·Issue·Pull Request·Commit·File
관계는 Neo4j에 저장합니다. 동일한 저장소를 다시 실행하면 기존 데이터를 갱신합니다.

Neo4j Browser(`http://localhost:7474`)에서 Commit과 변경 파일 관계를 확인합니다.

```cypher
MATCH path = (commit:Commit)-[:CHANGED]->(file:File)
RETURN path
LIMIT 50;
```

PostgreSQL에서 저장된 patch를 확인합니다.

```bash
docker compose exec postgres sh -c \
  'psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -c \
  "SELECT commit_sha, file_path, patch_status FROM commit_file_changes LIMIT 20;"'
```

## Azure OpenAI 임베딩

회사에서 제공한 Azure OpenAI 리소스 정보를 `.env`에 설정합니다. 실제 값과 API key는 커밋하거나
로그에 출력하지 않습니다.

```dotenv
AZURE_OPENAI_ENDPOINT=https://your-resource.openai.azure.com/
AZURE_OPENAI_API_KEY=your-api-key
AZURE_OPENAI_EMBEDDING_DEPLOYMENT=shared-embedding
```

테스트 API는 전체 벡터를 노출하지 않고 차원과 처음 세 값만 반환합니다.

```bash
curl -X POST http://127.0.0.1:8000/api/v1/embeddings/test \
  -H 'Content-Type: application/json' \
  -d '{"text":"예약 취소 처리 흐름을 분석합니다."}'
```

```json
{
  "dimension": 1536,
  "embeddingPreview": [0.01, -0.02, 0.03]
}
```

Azure 호출 없이 mock 테스트만 실행하려면 다음 명령을 사용합니다.

```bash
pytest tests/test_embedding_service.py tests/test_embeddings_api.py
```

## 개발 명령어

```bash
ruff check .
ruff format --check .
pytest
pytest --cov=app
```

## 데이터베이스 마이그레이션

Flask-SQLAlchemy와 Flask-Migrate가 Application Factory에 연결되어 있습니다. 모델을 추가한 뒤
최초 한 번 마이그레이션 디렉터리를 초기화하고 리비전을 생성합니다.

```bash
flask --app wsgi db init
flask --app wsgi db migrate -m "create initial tables"
flask --app wsgi db upgrade
```

이번 초기 설정에는 실제 데이터베이스 모델이나 마이그레이션 리비전이 포함되지 않습니다.

## 프로젝트 구조

```text
.
├── app/
│   ├── api/
│   │   ├── __init__.py       # /api/v1 Blueprint 구성
│   │   ├── embeddings.py     # 임베딩 테스트 API
│   │   └── health.py         # Health Check API
│   ├── clients/
│   │   ├── azure_openai.py   # Azure OpenAI 클라이언트 팩토리
│   │   ├── github.py         # GitHub REST API 및 페이지네이션
│   │   └── neo4j.py          # Neo4j 드라이버 및 연결 확인
│   ├── dtos/
│   │   └── github.py         # 개발 이력 수집 DTO
│   ├── services/
│   │   ├── embedding.py      # 임베딩 서비스
│   │   └── github_history.py # GitHub 개발 이력 수집
│   ├── __init__.py           # Application Factory
│   ├── config.py             # 환경별 설정
│   ├── errors.py             # 공통 예외 및 처리기
│   ├── extensions.py         # SQLAlchemy, Alembic 확장 인스턴스
│   └── responses.py          # 공통 응답 형식
├── tests/
│   ├── conftest.py
│   └── test_health.py
├── docker/
│   └── postgres/
│       └── init.sql           # 최초 vector 확장 활성화
├── scripts/
│   └── check_github_collection.py
├── .env.example
├── compose.yml
├── pyproject.toml
└── wsgi.py
```

PostgreSQL과 Neo4j 저장소, GitHub 개발 이력 수집, Tree-sitter 기반 Java 코드 분석 및 코드 그래프
저장 기능이 포함되어 있습니다.

## 코드 그래프 가져오기

GitHub 개발 이력과 Java 코드 분석 결과는 다음 형식의 키를 사용하여 동일한 `File` 노드를
공유합니다.

```text
{githubRepositoryId}:file:{normalizedRepositoryRelativePath}
```

두 import 과정 모두 Windows와 POSIX 경로 표현을 정규화하고 Neo4j `MERGE`를 사용합니다.
따라서 실행 순서가 달라지거나 같은 데이터를 반복해서 저장해도 File 노드가 중복 생성되지
않습니다.

로컬에서 Neo4j만 실행하고 그래프 제약조건을 초기화합니다.

```bash
docker compose up -d neo4j
python scripts/init_neo4j_schema.py
```

로컬에 checkout한 Java 저장소를 분석하여 코드 그래프를 저장합니다.

```bash
python scripts/import_code_graph.py \
  --github-repository-id 1296269 \
  --repository-path /path/to/repository
```

import 전에 로컬 저장소의 `origin`과 `githubRepositoryId`가 가리키는 GitHub 저장소가 같은지
검증합니다. Neo4j에 Repository 정보가 있으면 이를 먼저 사용하고, 없으면 GitHub API로 조회합니다.
일치하지 않거나 `origin`이 없으면 import를 중단합니다. 검증을 의도적으로 생략해야 할 때만 다음
옵션을 명시합니다.

```bash
python scripts/import_code_graph.py \
  --github-repository-id 1296269 \
  --repository-path /path/to/repository \
  --skip-repository-validation
```

백엔드를 호스트에서 실행할 때 `NEO4J_URI=bolt://127.0.0.1:7687`은 실행 중인 컴퓨터의
로컬 Neo4j를 가리킵니다. 백엔드까지 Docker 컨테이너에서 실행하는 경우에는 Compose 서비스
이름을 사용하여 `NEO4J_URI=bolt://neo4j:7687`로 설정해야 합니다.

프로젝트 내부 노드로 해석된 파일 간 관계는 Neo4j에 저장됩니다. 후보가 여러 개인 참조는 각
후보에 `ambiguous=true`로 저장합니다. 대상 노드를 찾지 못한 외부 참조는 mapper 결과에 진단
정보로 유지하지만 Neo4j에는 저장하지 않으며, import 결과에 제외된 관계 수를 출력합니다.
