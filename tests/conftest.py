"""Shared pytest fixtures."""

import pytest
from flask import Flask
from flask.testing import FlaskClient

from app import create_app


from app.extensions import db

@pytest.fixture()
def app() -> Flask:
    app = create_app("testing")
    with app.app_context():
        db.create_all()
    return app


@pytest.fixture()
def client(app: Flask) -> FlaskClient:
    return app.test_client()
