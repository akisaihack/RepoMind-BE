"""Flask extension instances initialized by the application factory."""

from flask_migrate import Migrate
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    """Base class for future SQLAlchemy 2.x models."""


db = SQLAlchemy(model_class=Base)
migrate = Migrate()
