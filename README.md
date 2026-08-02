# RepoMind Backend

Python 3.12와 Flask 3.1 기반의 RepoMind 백엔드 초기 프로젝트입니다. Application Factory와
Blueprint 구조를 사용하며, 향후 기능은 API 버전별 모듈 아래에 확장할 수 있습니다.

## 요구 환경

- Python 3.12

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

`.env`의 `APP_ENV`는 `development`, `testing`, `production` 중 하나를 사용합니다. PostgreSQL을
사용하기 시작할 때는 PostgreSQL 드라이버를 포함해 설치하고 `DATABASE_URL`을 변경합니다.

```bash
pip install -e '.[dev,postgres]'
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
│   │   └── health.py         # Health Check API
│   ├── __init__.py           # Application Factory
│   ├── config.py             # 환경별 설정
│   ├── errors.py             # 공통 예외 및 처리기
│   ├── extensions.py         # SQLAlchemy, Alembic 확장 인스턴스
│   └── responses.py          # 공통 응답 형식
├── tests/
│   ├── conftest.py
│   └── test_health.py
├── .env.example
├── pyproject.toml
└── wsgi.py
```

PostgreSQL, Azure OpenAI, Neo4j, Tree-sitter 연동과 비즈니스 로직은 아직 포함하지 않습니다.
