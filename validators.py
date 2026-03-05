"""
入力バリデーション・異常値検知エンジン

設計方針：
    【脅威】DoS攻撃・データ改ざん・SQLインジェクション
    【対策】型チェック・範囲チェック・急激な変化検知・パラメータバインディング

    全てのユーザー入力はこのモジュールを経由させること。
    UIレイヤー（views/）から直接データ層（data_manager.py）へのアクセスは禁止。
"""

from dataclasses import dataclass, field
from datetime import datetime, time
from typing import Any, Optional


@dataclass
class ValidationResult:
    """
    バリデーション結果を保持するデータクラス。

    Attributes:
        is_valid (bool): バリデーション通過フラグ
        value (Optional[int]): バリデーション済みの値（失敗時はNone）
        errors (list[str]): エラーメッセージリスト（複数エラー対応）
        warnings (list[str]): 警告メッセージリスト（anomaly detectionなど）
        requires_admin_alert (bool): 管理者通知が必要なフラグ
    """
    is_valid: bool
    value: Optional[int] = None
    errors: list = field(default_factory=list)
    warnings: list = field(default_factory=list)
    requires_admin_alert: bool = False


# バリデーション定数
QUEUE_LENGTH_MIN: int = 0
QUEUE_LENGTH_MAX: int = 500      # DoS対策：現実的な上限値
ANOMALY_THRESHOLD: int = 100     # 急激な変化検知閾値（前回比±人）
OPENING_HOUR: int = 9            # 開場時刻（9:00）
CLOSING_HOUR: int = 18           # 閉場時刻（18:00）


def validate_queue_input(
    value: Any,
    current_value: int,
    event_name: str = "",
    check_operating_hours: bool = True,
) -> ValidationResult:
    """
    行列人数入力の全バリデーションを実施する。

    チェック項目（優先度順）：
    1. 型チェック（整数に変換可能か）
    2. 範囲チェック（0〜500：DoS対策）
    3. 急激な変化検知（前回比±100人以上で管理者警告フラグ）
    4. 営業時間内チェック（開場・閉場時刻との整合）

    Args:
        value (Any): ユーザーが入力した値（未検証）
        current_value (int): 現在登録されている行列人数
        event_name (str): イベント名（エラーメッセージ用）
        check_operating_hours (bool): 営業時間チェックを行うか

    Returns:
        ValidationResult: バリデーション結果

    Examples:
        >>> result = validate_queue_input("abc", 50)
        >>> result.is_valid
        False
        >>> result.errors[0]
        '行列人数は整数で入力してください'

        >>> result = validate_queue_input(200, 50)
        >>> result.warnings[0]
        '前回比+150人の急激な変化です...'
        >>> result.requires_admin_alert
        True
    """
    errors: list[str] = []
    warnings: list[str] = []
    requires_admin_alert: bool = False

    # ── チェック1: 型チェック ──────────────────────────
    try:
        int_value = int(value)
    except (TypeError, ValueError):
        return ValidationResult(
            is_valid=False,
            value=None,
            errors=["行列人数は整数で入力してください"],
        )

    # ── チェック2: 範囲チェック ────────────────────────
    if int_value < QUEUE_LENGTH_MIN:
        errors.append(
            f"行列人数は{QUEUE_LENGTH_MIN}人以上で入力してください（入力値: {int_value}）"
        )
    elif int_value > QUEUE_LENGTH_MAX:
        errors.append(
            f"行列人数は{QUEUE_LENGTH_MAX}人以下で入力してください（DoS対策上限）"
        )

    if errors:
        return ValidationResult(is_valid=False, value=None, errors=errors)

    # ── チェック3: 急激な変化検知 ──────────────────────
    change = int_value - current_value
    abs_change = abs(change)

    if abs_change >= ANOMALY_THRESHOLD:
        direction = "+" if change > 0 else ""
        event_label = f"「{event_name}」" if event_name else ""
        warnings.append(
            f"⚠️ {event_label}前回比{direction}{change}人の急激な変化です。"
            f"管理者に確認が通知されます。"
        )
        requires_admin_alert = True

    # ── チェック4: 営業時間内チェック ─────────────────
    if check_operating_hours and int_value > 0:
        now = datetime.now().time()
        opening_time = time(OPENING_HOUR, 0)
        closing_time = time(CLOSING_HOUR, 0)

        if now < opening_time or now > closing_time:
            warnings.append(
                f"⚠️ 営業時間外（{OPENING_HOUR}:00〜{CLOSING_HOUR}:00）の"
                f"行列入力です。意図的な入力であれば問題ありません。"
            )

    return ValidationResult(
        is_valid=True,
        value=int_value,
        errors=errors,
        warnings=warnings,
        requires_admin_alert=requires_admin_alert,
    )


def validate_service_time(value: Any) -> ValidationResult:
    """
    平均サービス時間のバリデーションを行う。

    Args:
        value (Any): ユーザーが入力した値（未検証）

    Returns:
        ValidationResult: バリデーション結果（値の単位は分）
    """
    try:
        float_value = float(value)
    except (TypeError, ValueError):
        return ValidationResult(
            is_valid=False,
            errors=["サービス時間は数値で入力してください"],
        )

    if float_value <= 0:
        return ValidationResult(
            is_valid=False,
            errors=["サービス時間は0より大きい値を入力してください"],
        )

    if float_value > 120:
        return ValidationResult(
            is_valid=False,
            errors=["サービス時間は120分以下で入力してください"],
        )

    return ValidationResult(is_valid=True, value=int(float_value))


def validate_pin(pin: str) -> ValidationResult:
    """
    PIN入力のバリデーションを行う。

    【セキュリティ注意】
    - PIN値の内容をエラーメッセージに含めてはならない
    - ログやst.write()にPIN値を出力してはならない

    Args:
        pin (str): ユーザーが入力したPIN文字列

    Returns:
        ValidationResult: バリデーション結果
    """
    if not pin:
        return ValidationResult(
            is_valid=False,
            errors=["PINを入力してください"],
        )

    # 長さチェック（ブルートフォース対策ではなく、入力ミス検知）
    if len(pin) < 4:
        return ValidationResult(
            is_valid=False,
            errors=["PINは4桁以上で入力してください"],
        )

    if len(pin) > 20:
        return ValidationResult(
            is_valid=False,
            errors=["PINが長すぎます"],
        )

    # 数字のみか確認（文化祭PINは数字のみを想定）
    if not pin.isdigit():
        return ValidationResult(
            is_valid=False,
            errors=["PINは数字のみで入力してください"],
        )

    # バリデーション通過（PIN照合はsecurity.pyで実施）
    return ValidationResult(is_valid=True)


def sanitize_text_input(text: str, max_length: int = 100) -> str:
    """
    テキスト入力のサニタイズ処理。

    【XSS対策】
    HTMLタグとスクリプトインジェクション用の文字を除去する。
    unsafe_allow_html=True でレンダリングするコンテンツには
    このサニタイズを必ず適用すること。

    Args:
        text (str): サニタイズ対象のテキスト
        max_length (int): 最大文字数（デフォルト100文字）

    Returns:
        str: サニタイズ済みテキスト
    """
    if not isinstance(text, str):
        return ""

    # 長さ制限
    text = text[:max_length]

    # HTMLタグの無効化（< > をHTMLエンティティに変換）
    text = text.replace("&", "&amp;")
    text = text.replace("<", "&lt;")
    text = text.replace(">", "&gt;")
    text = text.replace('"', "&quot;")
    text = text.replace("'", "&#x27;")

    return text.strip()


def validate_export_request(role: str) -> ValidationResult:
    """
    CSVエクスポートリクエストの権限バリデーション。

    Args:
        role (str): リクエスト元のロール

    Returns:
        ValidationResult: バリデーション結果
    """
    if role != "ADMIN":
        return ValidationResult(
            is_valid=False,
            errors=["データエクスポートは管理者のみ実行できます"],
        )
    return ValidationResult(is_valid=True)
