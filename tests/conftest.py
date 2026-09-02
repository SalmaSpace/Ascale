"""Fixtures partagées entre tous les modules de tests."""

import pytest
from sqlalchemy.pool import StaticPool

import email_service
from app import create_app


TEST_CONFIG = {
    "TESTING": True,
    # Base in-memory isolée : StaticPool garantit que toutes les connexions
    # de la session partagent le même fichier en mémoire.
    "SQLALCHEMY_DATABASE_URI": "sqlite:///:memory:",
    "SQLALCHEMY_ENGINE_OPTIONS": {
        "connect_args": {"check_same_thread": False},
        "poolclass":    StaticPool,
    },
    "SQLALCHEMY_TRACK_MODIFICATIONS": False,
    "SECRET_KEY": "test-secret",
}


@pytest.fixture(scope="function")
def app(monkeypatch):
    """Application Flask avec base SQLite in-memory fraîche pour chaque test."""
    # Supprime l'envoi réel d'emails pendant les tests, même si un .env local
    # avec une vraie clé Brevo est chargé (email_service lit ces constantes
    # au niveau module, pas via app.config).
    monkeypatch.setattr(email_service, "BREVO_API_KEY", "")
    flask_app = create_app(test_config=TEST_CONFIG)
    with flask_app.app_context():
        yield flask_app


@pytest.fixture(scope="function")
def client(app):
    """Client HTTP de test (sans session persistante entre les requêtes)."""
    return app.test_client()


@pytest.fixture(scope="function")
def store(app):
    """Instance Store attachée à l'application de test."""
    return app.store
