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


IMAGE_PROMPT_SYSTEM = """あなたは一流メディアのアートディレクターです。渡された記事の内容をもとに、
SNS投稿用の画像を作る画像生成AIへの指示文(英語)を1つだけ出力してください。

必ず守るルール:
- 実在する人物の顔や容姿を写実的に描写しないこと(実名の人物が記事に含まれる場合も、本人を特定できる写実的描写は避ける)
- スタイルは「モダンな編集デザイン誌のエディトリアルイラスト」。具体的には、太い輪郭線と大胆な色面によるフラットデザイン、または洗練されたジオメトリックな構成のどちらか
- 配色は2〜4色程度に絞った、彩度を抑えた洗練されたパレットにすること(例: 深いネイビー×マスタード、テラコッタ×チャコールなど)。虹色・パステル・金色に光る演出は使わないこと
- 蝶・ハート・キラキラ・グロー効果・過度に感傷的な演出、ありきたりなグリーティングカード風の表現は避けること
- 記事のテーマを象徴する、シンプルで力強い1〜2個のモチーフに絞った構成にすること。ごちゃごちゃと物を並べた説明的なシーンにしないこと
- 文字やロゴ、透かしを画像内に含めないこと
- 説明文や前置きは含めず、画像生成プロンプトの本文のみを出力すること
"""


def generate_image_prompt(title: str, body: str) -> str:
    user_message = f"タイトル: {title}\n\n本文:\n{body[:1000]}"

    response = client.messages.create(
        model="claude-opus-5",
        max_tokens=300,
        system=IMAGE_PROMPT_SYSTEM,
        messages=[{"role": "user", "content": user_message}],
    )

    return "".join(block.text for block in response.content if block.type == "text").strip()
