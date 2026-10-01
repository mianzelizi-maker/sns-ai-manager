import hmac
import os


def admin_credentials() -> tuple[str, str] | None:
    """ADMIN_PASSWORDが設定されている場合のみ認証を有効にする。
    未設定ならローカル開発向けに認証なしで動く。
    """
    password = os.environ.get("ADMIN_PASSWORD")
    if not password:
        return None
    return os.environ.get("ADMIN_USERNAME", "admin"), password


def verify(username: str, password: str) -> bool:
    credentials = admin_credentials()
    if credentials is None:
        return False
    expected_user, expected_password = credentials
    # 比較時間から内容を推測されないよう、定数時間で比較する
    user_ok = hmac.compare_digest(username.encode(), expected_user.encode())
    password_ok = hmac.compare_digest(password.encode(), expected_password.encode())
    return user_ok and password_ok
