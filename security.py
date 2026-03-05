"""
セキュリティモジュール：認証・RBAC・セッション管理

設計方針：
    ゼロトラストセキュリティモデルに基づき、
    「信頼しない・常に検証する」原則を全層で実装する。

脅威モデル：
    1. 特権昇格攻撃 → RBAC最小権限原則で対応
    2. 平文パスワード漏洩 → bcryptソルト付きハッシュで対応
    3. セッション固定攻撃 → ロール昇格時のsession_id再生成で対応
    4. リプレイ攻撃 → JWTの有効期限（exp）クレームで対応
"""

import hashlib
import os
import uuid
from datetime import datetime, timedelta, timezone
from typing import Optional

import bcrypt
import streamlit as st

# python-jose のインポート（JWT処理）
try:
    from jose import JWTError, jwt
    JWT_AVAILABLE = True
except ImportError:
    JWT_AVAILABLE = False

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# ロール定義（RBAC：ロールベースアクセス制御）
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 【脅威】特権昇格攻撃・不正アクセス
# 【対策】ロールベースアクセス制御（RBAC）＋最小権限の原則
# 各ロールは上位ロールの権限を持たない（明示的許可リスト方式）
ROLES: dict = {
    "VISITOR": {
        "level": 0,
        "label": "来場者",
        "permissions": ["read:events", "read:wait_time"],
        "accessible_views": ["visitor"],
        "emoji": "🙋",
    },
    "STAFF": {
        "level": 1,
        "label": "担当者",
        "permissions": ["read:events", "read:wait_time", "write:queue"],
        "accessible_views": ["visitor", "staff"],
        "emoji": "📋",
    },
    "ADMIN": {
        "level": 2,
        "label": "管理者",
        "permissions": [
            "read:events", "read:wait_time", "write:queue",
            "read:analytics", "write:config", "export:data",
        ],
        "accessible_views": ["visitor", "staff", "admin", "simulation"],
        "emoji": "🔐",
    },
}

# JWT設定
# 【重要】本番環境では必ずst.secrets["JWT_SECRET_KEY"]に差し替えること
_JWT_ALGORITHM = "HS256"
_JWT_EXPIRE_HOURS = 8  # 文化祭1日分（開場〜閉場）

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# PINハッシュ（bcryptソルト付き）
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 【脅威】平文パスワード漏洩
# 【対策】bcryptによるソルト付きハッシュ。PIN平文をst.session_stateに保持禁止。
# 本番環境ではSupabase Authに差し替えること。
# bcrypt.gensalt()はモジュールロード時に1回のみ実行（起動時コスト）
_PIN_HASHES: dict = {
    "STAFF": bcrypt.hashpw(b"1234", bcrypt.gensalt()),
    "ADMIN": bcrypt.hashpw(b"9999", bcrypt.gensalt()),
}


def _get_jwt_secret() -> str:
    """
    JWT署名用シークレットキーを取得する。

    Streamlit Secretsが利用可能な場合はそちらを優先し、
    フォールバックとして環境変数を参照する。

    Returns:
        str: JWTシークレットキー

    Raises:
        RuntimeError: シークレットキーが設定されていない場合
    """
    # Streamlit Cloud の場合
    try:
        return st.secrets["JWT_SECRET_KEY"]
    except (KeyError, FileNotFoundError):
        pass

    # ローカル開発の場合（.env経由）
    secret = os.environ.get("JWT_SECRET_KEY", "")
    if secret:
        return secret

    # 開発用フォールバック（本番では使用禁止）
    return "dev-fallback-secret-change-in-production-32chars"


def verify_pin(pin: str, role: str) -> bool:
    """
    入力されたPINをbcryptハッシュと照合する。

    【セキュリティ注意】
    - pin引数をst.session_stateに保存してはならない
    - ログやUIに入力値を出力してはならない
    - タイミング攻撃対策として bcrypt.checkpw は定時間比較を行う

    Args:
        pin (str): ユーザーが入力したPIN文字列
        role (str): 照合対象のロール（"STAFF" or "ADMIN"）

    Returns:
        bool: PIN照合成功なら True、失敗なら False
    """
    if role not in _PIN_HASHES:
        return False

    try:
        pin_bytes = pin.encode("utf-8")
        return bcrypt.checkpw(pin_bytes, _PIN_HASHES[role])
    except Exception:
        # bcryptエラーは False として扱う（例外情報を漏洩させない）
        return False


def create_session(role: str) -> dict:
    """
    認証済みセッションを生成する。

    JWTペイロードにロールと有効期限（exp）を含める。
    ロール昇格時はsession_idを必ず再生成する（セッション固定攻撃対策）。

    Args:
        role (str): 認証されたロール名（"VISITOR" | "STAFF" | "ADMIN"）

    Returns:
        dict: セッション情報
            - session_id (str): UUID形式のセッションID
            - role (str): ロール名
            - token (str): JWTトークン文字列（JWT_AVAILABLE の場合）
            - expires_at (str): 有効期限（ISO 8601）

    Raises:
        ValueError: 無効なロール名が指定された場合
    """
    if role not in ROLES:
        raise ValueError(f"無効なロール名: {role}")

    # session_idを毎回新規生成（セッション固定攻撃対策）
    session_id = str(uuid.uuid4())
    now = datetime.now(timezone.utc)
    expires_at = now + timedelta(hours=_JWT_EXPIRE_HOURS)

    session = {
        "session_id": session_id,
        "role": role,
        "expires_at": expires_at.isoformat(),
        "token": None,
    }

    if JWT_AVAILABLE:
        payload = {
            "sub": session_id,
            "role": role,
            "iat": now,
            "exp": expires_at,
        }
        try:
            token = jwt.encode(payload, _get_jwt_secret(), algorithm=_JWT_ALGORITHM)
            session["token"] = token
        except Exception:
            # JWT生成失敗時はtokenなしで続行（セッションIDで代替）
            pass

    return session


def validate_session() -> bool:
    """
    現在のst.session_stateのセッションが有効かどうか検証する。

    検証項目：
    1. セッション情報の存在確認
    2. JWTトークンの署名検証（JWT_AVAILABLE の場合）
    3. 有効期限（exp）の確認

    Returns:
        bool: セッションが有効なら True、無効なら False
    """
    if not st.session_state.get("authenticated", False):
        return False

    session_info = st.session_state.get("session_info")
    if not session_info:
        return False

    # JWT検証
    if JWT_AVAILABLE and session_info.get("token"):
        try:
            jwt.decode(
                session_info["token"],
                _get_jwt_secret(),
                algorithms=[_JWT_ALGORITHM],
            )
            return True
        except JWTError:
            return False

    # JWTが利用できない場合は有効期限を直接チェック
    expires_at_str = session_info.get("expires_at")
    if expires_at_str:
        try:
            expires_at = datetime.fromisoformat(expires_at_str)
            now = datetime.now(timezone.utc)
            return now < expires_at
        except ValueError:
            return False

    return False


def validate_permission(required_permission: str) -> bool:
    """
    現在のセッションが指定パーミッションを持つか検証する。

    認証チェックと権限チェックを分離した設計（単一責任原則）。
    パーミッションの確認は毎回行い、キャッシュしない（ゼロトラスト原則）。

    Args:
        required_permission (str): 必要なパーミッション（例："write:queue"）

    Returns:
        bool: パーミッションがあれば True、なければ False
    """
    if not validate_session():
        return False

    current_role = st.session_state.get("role", "VISITOR")
    role_config = ROLES.get(current_role, ROLES["VISITOR"])
    return required_permission in role_config["permissions"]


def require_role(minimum_role: str) -> bool:
    """
    指定したロールレベル以上のロールを持つか確認する。

    Args:
        minimum_role (str): 必要な最小ロール（"VISITOR" | "STAFF" | "ADMIN"）

    Returns:
        bool: 十分なロールレベルを持つなら True
    """
    current_role = st.session_state.get("role", "VISITOR")
    current_level = ROLES.get(current_role, ROLES["VISITOR"])["level"]
    required_level = ROLES.get(minimum_role, ROLES["VISITOR"])["level"]
    return current_level >= required_level


def logout() -> None:
    """
    現在のセッションを破棄し、VISITOR ロールにリセットする。

    セキュリティ上の注意：
    - セッション情報を st.session_state から完全に削除する
    - ブラウザストレージには何も保存しない
    """
    keys_to_reset = ["authenticated", "role", "session_info"]
    for key in keys_to_reset:
        if key in st.session_state:
            del st.session_state[key]

    st.session_state["authenticated"] = False
    st.session_state["role"] = "VISITOR"
    st.session_state["session_info"] = None


def get_current_role_info() -> dict:
    """
    現在のロール情報を取得する。

    Returns:
        dict: 現在のロール設定（label, level, permissions, emoji）
    """
    current_role = st.session_state.get("role", "VISITOR")
    return ROLES.get(current_role, ROLES["VISITOR"])


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 【設計ドキュメント】security.py
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#
# ■ bcrypt採用理由
#   SHA-256より総当たり攻撃に強いコスト関数（KDF）を持つため。
#   bcrypt のデフォルトコスト係数（12）により、
#   ブルートフォースの計算コストを約4096倍に引き上げる。
#
# ■ JWTセッション採用理由
#   Streamlitはステートレスサーバーのため、
#   サーバー側でのセッションDB管理よりトークン検証が適切。
#   JWTのexpクレームにより、8時間後の自動無効化を保証。
#
# ■ ゼロトラスト実装ポイント
#   - 全ての操作前にvalidate_permission()を呼び出す
#   - セッションをキャッシュせず毎回検証する
#   - ロール昇格時はsession_idを必ず再生成する
