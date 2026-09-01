import logging
from datetime import datetime, timedelta

from apscheduler.schedulers.background import BackgroundScheduler
from sqlalchemy.orm import Session

from app import models
from app.database import SessionLocal
from app.instagram_client import post_to_instagram
from app.x_client import post_tweet

logger = logging.getLogger("scheduler")


def _publish(generated_post: models.GeneratedPost) -> str:
    if generated_post.platform == models.Platform.X:
        return post_tweet(generated_post.content)
    return post_to_instagram(generated_post.content, generated_post.article.featured_image_url)


def _next_occurrence(current: datetime, schedule: "models.Schedule") -> datetime | None:
    repeat = schedule.repeat
    custom_weekdays = schedule.custom_weekdays
    if repeat == models.RepeatType.DAILY:
        return current + timedelta(days=1)

    if repeat == models.RepeatType.WEEKLY:
        return current + timedelta(weeks=1)

    if repeat == models.RepeatType.WEEKDAYS:
        nxt = current + timedelta(days=1)
        while nxt.weekday() >= 5:  # 5=土, 6=日
            nxt += timedelta(days=1)
        return nxt

    if repeat == models.RepeatType.CUSTOM:
        interval = schedule.custom_interval or 1
        unit = schedule.custom_unit or "week"

        if unit == "day":
            return current + timedelta(days=interval)

        if unit == "week":
            allowed = {int(w) for w in custom_weekdays.split(",")} if custom_weekdays else set()
            if not allowed:
                return current + timedelta(weeks=interval)
            # 今週内の残り曜日、その後はinterval週ごとの該当曜日を順に探す
            for days_ahead in range(1, interval * 7 + 7):
                candidate = current + timedelta(days=days_ahead)
                if candidate.weekday() not in allowed:
                    continue
                if days_ahead <= 7 - current.weekday() - 1:
                    return candidate  # 今週の残り曜日はinterval無視で毎回発生
                weeks_passed = (days_ahead - (7 - current.weekday() - 1) - 1) // 7 + 1
                if weeks_passed % interval == 0:
                    return candidate
            return None

        if unit == "month":
            month = current.month + interval
            year = current.year + (month - 1) // 12
            month = (month - 1) % 12 + 1
            import calendar as calendar_module

            day = min(current.day, calendar_module.monthrange(year, month)[1])
            return current.replace(year=year, month=month, day=day)

        if unit == "year":
            try:
                return current.replace(year=current.year + interval)
            except ValueError:
                return current.replace(year=current.year + interval, day=28)

        return None

    if repeat == models.RepeatType.MONTHLY:
        month = current.month + 1
        year = current.year + (month - 1) // 12
        month = (month - 1) % 12 + 1
        import calendar as calendar_module

        day = min(current.day, calendar_module.monthrange(year, month)[1])
        return current.replace(year=year, month=month, day=day)

    if repeat == models.RepeatType.YEARLY:
        try:
            return current.replace(year=current.year + 1)
        except ValueError:
            # 2/29のような日付がうるう年以外に存在しない場合
            return current.replace(year=current.year + 1, day=28)

    return None


def run_due_schedules(db: Session) -> None:
    now = datetime.now()
    due_schedules = (
        db.query(models.Schedule)
        .filter(models.Schedule.is_active.is_(True), models.Schedule.scheduled_at <= now)
        .all()
    )

    for schedule in due_schedules:
        source_post = schedule.generated_post
        try:
            external_post_id = _publish(source_post)
        except Exception:
            logger.exception("予約投稿の実行に失敗しました(schedule_id=%s)", schedule.id)
            continue

        posted_copy = models.GeneratedPost(
            article_id=source_post.article_id,
            platform=source_post.platform,
            content=source_post.content,
            status=models.PostStatus.POSTED,
        )
        db.add(posted_copy)
        db.flush()
        db.add(
            models.PostLog(
                generated_post_id=posted_copy.id,
                posted_at=datetime.utcnow(),
                external_post_id=external_post_id,
            )
        )

        schedule.occurrence_count += 1

        count_limit_reached = (
            schedule.repeat == models.RepeatType.CUSTOM
            and schedule.custom_end_type == "count"
            and schedule.custom_count is not None
            and schedule.occurrence_count >= schedule.custom_count
        )

        next_at = _next_occurrence(schedule.scheduled_at, schedule)
        if (
            not count_limit_reached
            and next_at is not None
            and (schedule.repeat_until is None or next_at <= schedule.repeat_until)
        ):
            schedule.scheduled_at = next_at
        else:
            schedule.is_active = False

        db.commit()


def _job() -> None:
    db = SessionLocal()
    try:
        run_due_schedules(db)
    finally:
        db.close()


def start_scheduler() -> BackgroundScheduler:
    scheduler = BackgroundScheduler()
    scheduler.add_job(_job, "interval", seconds=60, id="run_due_schedules")
    scheduler.start()
    return scheduler
