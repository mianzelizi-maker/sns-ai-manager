import html
import os
import re

import requests
from dotenv import load_dotenv

load_dotenv()

WP_SITE_URL = os.environ.get("WP_SITE_URL", "https://wordpress.org/news").rstrip("/")


def _strip_html(raw_html: str) -> str:
    text = re.sub(r"<[^>]+>", "", raw_html)
    return html.unescape(text).strip()


def fetch_latest_posts(limit: int = 3) -> list[dict]:
    response = requests.get(
        f"{WP_SITE_URL}/wp-json/wp/v2/posts",
        params={"per_page": limit, "_embed": "1"},
        timeout=10,
    )
    response.raise_for_status()

    posts = []
    for item in response.json():
        featured_image_url = None
        embedded_media = item.get("_embedded", {}).get("wp:featuredmedia")
        if embedded_media:
            featured_image_url = embedded_media[0].get("source_url")

        posts.append(
            {
                "wp_post_id": item["id"],
                "title": _strip_html(item["title"]["rendered"]),
                "body": _strip_html(item["content"]["rendered"]),
                "featured_image_url": featured_image_url,
            }
        )

    return posts
