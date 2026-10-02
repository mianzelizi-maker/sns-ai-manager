import json
from datetime import datetime, timedelta

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app import engagement, models
from app.database import Base

NOW = datetime(2026, 10, 1, 12)
EMPTY = {"likes": 0, "reposts": 0, "replies": 0, "quotes": 0, "impressions": None}


@pytest.fixture
def db():
    engine = create_engine("sqlite://")
    Base.metadata.create_all(bind=engine)
    session = sessionmaker(bind=engine)()
    yield session
    session.close()


@pytest.fixture
def add_log(db):
    counter = iter(range(1, 1000))

    def add(posted_at, platform=models.Platform.X, ext="1", metrics=None):
        n = next(counter)
        article = models.Article(wp_post_id=n, title=f"記事{n}", body="b")
        post = models.GeneratedPost(
            article=article, platform=platform, content="c", status=models.PostStatus.POSTED
        )
        log = models.PostLog(
            generated_post=post,
            posted_at=posted_at,
            external_post_id=ext,
            engagement_json=json.dumps(metrics) if metrics else None,
        )
        db.add(log)
        db.commit()
        return log

    return add


def test_refresh_stores_metrics(db, add_log):
    log = add_log(NOW - timedelta(days=1))
    fetch = lambda platform, ext: {**EMPTY, "likes": 3, "impressions": 100}

    assert engagement.refresh_engagement(db, fetch=fetch, now=NOW) == 1

    stored = json.loads(log.engagement_json)
    assert stored["likes"] == 3 and stored["fetched_at"] == NOW.isoformat()


def test_refresh_skips_old_posts_and_unavailable_metrics(db, add_log):
    old = add_log(NOW - timedelta(days=60))
    mock = add_log(NOW - timedelta(days=1), platform=models.Platform.INSTAGRAM, ext="mock_x")
    calls = []

    def fetch(platform, ext):
        calls.append(ext)
        return None

    assert engagement.refresh_engagement(db, fetch=fetch, now=NOW) == 0
    assert calls == ["mock_x"]
    assert old.engagement_json is None and mock.engagement_json is None


def test_one_failure_does_not_stop_others(db, add_log):
    bad = add_log(NOW - timedelta(days=1), ext="bad")
    good = add_log(NOW - timedelta(days=1), ext="good")

    def fetch(platform, ext):
        if ext == "bad":
            raise RuntimeError("rate limit")
        return {**EMPTY, "likes": 1}

    assert engagement.refresh_engagement(db, fetch=fetch, now=NOW) == 1
    assert bad.engagement_json is None and good.engagement_json is not None


def test_fetch_metrics_returns_none_for_mock_posts():
    assert engagement.fetch_metrics(models.Platform.INSTAGRAM, "mock_abc") is None


def test_summary_scores_rates_and_weekday_in_jst(add_log, db):
    # UTC 2026-10-01 20:00 は日本時間で 10/2(金) 05:00
    add_log(
        datetime(2026, 10, 1, 20),
        metrics={"likes": 6, "reposts": 2, "replies": 1, "quotes": 1, "impressions": 200},
    )
    add_log(datetime(2026, 10, 1, 21), ext="2", metrics={**EMPTY, "likes": 2})

    summary = engagement.build_summary(db)

    assert summary["total_score"] == 12
    assert summary["top"][0]["score"] == 10
    rates = {r["score"]: r["rate"] for r in summary["rows"]}
    assert rates[10] == pytest.approx(0.05) and rates[2] is None
    assert [s["label"] for s in summary["weekday_stats"]] == ["金"]
    assert summary["weekday_stats"][0]["average"] == 6
    assert summary["has_sample"] is False


def test_summary_ignores_posts_without_metrics_and_flags_samples(add_log, db):
    add_log(NOW)
    add_log(NOW, ext="2", metrics={**EMPTY, "likes": 1, "impressions": 10, "sample": True})

    summary = engagement.build_summary(db)

    assert len(summary["rows"]) == 1 and summary["has_sample"] is True


def test_x_fetch_uses_user_auth_and_maps_metrics(monkeypatch):
    # OAuth1のユーザー認証を指定しないとBearerトークン扱いになり、401になる
    captured = {}

    class FakeClient:
        def get_tweet(self, tweet_id, **kwargs):
            captured.update(kwargs)

            class Response:
                data = {
                    "public_metrics": {
                        "like_count": 5,
                        "retweet_count": 2,
                        "reply_count": 1,
                        "quote_count": 0,
                        "impression_count": 80,
                    }
                }

            return Response()

    monkeypatch.setattr(engagement, "_v2_client", lambda: FakeClient())

    metrics = engagement.fetch_metrics(models.Platform.X, "123")

    assert captured["user_auth"] is True
    assert metrics == {"likes": 5, "reposts": 2, "replies": 1, "quotes": 0, "impressions": 80}
