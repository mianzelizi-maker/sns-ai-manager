import importlib

import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def client_factory(tmp_path, monkeypatch):
    """main.pyはimport時に環境変数とDBを読むため、一時ディレクトリで読み込み直す。"""
    monkeypatch.chdir(tmp_path)

    def make(read_only: bool):
        monkeypatch.setenv("READ_ONLY_MODE", "true" if read_only else "false")
        from app import main

        main = importlib.reload(main)
        return TestClient(main.app, follow_redirects=False)

    return make


def test_health(client_factory):
    assert client_factory(read_only=True).get("/health").json() == {"status": "ok"}


def test_read_only_blocks_post_requests(client_factory):
    response = client_factory(read_only=True).post("/posts/1/publish")
    assert response.status_code == 303
    assert response.headers["location"].startswith("/posts?error=")


def test_read_only_blocks_recommendation_updates(client_factory):
    response = client_factory(read_only=True).post("/recommendations/1/regenerate")
    assert response.headers["location"].startswith("/recommendations?error=")


def test_read_only_allows_pages(client_factory):
    client = client_factory(read_only=True)
    for path in ("/posts", "/calendar", "/recommendations"):
        assert client.get(path).status_code == 200, path


def test_read_only_analytics_page_and_refresh_block(client_factory):
    client = client_factory(read_only=True)
    assert client.get("/analytics").status_code == 200
    response = client.post("/analytics/refresh")
    assert response.headers["location"].startswith("/analytics?error=")
