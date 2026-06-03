import pytest
from fastapi.testclient import TestClient
from main import app

client = TestClient(app)

def test_health():
    res = client.get("/health")
    assert res.status_code == 200
    assert res.json() == {"status": "ok"}

def test_login_success():
    res = client.post("/auth/login", json={"username": "owner", "password": "owner123"})
    assert res.status_code == 200
    data = res.json()
    assert "token" in data
    assert data["role"] == "owner"

def test_login_wrong_password():
    res = client.post("/auth/login", json={"username": "owner", "password": "wrong"})
    assert res.status_code == 401

def test_get_computers_no_auth():
    res = client.get("/computers")
    assert res.status_code == 200

def test_get_clients_no_auth():
    res = client.get("/clients")
    assert res.status_code == 200

def test_get_tariffs_no_auth():
    res = client.get("/tariffs")
    assert res.status_code == 200

def test_get_users_no_auth():
    res = client.get("/users")
    assert res.status_code == 403 or res.status_code == 401

def test_get_sessions_active():
    res = client.get("/sessions/active")
    assert res.status_code == 200

def get_token():
    res = client.post("/auth/login", json={"username": "owner", "password": "owner123"})
    return res.json()["token"]

def test_get_users_with_auth():
    token = get_token()
    res = client.get("/users", headers={"Authorization": f"Bearer {token}"})
    assert res.status_code == 200
    assert isinstance(res.json(), list)

def test_create_and_delete_client():
    token = get_token()
    headers = {"Authorization": f"Bearer {token}"}
    res = client.post("/clients", json={"name": "Тестовый клиент"}, headers=headers)
    assert res.status_code == 200
    client_id = res.json()["id"]
    res = client.get("/clients", headers=headers)
    assert any(c["id"] == client_id for c in res.json())
