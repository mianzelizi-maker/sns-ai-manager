import os
import shutil
from datetime import date, datetime
from pathlib import Path
from urllib.parse import quote

from fastapi import Depends, FastAPI, Form, Request
from fastapi.responses import RedirectResponse
from fastapi.staticfiles import StaticFiles
from starlette.middleware.sessions import SessionMiddleware
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from app import auth, models  # noqa: F401  register models before create_all
from app.ai_generator import generate_image_prompt, generate_sns_posts
from app.calendar_view import build_calendar
from app.engagement import build_summary, refresh_engagement
from app.database import Base, engine, get_db
from app.image_generator import IMAGE_DIR, generate_image
from app.instagram_client import post_to_instagram
from app.recommender import (
    WEEKDAY_LABELS,
    get_recommended_times,
    get_repeat_settings,
    get_repost_candidates,
    update_recommended_time,
    update_repeat_setting,
)
from app.scheduler import start_scheduler
from app.x_client import post_tweet

READ_ONLY_MODE = os.environ.get("READ_ONLY_MODE", "").lower() == "true"

# 閲覧専用の公開デモで、DBが空の状態でデプロイされた場合にサンプルデータを投入する。
_DEMO_DB = Path("demo_seed.db")
_DEMO_IMAGES = Path("demo_data/images")
if READ_ONLY_MODE:
    db_path = Path("sns_manager.db")
    if not db_path.exists() and _DEMO_DB.exists():
        shutil.copy(_DEMO_DB, db_path)
    if _DEMO_IMAGES.exists():
        IMAGE_DIR.mkdir(exist_ok=True)
        for image_file in _DEMO_IMAGES.glob("*.png"):
            dest = IMAGE_DIR / image_file.name
            if not dest.exists():
                shutil.copy(image_file, dest)

Base.metadata.create_all(bind=engine)

app = FastAPI(title="SNS AI運用システム")
templates = Jinja2Templates(directory=Path(__file__).parent / "templates")
app.mount("/generated_images", StaticFiles(directory=IMAGE_DIR), name="generated_images")


def _image_version(filename: str | None) -> int:
    """画像の最終更新時刻を返す。再生成後にブラウザキャッシュを回避するために使う。"""
    if not filename:
        return 0
    path = IMAGE_DIR / filename
    return int(path.stat().st_mtime) if path.exists() else 0


templates.env.globals["image_version"] = _image_version
templates.env.globals["read_only_mode"] = READ_ONLY_MODE


@app.middleware("http")
async def read_only_guard(request: Request, call_next):
    """READ_ONLY_MODE=trueの間は、すべての更新系リクエスト(POST)を無効化する。
    デモ用に不特定多数へ公開したURLで、投稿実行などの操作をされないための安全策。
    """
    if READ_ONLY_MODE and request.method == "POST":
        path = request.url.path
        target = next((t for t in ("/recommendations", "/analytics") if path.startswith(t)), "/posts")
        return RedirectResponse(
            url=f"{target}?error=" + quote("デモ公開環境のため、この操作は無効になっています"),
            status_code=303,
        )
    return await call_next(request)


# 閲覧専用の公開デモは誰でも見られる前提なので、認証は更新操作ができる通常モードでのみ有効にする
AUTH_ENABLED = not READ_ONLY_MODE and auth.admin_credentials() is not None
_PUBLIC_PATHS = {"/login", "/health"}
templates.env.globals["auth_enabled"] = AUTH_ENABLED


def _safe_next(target: str) -> str:
    """ログイン後の遷移先は、サイト内の相対パスのみ許可する(オープンリダイレクト対策)。"""
    if target.startswith("/") and not target.startswith("//"):
        return target
    return "/posts"


@app.middleware("http")
async def require_login(request: Request, call_next):
    if AUTH_ENABLED and request.url.path not in _PUBLIC_PATHS:
        if not request.session.get("user"):
            return RedirectResponse(
                url="/login?next=" + quote(request.url.path), status_code=303
            )
    return await call_next(request)


@app.get("/login")
def login_form(request: Request, next: str = "/posts"):
    return templates.TemplateResponse(
        request=request, name="login.html", context={"error": None, "next": _safe_next(next)}
    )


@app.post("/login")
def login(
    request: Request,
    username: str = Form(...),
    password: str = Form(...),
    next: str = Form("/posts"),
):
    if not auth.verify(username, password):
        return templates.TemplateResponse(
            request=request,
            name="login.html",
            context={"error": "ユーザー名またはパスワードが違います", "next": _safe_next(next)},
            status_code=401,
        )
    request.session["user"] = username
    return RedirectResponse(url=_safe_next(next), status_code=303)


@app.post("/logout")
def logout(request: Request):
    request.session.clear()
    return RedirectResponse(url="/login", status_code=303)


@app.on_event("startup")
def _start_scheduler():
    # 閲覧専用の公開デモでは、意図せず実際のSNSへ自動投稿されないようスケジューラーを起動しない
    if not READ_ONLY_MODE:
        start_scheduler()


app.add_middleware(
    SessionMiddleware,
    secret_key=os.environ.get("SESSION_SECRET") or os.urandom(32).hex(),
    https_only=os.environ.get("SESSION_HTTPS_ONLY", "").lower() == "true",
    same_site="lax",
)


@app.get("/health")
def health_check():
    return {"status": "ok"}


@app.get("/posts")
def list_posts(request: Request, db: Session = Depends(get_db)):
    posts = db.query(models.GeneratedPost).order_by(models.GeneratedPost.id.desc()).all()
    return templates.TemplateResponse(
        request=request, name="posts_list.html", context={"posts": posts}
    )


@app.get("/posts/{post_id}/edit")
def edit_post_form(post_id: int, request: Request, db: Session = Depends(get_db)):
    post = db.get(models.GeneratedPost, post_id)
    return templates.TemplateResponse(
        request=request, name="post_edit.html", context={"post": post}
    )


@app.post("/posts/{post_id}")
def update_post(post_id: int, content: str = Form(...), db: Session = Depends(get_db)):
    post = db.get(models.GeneratedPost, post_id)
    post.content = content
    db.commit()
    return RedirectResponse(url="/posts", status_code=303)


@app.post("/posts/{post_id}/generate-image")
def generate_post_image(
    post_id: int, instruction: str = Form(default=""), db: Session = Depends(get_db)
):
    post = db.get(models.GeneratedPost, post_id)
    try:
        prompt = generate_image_prompt(post.article.title, post.article.body, instruction)
        post.ai_image_path = generate_image(prompt, post.id)
        db.commit()
    except Exception as exc:
        return RedirectResponse(url="/posts?error=" + quote(str(exc)), status_code=303)
    return RedirectResponse(url="/posts", status_code=303)


@app.post("/posts/{post_id}/image-source")
def set_image_source(post_id: int, source: str = Form(...), db: Session = Depends(get_db)):
    post = db.get(models.GeneratedPost, post_id)
    post.image_source = source
    db.commit()
    return RedirectResponse(url="/posts", status_code=303)


@app.post("/posts/{post_id}/approve")
def approve_post(post_id: int, db: Session = Depends(get_db)):
    post = db.get(models.GeneratedPost, post_id)
    post.status = models.PostStatus.APPROVED
    db.commit()
    return RedirectResponse(url="/posts", status_code=303)


@app.post("/posts/{post_id}/publish")
def publish_post(post_id: int, db: Session = Depends(get_db)):
    post = db.get(models.GeneratedPost, post_id)

    try:
        use_ai_image = post.image_source == "ai" and post.ai_image_path
        image_path = str(IMAGE_DIR / post.ai_image_path) if use_ai_image else None
        if post.platform == models.Platform.X:
            external_post_id = post_tweet(
                post.content, post.article.featured_image_url, image_path
            )
        elif post.platform == models.Platform.INSTAGRAM:
            external_post_id = post_to_instagram(
                post.content, post.article.featured_image_url
            )
        else:
            return RedirectResponse(
                url="/posts?error=" + quote("この媒体への投稿はまだ実装されていません"),
                status_code=303,
            )
    except Exception as exc:
        return RedirectResponse(url="/posts?error=" + quote(str(exc)), status_code=303)

    post.status = models.PostStatus.POSTED
    db.add(
        models.PostLog(
            generated_post_id=post.id,
            posted_at=datetime.utcnow(),
            external_post_id=external_post_id,
        )
    )
    db.commit()
    return RedirectResponse(url="/posts", status_code=303)


@app.get("/posts/{post_id}/schedule")
def schedule_form(post_id: int, request: Request, db: Session = Depends(get_db)):
    post = db.get(models.GeneratedPost, post_id)
    return templates.TemplateResponse(
        request=request, name="schedule_form.html", context={"post": post}
    )


@app.post("/posts/{post_id}/schedule")
def create_schedule(
    post_id: int,
    date: str = Form(...),
    time: str = Form(...),
    repeat: str = Form(...),
    repeat_until: str = Form(default=""),
    repeat_until_time: str = Form(default="23:00"),
    custom_weekdays: list[str] = Form(default=[]),
    custom_interval: int = Form(default=1),
    custom_unit: str = Form(default="week"),
    custom_end_type: str = Form(default="none"),
    custom_until: str = Form(default=""),
    custom_count: int | None = Form(default=None),
    db: Session = Depends(get_db),
):
    until_at = None
    if repeat == "custom" and custom_end_type == "until" and custom_until:
        until_at = datetime.fromisoformat(f"{custom_until}T23:59:59")
    elif repeat != "custom" and repeat_until:
        until_at = datetime.fromisoformat(f"{repeat_until}T{repeat_until_time}")

    db.add(
        models.Schedule(
            generated_post_id=post_id,
            scheduled_at=datetime.fromisoformat(f"{date}T{time}"),
            repeat=models.RepeatType(repeat),
            repeat_until=until_at,
            custom_weekdays=",".join(custom_weekdays) if custom_weekdays else None,
            custom_interval=custom_interval,
            custom_unit=custom_unit,
            custom_end_type=custom_end_type,
            custom_count=custom_count if custom_end_type == "count" else None,
        )
    )
    db.commit()
    return RedirectResponse(url="/posts", status_code=303)


@app.post("/schedules/{schedule_id}/cancel")
def cancel_schedule(schedule_id: int, db: Session = Depends(get_db)):
    schedule = db.get(models.Schedule, schedule_id)
    schedule.is_active = False
    db.commit()
    return RedirectResponse(url="/posts", status_code=303)


@app.get("/calendar")
def calendar_page(
    request: Request,
    year: int | None = None,
    month: int | None = None,
    db: Session = Depends(get_db),
):
    today = date.today()
    year = year or today.year
    month = month or today.month

    prev_month = 12 if month == 1 else month - 1
    prev_year = year - 1 if month == 1 else year
    next_month = 1 if month == 12 else month + 1
    next_year = year + 1 if month == 12 else year

    return templates.TemplateResponse(
        request=request,
        name="calendar.html",
        context={
            "weeks": build_calendar(db, year, month),
            "year": year,
            "month": month,
            "prev_year": prev_year,
            "prev_month": prev_month,
            "next_year": next_year,
            "next_month": next_month,
            "today": today if (today.year == year and today.month == month) else None,
        },
    )


@app.get("/analytics")
def analytics_page(request: Request, db: Session = Depends(get_db)):
    return templates.TemplateResponse(
        request=request, name="analytics.html", context={"summary": build_summary(db)}
    )


@app.post("/analytics/refresh")
def refresh_analytics(db: Session = Depends(get_db)):
    try:
        updated = refresh_engagement(db)
    except Exception as exc:
        return RedirectResponse(url="/analytics?error=" + quote(str(exc)), status_code=303)
    return RedirectResponse(
        url="/analytics?notice=" + quote(f"{updated}件の反応数を更新しました"), status_code=303
    )


@app.get("/recommendations")
def recommendations(
    request: Request,
    weekday: int | None = None,
    date: str | None = None,
    db: Session = Depends(get_db),
):
    return templates.TemplateResponse(
        request=request,
        name="recommendations.html",
        context={
            "recommended_times": get_recommended_times(db),
            "repeat_settings": get_repeat_settings(db),
            "repost_candidates": get_repost_candidates(db),
            "days": 14,
            "Platform": models.Platform,
            "weekday_labels": WEEKDAY_LABELS,
            "highlight_weekday": weekday,
            "clicked_date": date,
        },
    )


@app.post("/recommendations/times")
async def save_recommended_times(request: Request, db: Session = Depends(get_db)):
    form = await request.form()
    for platform in models.Platform:
        for weekday in range(7):
            start_field = f"start__{platform.value}__{weekday}"
            end_field = f"end__{platform.value}__{weekday}"
            if start_field in form and end_field in form:
                update_recommended_time(db, platform, weekday, form[start_field], form[end_field])

    for weekday in range(7):
        repeat_field = f"repeat__{weekday}"
        if repeat_field in form:
            enabled = form.get(f"enabled__{weekday}", "on") == "on"
            custom_interval = int(form.get(f"custom_interval__{weekday}", "1") or "1")
            custom_unit = form.get(f"custom_unit__{weekday}", "week")
            update_repeat_setting(
                db, weekday, form[repeat_field], custom_interval, custom_unit, enabled
            )

    return RedirectResponse(url="/recommendations", status_code=303)


@app.post("/recommendations/{article_id}/regenerate")
def regenerate_posts(article_id: int, db: Session = Depends(get_db)):
    article = db.get(models.Article, article_id)
    generated = generate_sns_posts(article.title, article.body)

    db.add(
        models.GeneratedPost(
            article_id=article.id, platform=models.Platform.X, content=generated["x"]
        )
    )
    db.add(
        models.GeneratedPost(
            article_id=article.id,
            platform=models.Platform.INSTAGRAM,
            content=generated["instagram"],
        )
    )
    db.commit()
    return RedirectResponse(url="/posts", status_code=303)
