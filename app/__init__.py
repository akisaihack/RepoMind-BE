"""Application factory for the RepoMind API."""

from flask import Flask

from app.api.v1 import api_v1
from app.config import get_config
from app.errors import register_error_handlers
from app.extensions import db, migrate


def create_app(config_name: str | None = None) -> Flask:
    """Create and configure a Flask application instance."""
    app = Flask(__name__, instance_relative_config=True)
    app.config.from_object(get_config(config_name))

    db.init_app(app)
    migrate.init_app(app, db)

    app.register_blueprint(api_v1)
    register_error_handlers(app)

    return app
