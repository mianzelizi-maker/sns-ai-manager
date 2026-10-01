from datetime import datetime

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app import models, scheduler
from app.database import Base


def _schedule(repeat, **kwargs):
    return models.Schedule(repeat=repeat, **kwargs)


@pytest.fixture
def db():
    engine = create_engine("sqlite://")
    Base.metadata.create_all(bind=engine)
    session = sessionmaker(bind=engine)()
    yield session
    session.close()


def _make_post(db, platform=models.Platform.X):
    article = models.Article(wp_post_id=1, title="t", body="b")
    post = models.GeneratedPost(
        article=article, platform=platform, content="hello", status=models.PostStatus.APPROVED
    )
    db.add(post)
    db.commit()
    return post


@pytest.mark.parametrize(
    "repeat, current, expected",
    [
        (models.RepeatType.DAILY, datetime(2026, 10, 1, 9), datetime(2026, 10, 2, 9)),
        (models.RepeatType.WEEKLY, datetime(2026, 10, 1, 9), datetime(2026, 10, 8, 9)),
        # 金曜の次は月曜
        (models.RepeatType.WEEKDAYS, datetime(2026, 10, 2, 9), datetime(2026, 10, 5, 9)),
        # 月末は翌月の末日に丸める
        (models.RepeatType.MONTHLY, datetime(2026, 1, 31, 9), datetime(2026, 2, 28, 9)),
        (models.RepeatType.MONTHLY, datetime(2026, 12, 15, 9), datetime(2027, 1, 15, 9)),
        # うるう日は翌年28日に丸める
        (models.RepeatType.YEARLY, datetime(2028, 2, 29, 9), datetime(2029, 2, 28, 9)),
        (models.RepeatType.NONE, datetime(2026, 10, 1, 9), None),
    ],
)
def test_next_occurrence_basic(repeat, current, expected):
    assert scheduler._next_occurrence(current, _schedule(repeat)) == expected


def test_custom_every_n_days():
    s = _schedule(models.RepeatType.CUSTOM, custom_interval=3, custom_unit="day")
    assert scheduler._next_occurrence(datetime(2026, 10, 1, 9), s) == datetime(2026, 10, 4, 9)


def test_custom_weekdays_within_same_week():
    # 2026-10-05は月曜。月水金指定なら次は水曜
    s = _schedule(
        models.RepeatType.CUSTOM, custom_interval=1, custom_unit="week", custom_weekdays="0,2,4"
    )
    assert scheduler._next_occurrence(datetime(2026, 10, 5, 9), s) == datetime(2026, 10, 7, 9)


def test_custom_every_n_months_and_years():
    month = _schedule(models.RepeatType.CUSTOM, custom_interval=2, custom_unit="month")
    assert scheduler._next_occurrence(datetime(2026, 11, 30, 9), month) == datetime(2027, 1, 30, 9)
    year = _schedule(models.RepeatType.CUSTOM, custom_interval=2, custom_unit="year")
    assert scheduler._next_occurrence(datetime(2026, 10, 1, 9), year) == datetime(2028, 10, 1, 9)


def test_due_schedule_posts_and_deactivates_when_not_repeating(db, monkeypatch):
    post = _make_post(db)
    monkeypatch.setattr(scheduler, "_publish", lambda p: "ext-1")
    db.add(models.Schedule(generated_post_id=post.id, scheduled_at=datetime(2020, 1, 1)))
    db.commit()

    scheduler.run_due_schedules(db)

    schedule = db.query(models.Schedule).one()
    assert schedule.is_active is False
    assert schedule.occurrence_count == 1
    log = db.query(models.PostLog).one()
    assert log.external_post_id == "ext-1"
    posted = db.get(models.GeneratedPost, log.generated_post_id)
    assert posted.status == models.PostStatus.POSTED


def test_future_schedule_is_not_run(db, monkeypatch):
    post = _make_post(db)
    monkeypatch.setattr(scheduler, "_publish", lambda p: pytest.fail("実行されないはず"))
    db.add(models.Schedule(generated_post_id=post.id, scheduled_at=datetime(2999, 1, 1)))
    db.commit()

    scheduler.run_due_schedules(db)

    assert db.query(models.PostLog).count() == 0


def test_repeating_schedule_advances(db, monkeypatch):
    post = _make_post(db)
    monkeypatch.setattr(scheduler, "_publish", lambda p: "ext")
    db.add(
        models.Schedule(
            generated_post_id=post.id,
            scheduled_at=datetime(2020, 1, 1, 9),
            repeat=models.RepeatType.DAILY,
        )
    )
    db.commit()

    scheduler.run_due_schedules(db)

    schedule = db.query(models.Schedule).one()
    assert schedule.is_active is True
    assert schedule.scheduled_at == datetime(2020, 1, 2, 9)


def test_custom_count_limit_stops_schedule(db, monkeypatch):
    post = _make_post(db)
    monkeypatch.setattr(scheduler, "_publish", lambda p: "ext")
    db.add(
        models.Schedule(
            generated_post_id=post.id,
            scheduled_at=datetime(2020, 1, 1, 9),
            repeat=models.RepeatType.CUSTOM,
            custom_interval=1,
            custom_unit="day",
            custom_end_type="count",
            custom_count=1,
        )
    )
    db.commit()

    scheduler.run_due_schedules(db)

    assert db.query(models.Schedule).one().is_active is False


def test_repeat_until_stops_schedule(db, monkeypatch):
    post = _make_post(db)
    monkeypatch.setattr(scheduler, "_publish", lambda p: "ext")
    db.add(
        models.Schedule(
            generated_post_id=post.id,
            scheduled_at=datetime(2020, 1, 1, 9),
            repeat=models.RepeatType.DAILY,
            repeat_until=datetime(2020, 1, 1, 23),
        )
    )
    db.commit()

    scheduler.run_due_schedules(db)

    assert db.query(models.Schedule).one().is_active is False


def test_publish_failure_keeps_schedule_active(db, monkeypatch):
    post = _make_post(db)

    def boom(p):
        raise RuntimeError("API error")

    monkeypatch.setattr(scheduler, "_publish", boom)
    db.add(models.Schedule(generated_post_id=post.id, scheduled_at=datetime(2020, 1, 1)))
    db.commit()

    scheduler.run_due_schedules(db)

    schedule = db.query(models.Schedule).one()
    assert schedule.is_active is True
    assert schedule.occurrence_count == 0
    assert db.query(models.PostLog).count() == 0
