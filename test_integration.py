"""
Quick integration tests for authentication and annotation endpoints.
Run with: pytest test_integration.py -v
"""
import pytest
from fastapi.testclient import TestClient
from main import app
from database import get_session
from sqlmodel import Session, create_engine, SQLModel, select
from sqlmodel.pool import StaticPool

# Use in-memory SQLite for tests
@pytest.fixture(name="session")
def session_fixture():
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    SQLModel.metadata.create_all(engine)
    with Session(engine) as session:
        yield session


@pytest.fixture(name="client")
def client_fixture(session: Session):
    def get_session_override():
        return session
    app.dependency_overrides[get_session] = get_session_override
    client = TestClient(app)
    yield client
    app.dependency_overrides.clear()


def test_signup(client: TestClient):
    """Test user signup."""
    response = client.post(
        "/auth/signup",
        data={"username": "testuser", "email": "test@example.com", "password": "pass123"}
    )
    assert response.status_code == 200
    data = response.json()
    assert "access_token" in data
    assert data["token_type"] == "bearer"
    assert data["user_id"] == 1


def test_login(client: TestClient):
    """Test user login."""
    # First sign up
    client.post(
        "/auth/signup",
        data={"username": "testuser", "email": "test@example.com", "password": "pass123"}
    )
    
    # Then login
    response = client.post(
        "/auth/login",
        data={"username": "testuser", "password": "pass123"}
    )
    assert response.status_code == 200
    data = response.json()
    assert "access_token" in data
    assert data["token_type"] == "bearer"


def test_login_invalid_password(client: TestClient):
    """Test login with wrong password."""
    client.post(
        "/auth/signup",
        data={"username": "testuser", "email": "test@example.com", "password": "pass123"}
    )
    
    response = client.post(
        "/auth/login",
        data={"username": "testuser", "password": "wrongpass"}
    )
    assert response.status_code == 401


def test_duplicate_username(client: TestClient):
    """Test signup with duplicate username."""
    client.post(
        "/auth/signup",
        data={"username": "testuser", "email": "test1@example.com", "password": "pass123"}
    )
    
    response = client.post(
        "/auth/signup",
        data={"username": "testuser", "email": "test2@example.com", "password": "pass123"}
    )
    assert response.status_code == 400
    assert "already exists" in response.json()["detail"]


def test_annotations_list_empty(client: TestClient, session: Session):
    """Test listing annotations on non-existent viz."""
    response = client.get("/viz/999/annotations")
    assert response.status_code == 404


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
