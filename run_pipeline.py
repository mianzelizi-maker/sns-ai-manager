from app import models
from app.ai_generator import generate_sns_posts
from app.database import Base, SessionLocal, engine
from app.wordpress_client import fetch_latest_posts

Base.metadata.create_all(bind=engine)

db = SessionLocal()

posts = fetch_latest_posts(limit=1)
if not posts:
    print("WordPress記事が取得できませんでした。")
    raise SystemExit(1)

wp_post = posts[0]
print("--- 取得した記事 ---")
print("タイトル:", wp_post["title"])
print("本文(先頭100文字):", wp_post["body"][:100])
print()

existing = db.query(models.Article).filter_by(wp_post_id=wp_post["wp_post_id"]).first()
if existing:
    print(f"記事はすでにDBに保存済みです(article_id: {existing.id})。生成をスキップします。")
    db.close()
    raise SystemExit(0)

article = models.Article(
    wp_post_id=wp_post["wp_post_id"],
    title=wp_post["title"],
    body=wp_post["body"],
    featured_image_url=wp_post["featured_image_url"],
)
db.add(article)
db.flush()

generated = generate_sns_posts(wp_post["title"], wp_post["body"])

print("--- X用投稿文(下書き) ---")
print(generated["x"])
print()
print("--- Instagram用投稿文(下書き) ---")
print(generated["instagram"])

db.add(
    models.GeneratedPost(
        article_id=article.id,
        platform=models.Platform.X,
        content=generated["x"],
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
article_id = article.id
db.close()

print()
print(f"記事(article_id: {article_id})と、2件の下書き投稿(status: draft)をDBに保存しました。")
