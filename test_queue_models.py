"""
M/M/1待ち行列モデルの単体テスト

テスト方針：
    - 境界値・正常系・異常系を網羅的に検証
    - 飽和条件（ρ≧1.0）の正しいハンドリングを確認
    - 数式の正確性を理論値と照合
"""

import math
import pytest
from core.queue_models import (
    calculate_mm1_metrics,
    calculate_trend,
    determine_status,
    simulate_scaled_metrics,
    QueueMetrics,
)


class TestDetermineStatus:
    """混雑ステータス判定のテスト"""

    def test_low_status(self):
        """ρ < 0.5 → LOW"""
        assert determine_status(0.0) == "LOW"
        assert determine_status(0.3) == "LOW"
        assert determine_status(0.499) == "LOW"

    def test_moderate_status(self):
        """ρ = 0.5〜0.75 → MODERATE"""
        assert determine_status(0.5) == "MODERATE"
        assert determine_status(0.6) == "MODERATE"
        assert determine_status(0.749) == "MODERATE"

    def test_high_status(self):
        """ρ = 0.75〜0.9 → HIGH"""
        assert determine_status(0.75) == "HIGH"
        assert determine_status(0.8) == "HIGH"
        assert determine_status(0.899) == "HIGH"

    def test_critical_status(self):
        """ρ = 0.9〜1.0 → CRITICAL"""
        assert determine_status(0.9) == "CRITICAL"
        assert determine_status(0.95) == "CRITICAL"
        assert determine_status(0.999) == "CRITICAL"

    def test_saturated_status(self):
        """ρ ≧ 1.0 → SATURATED"""
        assert determine_status(1.0) == "SATURATED"
        assert determine_status(1.5) == "SATURATED"
        assert determine_status(float("inf")) == "SATURATED"


class TestCalculateMm1Metrics:
    """M/M/1メトリクス計算のテスト"""

    def test_zero_queue(self):
        """行列ゼロ → 待ち時間0・LOW"""
        result = calculate_mm1_metrics(0, 5.0, 1)
        assert result.status == "LOW"
        assert result.wait_minutes == 0
        assert result.utilization == 0.0

    def test_normal_stable_state(self):
        """正常な安定状態のM/M/1計算"""
        # λ = 30/60 = 0.5人/分, μ = 1/5 = 0.2人/分
        # ρ = 0.5/0.2 = 2.5... → 飽和
        # queue_length = 5, time_window = 60, service_time = 10, capacity = 1
        # λ = 5/60 ≈ 0.0833, μ = 1/10 = 0.1, ρ = 0.0833/0.1 = 0.833
        result = calculate_mm1_metrics(5, 10.0, 1, 60.0)
        assert result.status in ["HIGH", "CRITICAL"]
        assert result.utilization > 0
        assert result.wait_minutes >= 0

    def test_low_utilization(self):
        """低利用率ケース（ρ < 0.5）"""
        # λ = 1/60 ≈ 0.0167, μ = 1/5 = 0.2, ρ ≈ 0.083
        result = calculate_mm1_metrics(1, 5.0, 1, 60.0)
        assert result.status == "LOW"
        assert result.utilization < 0.5
        assert result.wait_minutes >= 0

    def test_saturated_state(self):
        """飽和状態（ρ ≧ 1.0）→ SATURATED & フォールバック待ち時間"""
        # λ = 100/60 ≈ 1.67, μ = 1/5 = 0.2, ρ ≈ 8.33 → 飽和
        result = calculate_mm1_metrics(100, 5.0, 1, 60.0)
        assert result.status == "SATURATED"
        assert result.utilization >= 1.0
        # フォールバック待ち時間は 100*5/1 = 500分
        assert result.wait_minutes == 500

    def test_multi_capacity(self):
        """複数窓口（capacity > 1）でμが増加することを確認"""
        result_1 = calculate_mm1_metrics(10, 5.0, 1, 60.0)
        result_2 = calculate_mm1_metrics(10, 5.0, 2, 60.0)
        # 窓口2個の方が利用率が低いはず
        assert result_2.utilization < result_1.utilization

    def test_negative_queue_handled(self):
        """負の行列長は0にクランプされる"""
        result = calculate_mm1_metrics(-10, 5.0, 1)
        assert result.wait_minutes == 0
        assert result.status == "LOW"

    def test_invalid_service_time_raises(self):
        """サービス時間≦0はValueErrorを発生させる"""
        with pytest.raises(ValueError):
            calculate_mm1_metrics(10, 0.0, 1)

        with pytest.raises(ValueError):
            calculate_mm1_metrics(10, -5.0, 1)

    def test_invalid_capacity_raises(self):
        """capacity≦0はValueErrorを発生させる"""
        with pytest.raises(ValueError):
            calculate_mm1_metrics(10, 5.0, 0)

    def test_utilization_formula(self):
        """ρ = λ/μ の計算を検証"""
        # λ = 30/60 = 0.5, μ = 1/5 = 0.2
        # → 飽和（ρ=2.5）なのでメトリクス正常だがSATURATED
        # テスト用に低い値で確認
        # λ = 6/60 = 0.1, μ = 1/5 = 0.2, ρ = 0.5
        result = calculate_mm1_metrics(6, 5.0, 1, 60.0)
        expected_rho = (6 / 60.0) / (1 / 5.0)  # 0.5
        assert abs(result.utilization - expected_rho) < 0.01

    def test_wq_formula(self):
        """Wq = ρ / (μ(1-ρ)) の計算を検証"""
        # λ = 6/60 = 0.1, μ = 0.2, ρ = 0.5
        # Wq = 0.5 / (0.2 * 0.5) = 5分
        result = calculate_mm1_metrics(6, 5.0, 1, 60.0)
        rho = (6 / 60.0) / (1 / 5.0)  # 0.5
        mu = 1 / 5.0
        expected_wq = rho / (mu * (1 - rho))  # 5.0分
        assert abs(result.wait_minutes - math.ceil(expected_wq)) <= 1

    def test_returns_queue_metrics_type(self):
        """戻り値がQueueMetrics型であることを確認"""
        result = calculate_mm1_metrics(10, 5.0, 1)
        assert isinstance(result, QueueMetrics)

    def test_throughput_equals_arrival_in_stable(self):
        """安定状態ではスループット = 到着率"""
        result = calculate_mm1_metrics(3, 5.0, 1, 60.0)
        if result.status != "SATURATED":
            expected_lambda = 3 / 60.0
            assert abs(result.throughput - expected_lambda) < 0.001


class TestCalculateTrend:
    """トレンド算出のテスト"""

    def test_increasing_trend(self):
        """増加傾向 → ↑"""
        history = [
            {"queue_length": 10}, {"queue_length": 15},
            {"queue_length": 20}, {"queue_length": 28}, {"queue_length": 35},
        ]
        assert calculate_trend(history) == "↑"

    def test_decreasing_trend(self):
        """減少傾向 → ↓"""
        history = [
            {"queue_length": 40}, {"queue_length": 32},
            {"queue_length": 25}, {"queue_length": 15}, {"queue_length": 8},
        ]
        assert calculate_trend(history) == "↓"

    def test_stable_trend(self):
        """安定 → →"""
        history = [
            {"queue_length": 20}, {"queue_length": 21},
            {"queue_length": 20}, {"queue_length": 19}, {"queue_length": 20},
        ]
        assert calculate_trend(history) == "→"

    def test_empty_history(self):
        """空履歴 → →（デフォルト）"""
        assert calculate_trend([]) == "→"

    def test_single_record(self):
        """1件 → →"""
        assert calculate_trend([{"queue_length": 10}]) == "→"


class TestSimulateScaledMetrics:
    """スケールシミュレーションのテスト"""

    def test_scale_factor_1_equals_original(self):
        """scale_factor=1.0 は元のメトリクスと同等"""
        original = calculate_mm1_metrics(10, 5.0, 1)
        scaled = simulate_scaled_metrics(10, 5.0, 1, 1.0)
        assert original.status == scaled.status

    def test_higher_scale_higher_utilization(self):
        """スケール増加 → 利用率増加"""
        result_1x = simulate_scaled_metrics(10, 5.0, 1, 1.0)
        result_2x = simulate_scaled_metrics(10, 5.0, 1, 2.0)
        assert result_2x.utilization >= result_1x.utilization

    def test_scale_zero_equals_empty(self):
        """scale_factor=0 → 行列なし"""
        result = simulate_scaled_metrics(50, 5.0, 1, 0.0)
        assert result.wait_minutes == 0
