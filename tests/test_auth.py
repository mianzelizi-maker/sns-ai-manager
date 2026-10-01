import importlib

import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def make_client(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("READ_ONLY_MODE", raising=False)

    def make(password: str | None = "secret"):
        if password is None:
            monkeypatch.delenv("ADMIN_PASSWORD", raising=False)
        else:
            monkeypatch.setenv("ADMIN_PASSWORD", password)
        monkeypatch.setenv("ADMIN_USERNAME", "admin")
        from app import main

        main = importlib.reload(main)
        return TestClient(main.app, follow_redirects=False)

    return make


def test_no_password_configured_means_no_login(make_client):
    assert make_client(password=None).get("/posts").status_code == 200


def test_unauthenticated_requests_redirect_to_login(make_client):
    client = make_client()
    for method, path in (("get", "/posts"), ("get", "/calendar"), ("post", "/posts/1/publish")):
        response = getattr(client, method)(path)
        assert response.status_code == 303, path
        assert response.headers["location"].startswith("/login"), path


def test_health_and_login_page_are_public(make_client):
    client = make_client()
    assert client.get("/health").status_code == 200
    assert client.get("/login").status_code == 200


def test_wrong_password_is_rejected(make_client):
    client = make_client()
    response = client.post("/login", data={"username": "admin", "password": "nope"})
    assert response.status_code == 401
    assert client.get("/posts").status_code == 303


def test_login_then_logout(make_client):
    client = make_client()
    response = client.post("/login", data={"username": "admin", "password": "secret"})
    assert response.status_code == 303
    assert client.get("/posts").status_code == 200

    client.post("/logout")
    assert client.get("/posts").status_code == 303


def test_login_does_not_redirect_to_external_site(make_client):
    client = make_client()
    for target in ("https://evil.example", "//evil.example"):
        response = client.post(
            "/login", data={"username": "admin", "password": "secret", "next": target}
        )
        assert response.headers["location"] == "/posts"


def test_read_only_demo_needs_no_login(make_client, monkeypatch):
    client = make_client()
    monkeypatch.setenv("READ_ONLY_MODE", "true")
    from app import main

    client = TestClient(importlib.reload(main).app, follow_redirects=False)
    assert client.get("/posts").status_code == 200
