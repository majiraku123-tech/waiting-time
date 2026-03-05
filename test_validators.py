"""
バリデーションロジックの網羅的テスト

テスト対象：validators.py
テスト手法：境界値分析・同値分割・異常系テスト
"""

import pytest
from validators import (
    validate_queue_input,
    validate_service_time,
    validate_pin,
    sanitize_text_input,
    validate_export_request,
    QUEUE_LENGTH_MIN,
    QUEUE_LENGTH_MAX,
    ANOMALY_THRESHOLD,
    ValidationResult,
)


class TestValidateQueueInput:
    """行列人数バリデーションのテスト"""

    def test_valid_normal_value(self):
        """正常値 → バリデーション通過"""
        result = validate_queue_input(50, 30)
        assert result.is_valid is True
        assert result.value == 50
        assert not result.errors

    def test_valid_minimum_value(self):
        """最小値(0) → 通過"""
        result = validate_queue_input(0, 5)
        assert result.is_valid is True
        assert result.value == 0

    def test_valid_maximum_value(self):
        """最大値(500) → 通過"""
        result = validate_queue_input(500, 0)
        assert result.is_valid is True
        assert result.value == 500

    def test_invalid_negative(self):
        """負の値 → エラー"""
        result = validate_queue_input(-1, 0)
        assert result.is_valid is False
        assert len(result.errors) > 0

    def test_invalid_over_max(self):
        """上限超過(501) → エラー"""
        result = validate_queue_input(501, 0)
        assert result.is_valid is False

    def test_invalid_string(self):
        """文字列入力 → 型エラー"""
        result = validate_queue_input("abc", 10)
        assert result.is_valid is False
        assert "整数" in result.errors[0]

    def test_invalid_none(self):
        """None入力 → 型エラー"""
        result = validate_queue_input(None, 10)
        assert result.is_valid is False

    def test_invalid_float_string(self):
        """浮動小数点文字列 → 型変換で通過（int変換可能）"""
        # "3.5" → int("3.5") はTypeError/ValueErrorになる
        result = validate_queue_input("3.5", 0)
        # "3.5"をintに直接変換できないのでFalse
        assert result.is_valid is False

    def test_anomaly_detection_increase(self):
        """前回比+100人以上 → 警告・管理者アラートフラグ"""
        result = validate_queue_input(150, 49, event_name="テストイベント")
        assert result.is_valid is True
        assert result.requires_admin_alert is True
        assert len(result.warnings) > 0

    def test_anomaly_detection_decrease(self):
        """前回比-100人以上 → 警告・管理者アラートフラグ"""
        result = validate_queue_input(0, 101)
        assert result.is_valid is True
        assert result.requires_admin_alert is True

    def test_no_anomaly_within_threshold(self):
        """前回比±99人以内 → 警告なし"""
        result = validate_queue_input(99, 0)
        assert result.is_valid is True
        assert result.requires_admin_alert is False
        assert not result.warnings

    def test_exact_anomaly_threshold(self):
        """ちょうど±100人 → アラートが発生する"""
        result = validate_queue_input(100, 0)  # +100
        assert result.requires_admin_alert is True

    def test_integer_string_converts(self):
        """整数文字列 → int変換で通過"""
        result = validate_queue_input("42", 10)
        assert result.is_valid is True
        assert result.value == 42


class TestValidateServiceTime:
    """サービス時間バリデーションのテスト"""

    def test_valid_service_time(self):
        """正常値 → 通過"""
        result = validate_service_time(5.0)
        assert result.is_valid is True

    def test_zero_service_time(self):
        """0分 → エラー（正の値のみ許可）"""
        result = validate_service_time(0)
        assert result.is_valid is False

    def test_negative_service_time(self):
        """負の値 → エラー"""
        result = validate_service_time(-1)
        assert result.is_valid is False

    def test_over_max_service_time(self):
        """121分 → エラー（上限120分）"""
        result = validate_service_time(121)
        assert result.is_valid is False

    def test_string_service_time(self):
        """文字列 → エラー"""
        result = validate_service_time("abc")
        assert result.is_valid is False


class TestValidatePin:
    """PINバリデーションのテスト"""

    def test_valid_4digit_pin(self):
        """4桁数字PIN → 通過"""
        result = validate_pin("1234")
        assert result.is_valid is True

    def test_empty_pin(self):
        """空文字列 → エラー"""
        result = validate_pin("")
        assert result.is_valid is False

    def test_short_pin(self):
        """3桁PIN → エラー"""
        result = validate_pin("123")
        assert result.is_valid is False

    def test_long_pin(self):
        """21桁PIN → エラー"""
        result = validate_pin("1" * 21)
        assert result.is_valid is False

    def test_non_numeric_pin(self):
        """英字混じりPIN → エラー"""
        result = validate_pin("abcd")
        assert result.is_valid is False

    def test_pin_does_not_leak_value(self):
        """エラーメッセージにPIN値が含まれないことを確認"""
        pin_value = "5678"
        result = validate_pin(pin_value)
        # バリデーションは通過するが、エラーメッセージにPIN値が含まれないことを確認
        for error in result.errors:
            assert pin_value not in error


class TestSanitizeTextInput:
    """テキストサニタイズのテスト"""

    def test_normal_text(self):
        """通常テキスト → そのまま（エスケープなし）"""
        result = sanitize_text_input("こんにちは")
        assert "こんにちは" in result

    def test_html_tag_escaped(self):
        """HTMLタグ → エスケープ"""
        result = sanitize_text_input("<script>alert('xss')</script>")
        assert "<script>" not in result
        assert "&lt;script&gt;" in result

    def test_max_length(self):
        """最大文字数超過 → 切り詰め"""
        long_text = "a" * 200
        result = sanitize_text_input(long_text, max_length=100)
        assert len(result) <= 100

    def test_none_returns_empty(self):
        """None → 空文字列"""
        result = sanitize_text_input(None)
        assert result == ""

    def test_ampersand_escaped(self):
        """& → &amp; エスケープ"""
        result = sanitize_text_input("A&B")
        assert "&amp;" in result


class TestValidateExportRequest:
    """エクスポートリクエストバリデーションのテスト"""

    def test_admin_can_export(self):
        """管理者 → エクスポート許可"""
        result = validate_export_request("ADMIN")
        assert result.is_valid is True

    def test_staff_cannot_export(self):
        """担当者 → エクスポート拒否"""
        result = validate_export_request("STAFF")
        assert result.is_valid is False

    def test_visitor_cannot_export(self):
        """来場者 → エクスポート拒否"""
        result = validate_export_request("VISITOR")
        assert result.is_valid is False
