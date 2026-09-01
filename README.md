# SNS AI運用システム

AIを活用してWordPress記事をSNS(X / Instagram)向けに自動展開する、SNS運用効率化ツールです。実際のクライアント案件の相談内容をもとに、ポートフォリオとして開発しました。

## 背景

SNS運用担当者が抱えがちな「記事は書いたが、SNS投稿文を考える時間がない」「投稿のタイミングやネタ選定に悩む」という課題に対し、AIによるコンテンツ生成とレコメンドで運用工数を削減することを目的としています。

## 主な機能

- **WordPress連携**: WordPress REST APIから記事を取得
- **AI投稿文生成**: Claude APIを使い、記事内容からX用・Instagram用の投稿文をそれぞれ自動生成
- **AI画像生成**: Claudeが記事内容から画像生成用プロンプト(モダンなエディトリアルイラスト調、実在人物の写実描写は禁止)を作成し、OpenAIの画像生成API(`gpt-image-1`)でオリジナル画像を生成
- **承認UI**: AIが生成した下書きを一覧・編集・承認できる画面(AI生成物を無検証で投稿しないための安全策)
- **即時投稿・予約投稿**: 承認済みの投稿をX/Instagramへ即時実行、または日時を指定して予約実行(AI生成画像があればそれを、なければ記事のアイキャッチ画像を自動添付)
  - 繰り返し: 毎日 / 毎週 / 毎週平日 / 毎月 / 毎年 / カスタム(◯日・週間・か月・年ごと、曜日指定、終了日または回数指定)
  - 裏側でスケジューラー(APScheduler)が1分間隔でチェックし、該当時刻になった予約を自動実行
- **カレンダー**: 投稿済み・予約済みの投稿を月表示で確認。日付クリックでその曜日のレコメンド設定へ移動
- **レコメンド**: 曜日ごとにX/Instagramのおすすめ投稿時間帯(開始〜終了)、繰り返し間隔、投稿する/しないを設定。あわせて一定期間投稿されていない記事をリポスト候補として抽出・再生成

## 技術構成

- バックエンド: Python / FastAPI
- DB: SQLite + SQLAlchemy
- スケジューラー: APScheduler(アプリ起動中、1分間隔でバックグラウンド実行)
- AI生成(文章): Anthropic Claude API
- AI生成(画像): OpenAI画像生成API(`gpt-image-1`)
- X投稿: X API v2(tweepy)、画像添付は v1.1 メディアアップロード経由
- Instagram投稿: Instagram Graph API(Meta App Review完了までモック実装で動作)
- 画面: Jinja2テンプレートによるサーバーサイドレンダリング

## 画面・エンドポイント

| パス | 内容 |
|---|---|
| `/posts` | 投稿の一覧・編集・承認・即時投稿・予約設定 |
| `/posts/{id}/schedule` | 予約投稿の設定(開始日時・繰り返し) |
| `/calendar` | 投稿済み・予約済み投稿のカレンダー表示 |
| `/recommendations` | 曜日別のおすすめ投稿時間帯・繰り返し設定、リポスト候補の一覧・再生成 |
| `/health` | ヘルスチェック |

## セットアップ

```bash
python -m venv venv
.\venv\Scripts\Activate.ps1   # Windows PowerShellの場合
pip install -r requirements.txt
```

`.env.example`を参考に`.env`を作成し、各APIキーを設定してください。

```
X_API_KEY=
X_API_KEY_SECRET=
X_ACCESS_TOKEN=
X_ACCESS_TOKEN_SECRET=
ANTHROPIC_API_KEY=
OPENAI_API_KEY=                  # AI画像生成に使用
WP_SITE_URL=                     # 未設定時はWordPress公式ニュースブログを使用
INSTAGRAM_ACCESS_TOKEN=          # 未設定時はモック応答
INSTAGRAM_BUSINESS_ACCOUNT_ID=   # 未設定時はモック応答
```

サーバー起動:

```bash
uvicorn app.main:app --reload
```

`http://127.0.0.1:8000/posts` にアクセスして画面を確認できます。サーバー起動中は予約投稿のスケジューラーもバックグラウンドで動作します。

パイプラインを1回実行(記事取得→AI生成→DB保存)する場合:

```bash
python run_pipeline.py
```

## 現状の制約・今後の展望

- **Instagram投稿はモック実装**です。Meta社のApp Review(`instagram_content_publish`権限)が完了し、`.env`に`INSTAGRAM_ACCESS_TOKEN`と`INSTAGRAM_BUSINESS_ACCOUNT_ID`を設定すると、コード変更なしに本番のGraph API呼び出しへ自動的に切り替わります。
- レコメンド機能は現状ルールベースです。運用データが蓄積された後、エンゲージメント実績(いいね数・クリック率など)に基づくロジックへの拡張を想定しています。
- WordPress連携は`WP_SITE_URL`で対象サイトを切り替え可能です(未設定時はデモとしてWordPress公式ニュースブログを使用)。
- 予約投稿の自動実行は、アプリケーション(uvicorn)が起動している間のみ動作します。本番運用時は常時起動するサーバー上への配置を想定しています。
