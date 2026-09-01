from datetime import datetime, timedelta

from sqlalchemy.orm import Session

from app import models

WEEKDAY_LABELS = ["月", "火", "水", "木", "金", "土", "日"]

# 初回アクセス時にDBへ登録される初期値(Phase 1のルールベース案)。
# 実運用データが蓄積された後は、エンゲージメント実績から算出するロジックに置き換える。
DEFAULT_RANGE = {
    models.Platform.X: ("12:00", "13:00"),
    models.Platform.INSTAGRAM: ("19:00", "21:00"),
}


def get_recommended_times(db: Session) -> dict:
    """{platform: {weekday(0=月..6=日): {"start": "HH:00", "end": "HH:00"}}} を返す。"""
    existing = {
        (row.platform, row.weekday): row for row in db.query(models.RecommendedTime).all()
    }

    result = {platform: {} for platform in models.Platform}
    for platform in models.Platform:
        for weekday in range(7):
            key = (platform, weekday)
            if key in existing:
                row = existing[key]
                result[platform][weekday] = {"start": row.start_time, "end": row.end_time}
            else:
                default_start, default_end = DEFAULT_RANGE[platform]
                db.add(
                    models.RecommendedTime(
                        platform=platform,
                        weekday=weekday,
                        start_time=default_start,
                        end_time=default_end,
                    )
                )
                result[platform][weekday] = {"start": default_start, "end": default_end}
    db.commit()
    return result


def update_recommended_time(
    db: Session, platform: models.Platform, weekday: int, start_time: str, end_time: str
) -> None:
    row = db.query(models.RecommendedTime).filter_by(platform=platform, weekday=weekday).first()
    if row:
        row.start_time = start_time
        row.end_time = end_time
    else:
        db.add(
            models.RecommendedTime(
                platform=platform, weekday=weekday, start_time=start_time, end_time=end_time
            )
        )
    db.commit()


def get_repeat_settings(db: Session) -> dict:
    """{weekday: {"repeat": str, "custom_interval": int, "custom_unit": str, "enabled": bool}} を返す。"""
    existing = {row.weekday: row for row in db.query(models.RecommendationRepeat).all()}
    result = {}
    for weekday in range(7):
        if weekday in existing:
            row = existing[weekday]
            result[weekday] = {
                "repeat": row.repeat,
                "custom_interval": row.custom_interval or 1,
                "custom_unit": row.custom_unit or "week",
                "enabled": row.enabled,
            }
        else:
            db.add(models.RecommendationRepeat(weekday=weekday, repeat="weekly"))
            result[weekday] = {
                "repeat": "weekly",
                "custom_interval": 1,
                "custom_unit": "week",
                "enabled": True,
            }
    db.commit()
    return result


def update_repeat_setting(
    db: Session,
    weekday: int,
    repeat: str,
    custom_interval: int,
    custom_unit: str,
    enabled: bool,
) -> None:
    row = db.query(models.RecommendationRepeat).filter_by(weekday=weekday).first()
    if row:
        row.repeat = repeat
        row.custom_interval = custom_interval
        row.custom_unit = custom_unit
        row.enabled = enabled
    else:
        db.add(
            models.RecommendationRepeat(
                weekday=weekday,
                repeat=repeat,
                custom_interval=custom_interval,
                custom_unit=custom_unit,
                enabled=enabled,
            )
        )
    db.commit()


def get_repost_candidates(db: Session, days: int = 14) -> list[models.Article]:
    """直近days日以内にどの媒体にも投稿されていない記事を、リポスト候補として返す。"""
    cutoff = datetime.utcnow() - timedelta(days=days)

    candidates = []
    for article in db.query(models.Article).all():
        recent_post = (
            db.query(models.PostLog)
            .join(models.GeneratedPost)
            .filter(
                models.GeneratedPost.article_id == article.id,
                models.PostLog.posted_at >= cutoff,
            )
            .first()
        )
        if recent_post is None:
            candidates.append(article)

    return candidates
