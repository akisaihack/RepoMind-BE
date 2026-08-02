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
│   │   └── azure_openai.py   # Azure OpenAI 클라이언트 팩토리
│   ├── services/
│   │   └── embedding.py      # 임베딩 서비스
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
├── .env.example
├── compose.yml
├── pyproject.toml
└── wsgi.py
```

PostgreSQL 테이블과 SQLAlchemy 모델, Neo4j 및 Tree-sitter 연동과 비즈니스 로직은 아직 포함하지
않습니다.
