import os

import anthropic
from dotenv import load_dotenv

load_dotenv()

client = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])

SYSTEM_PROMPT = """あなたはSNS運用担当者です。渡された記事の内容から、X(旧Twitter)とInstagram向けの投稿文をそれぞれ作成してください。

出力は必ず以下の形式で、余計な説明を含めないでください。

[X]
(ここにX用の投稿文。140字以内、ハッシュタグを1〜2個含める)

[Instagram]
(ここにInstagram用のキャプション。文章は少し長めでOK。最後にハッシュタグを3〜5個含める)
"""


def generate_sns_posts(title: str, body: str) -> dict:
    user_message = f"タイトル: {title}\n\n本文:\n{body}"

    response = client.messages.create(
        model="claude-opus-5",
        max_tokens=1024,
        system=SYSTEM_PROMPT,
        messages=[{"role": "user", "content": user_message}],
    )

    text = "".join(block.text for block in response.content if block.type == "text")

    if "[Instagram]" in text:
        x_part, instagram_part = text.split("[Instagram]", 1)
        x_post = x_part.replace("[X]", "").strip()
        instagram_post = instagram_part.strip()
    else:
        x_post = text.strip()
        instagram_post = ""

    return {"x": x_post, "instagram": instagram_post}
