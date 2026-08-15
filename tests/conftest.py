import mongomock
import pytest

from app import create_app, db


@pytest.fixture()
def mongo_db():
    """A fresh in-memory MongoDB (mongomock) for each test, injected as the
    app's active database."""
    client = mongomock.MongoClient(tz_aware=True)
    database = client["vehicle_safety_test"]
    db.set_db(database)
    yield database


@pytest.fixture()
def app(mongo_db):
    application = create_app()
    application.config.update(TESTING=True)
    return application


@pytest.fixture()
def client(app):
    return app.test_client()
