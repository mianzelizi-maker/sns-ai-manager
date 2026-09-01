from app import models
from app.ai_generator import generate_sns_posts
from app.database import Base, SessionLocal, engine

Base.metadata.create_all(bind=engine)

SAMPLE_TITLE = "在宅ワークを効率化する5つのツール"
SAMPLE_BODY = (
    "リモートワークが定着する中、作業効率を上げるツール選びが重要になっています。"
    "本記事では、タスク管理・オンライン会議・ファイル共有の3分野から、"
    "特におすすめのツールを5つ厳選して紹介します。"
)

result = generate_sns_posts(SAMPLE_TITLE, SAMPLE_BODY)

print("--- X用投稿文 ---")
print(result["x"])
print()
print("--- Instagram用投稿文 ---")
print(result["instagram"])

db = SessionLocal()
article = models.Article(
    wp_post_id=9999,
    title=SAMPLE_TITLE,
    body=SAMPLE_BODY,
)
db.add(article)
db.flush()

db.add(
    models.GeneratedPost(
        article_id=article.id,
        platform=models.Platform.X,
        content=result["x"],
    )
)
db.add(
    models.GeneratedPost(
        article_id=article.id,
        platform=models.Platform.INSTAGRAM,
        content=result["instagram"],
    )
)
db.commit()
article_id = article.id
db.close()

print()
print("DBへの保存も完了しました(article_id:", article_id, ")")
