import os
import uuid

import requests
from dotenv import load_dotenv

load_dotenv()

GRAPH_API_BASE = "https://graph.facebook.com/v21.0"


def post_to_instagram(caption: str, image_url: str | None) -> str:
    access_token = os.environ.get("INSTAGRAM_ACCESS_TOKEN")
    ig_user_id = os.environ.get("INSTAGRAM_BUSINESS_ACCOUNT_ID")

    if not access_token or not ig_user_id:
        # Meta App Review(instagram_content_publish)が未完了のため、
        # 認証情報が揃うまでは実際のAPIを呼ばずモック応答を返す。
        # .envにINSTAGRAM_ACCESS_TOKEN / INSTAGRAM_BUSINESS_ACCOUNT_IDを設定すれば、
        # 下の本番コードが自動的に使われるようになる。
        return f"mock_{uuid.uuid4().hex[:12]}"

    container_response = requests.post(
        f"{GRAPH_API_BASE}/{ig_user_id}/media",
        data={
            "image_url": image_url,
            "caption": caption,
            "access_token": access_token,
        },
        timeout=15,
    )
    container_response.raise_for_status()
    creation_id = container_response.json()["id"]

    publish_response = requests.post(
        f"{GRAPH_API_BASE}/{ig_user_id}/media_publish",
        data={
            "creation_id": creation_id,
            "access_token": access_token,
        },
        timeout=15,
    )
    publish_response.raise_for_status()
    return publish_response.json()["id"]
