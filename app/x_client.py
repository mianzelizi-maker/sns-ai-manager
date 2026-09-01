import io
import logging
import os

import requests
import tweepy
from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger("x_client")


def _oauth1_api() -> tweepy.API:
    auth = tweepy.OAuth1UserHandler(
        os.environ["X_API_KEY"],
        os.environ["X_API_KEY_SECRET"],
        os.environ["X_ACCESS_TOKEN"],
        os.environ["X_ACCESS_TOKEN_SECRET"],
    )
    return tweepy.API(auth)


def _v2_client() -> tweepy.Client:
    return tweepy.Client(
        consumer_key=os.environ["X_API_KEY"],
        consumer_secret=os.environ["X_API_KEY_SECRET"],
        access_token=os.environ["X_ACCESS_TOKEN"],
        access_token_secret=os.environ["X_ACCESS_TOKEN_SECRET"],
    )


def _upload_image(image_url: str) -> str | None:
    try:
        response = requests.get(image_url, timeout=15)
        response.raise_for_status()
        media = _oauth1_api().media_upload(
            filename="image.jpg", file=io.BytesIO(response.content)
        )
        return media.media_id
    except Exception:
        logger.exception("画像のアップロードに失敗したため、テキストのみで投稿します")
        return None


def post_tweet(content: str, image_url: str | None = None) -> str:
    media_ids = None
    if image_url:
        media_id = _upload_image(image_url)
        if media_id:
            media_ids = [media_id]

    response = _v2_client().create_tweet(text=content, media_ids=media_ids)
    return response.data["id"]
