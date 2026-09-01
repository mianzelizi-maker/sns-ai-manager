import os

import tweepy
from dotenv import load_dotenv

load_dotenv()

client = tweepy.Client(
    consumer_key=os.environ["X_API_KEY"],
    consumer_secret=os.environ["X_API_KEY_SECRET"],
    access_token=os.environ["X_ACCESS_TOKEN"],
    access_token_secret=os.environ["X_ACCESS_TOKEN_SECRET"],
)

response = client.create_tweet(text="AI SNS運用システム 動作確認テスト投稿")
print("投稿成功。ツイートID:", response.data["id"])
