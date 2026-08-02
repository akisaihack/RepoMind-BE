"""Shared pytest fixtures."""

import pytest
from flask import Flask
from flask.testing import FlaskClient

from app import create_app


@pytest.fixture()
def app() -> Flask:
    return create_app("testing")


@pytest.fixture()
def client(app: Flask) -> FlaskClient:
    return app.test_client()
