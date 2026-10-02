import json
import logging
import os
from collections import defaultdict
from datetime import datetime, timedelta
from typing import Callable

import requests
from sqlalchemy.orm import Session

from app import models
from app.x_client import _v2_client

logger = logging.getLogger("engagement")

GRAPH_API_BASE = "https://graph.facebook.com/v21.0"
JST_OFFSET = timedelta(hours=9)
WEEKDAY_LABELS = ["月", "火", "水", "木", "金", "土", "日"]
# 投稿から日が浅いうちは反応が動くため取得対象にし、古い投稿は取得をやめてAPI呼び出しを減らす
REFRESH_WINDOW_DAYS = 30


def fetch_metrics(platform: models.Platform, external_post_id: str) -> dict | None:
    """投稿の反応数を取得する。取得できない(モック投稿・認証情報なし)場合はNone。"""
    if not external_post_id or external_post_id.startswith("mock_"):
        return None

    if platform == models.Platform.X:
        response = _v2_client().get_tweet(external_post_id, tweet_fields=["public_metrics"])
        m = response.data["public_metrics"]
        return {
            "likes": m.get("like_count", 0),
            "reposts": m.get("retweet_count", 0),
            "replies": m.get("reply_count", 0),
            "quotes": m.get("quote_count", 0),
            "impressions": m.get("impression_count"),
        }

    token = os.environ.get("INSTAGRAM_ACCESS_TOKEN")
    if not token:
        return None
    response = requests.get(
        f"{GRAPH_API_BASE}/{external_post_id}",
        params={"fields": "like_count,comments_count", "access_token": token},
        timeout=15,
    )
    response.raise_for_status()
    data = response.json()
    return {
        "likes": data.get("like_count", 0),
        "reposts": 0,
        "replies": data.get("comments_count", 0),
        "quotes": 0,
        "impressions": None,
    }


def refresh_engagement(
    db: Session,
    fetch: Callable[[models.Platform, str], dict | None] = fetch_metrics,
    now: datetime | None = None,
) -> int:
    """直近の投稿の反応数を取得してPostLog.engagement_jsonに保存する。更新できた件数を返す。"""
    now = now or datetime.utcnow()
    cutoff = now - timedelta(days=REFRESH_WINDOW_DAYS)
    logs = db.query(models.PostLog).filter(models.PostLog.posted_at >= cutoff).all()

    updated = 0
    for log in logs:
        try:
            metrics = fetch(log.generated_post.platform, log.external_post_id)
        except Exception:
            # 1件の失敗(レート制限や削除済みの投稿など)で、他の投稿の更新を止めない
            logger.exception("反応数の取得に失敗しました(post_log_id=%s)", log.id)
            continue
        if metrics is None:
            continue
        log.engagement_json = json.dumps({**metrics, "fetched_at": now.isoformat()})
        updated += 1
    db.commit()
    return updated


def _score(metrics: dict) -> int:
    return sum(metrics.get(k) or 0 for k in ("likes", "reposts", "replies", "quotes"))


def build_summary(db: Session) -> dict:
    """分析画面用に、投稿ごとの反応・合計・曜日別/時間帯別の平均を集計する。"""
    rows = []
    for log in db.query(models.PostLog).order_by(models.PostLog.posted_at.desc()).all():
        if not log.engagement_json:
            continue
        metrics = json.loads(log.engagement_json)
        post = log.generated_post
        posted_jst = log.posted_at + JST_OFFSET
        impressions = metrics.get("impressions")
        score = _score(metrics)
        rows.append(
            {
                "post": post,
                "platform": post.platform,
                "title": post.article.title,
                "posted_jst": posted_jst,
                "metrics": metrics,
                "score": score,
                "rate": score / impressions if impressions else None,
                "sample": bool(metrics.get("sample")),
            }
        )

    by_weekday: dict[int, list[int]] = defaultdict(list)
    by_hour: dict[int, list[int]] = defaultdict(list)
    for row in rows:
        by_weekday[row["posted_jst"].weekday()].append(row["score"])
        by_hour[row["posted_jst"].hour].append(row["score"])

    def averages(groups: dict[int, list[int]]) -> list[dict]:
        return [
            {"key": key, "average": sum(v) / len(v), "count": len(v)}
            for key, v in sorted(groups.items())
        ]

    weekday_stats = averages(by_weekday)
    for stat in weekday_stats:
        stat["label"] = WEEKDAY_LABELS[stat["key"]]

    return {
        "rows": rows,
        "top": sorted(rows, key=lambda r: r["score"], reverse=True)[:3],
        "total_score": sum(r["score"] for r in rows),
        "weekday_stats": weekday_stats,
        "hour_stats": averages(by_hour),
        "has_sample": any(r["sample"] for r in rows),
    }
