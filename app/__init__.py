"""Application factory for the RepoMind API."""

import logging

from flask import Flask
from flask_cors import CORS

from app.api.v1 import api_v1
from app.config import get_config
from app.errors import register_error_handlers
from app.extensions import db, migrate
from app.models import register_models


def create_app(config_name: str | None = None) -> Flask:
    """Create and configure a Flask application instance."""
    app = Flask(__name__, instance_relative_config=True)
    
    CORS(app, resources={r"/api/*": {"origins": "*"}})

    app.config.from_object(get_config(config_name))
    logging.basicConfig(
        level=app.config["LOG_LEVEL"],
        format="%(asctime)s %(levelname)s [%(threadName)s] %(name)s - %(message)s",
    )
    logging.getLogger().setLevel(app.config["LOG_LEVEL"])
    # 외부 라이브러리의 요청 단위 INFO 로그는 분석 진행 로그를 묻히므로
    # 경고와 오류만 출력한다. RepoMind의 app.* 로그는 위 설정대로 INFO 유지.
    for noisy_logger in ("httpx", "httpcore", "neo4j", "openai._base_client"):
        logging.getLogger(noisy_logger).setLevel(logging.WARNING)
    register_models()

    db.init_app(app)
    migrate.init_app(app, db)

    app.register_blueprint(api_v1)
    register_error_handlers(app)

    return app
