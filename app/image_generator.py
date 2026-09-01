import base64
import os
from pathlib import Path

from dotenv import load_dotenv
from openai import OpenAI

load_dotenv()

client = OpenAI(api_key=os.environ["OPENAI_API_KEY"])

IMAGE_DIR = Path(__file__).parent.parent / "generated_images"
IMAGE_DIR.mkdir(exist_ok=True)


def generate_image(prompt: str, post_id: int) -> str:
    """画像を生成してファイルに保存し、ファイル名(generated_images配下の相対名)を返す。"""
    response = client.images.generate(
        model="gpt-image-1",
        prompt=prompt,
        size="1024x1024",
    )
    image_bytes = base64.b64decode(response.data[0].b64_json)

    filename = f"post_{post_id}.png"
    (IMAGE_DIR / filename).write_bytes(image_bytes)

    return filename
