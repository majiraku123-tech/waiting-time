"""
待ち行列理論エンジン（M/M/1モデル）

参考文献：
    Kleinrock, L. (1975). Queueing Systems Vol.1. Wiley.
    Little, J.D.C. (1961). A proof for the queueing formula: L = λW.
        Operations Research, 9(3), 383-387.
"""

import math
from dataclasses import dataclass
from typing import Literal

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 混雑ステータス定義
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
CongestionStatus = Literal["LOW", "MODERATE", "HIGH", "CRITICAL", "SATURATED"]

STATUS_CONFIG = {
    "LOW":       {"label": "空いている",   "color": "#22C55E", "emoji": "🟢", "threshold": 0.5},
    "MODERATE":  {"label": "やや混雑",     "color": "#EAB308", "emoji": "🟡", "threshold": 0.75},
    "HIGH":      {"label": "混雑",         "color": "#F97316", "emoji": "🟠", "threshold": 0.9},
    "CRITICAL":  {"label": "非常に混雑",   "color": "#EF4444", "emoji": "🔴", "threshold": 1.0},
    "SATURATED": {"label": "飽和状態",     "color": "#7C3AED", "emoji": "🚫", "threshold": float("inf")},
}


@dataclass
class QueueMetrics:
    """
    M/M/1待ち行列モデルの計算結果を保持するデータクラス。

    Attributes:
        wait_minutes (int): 推定待ち時間（切り上げ、分単位）
        utilization (float): サーバー利用率 ρ（0.0〜1.0+）
        avg_queue_length (float): 平均キュー長 Lq（人）
        avg_system_length (float): システム内平均人数 L（人）
        status (CongestionStatus): 混雑ステータス
        throughput (float): 実効スループット（人/分）
        arrival_rate (float): 推定到着率 λ（人/分）
        service_rate (float): サービス率 μ（人/分）
    """
    wait_minutes: int
    utilization: float
    avg_queue_length: float
    avg_system_length: float
    status: CongestionStatus
    throughput: float
    arrival_rate: float
    service_rate: float


def determine_status(utilization: float) -> CongestionStatus:
    """
    サーバー利用率 ρ から混雑ステータスを決定する。

    Args:
        utilization (float): サーバー利用率 ρ（0.0〜）

    Returns:
        CongestionStatus: 混雑ステータス文字列
    """
    if utilization >= 1.0:
        return "SATURATED"
    elif utilization >= 0.9:
        return "CRITICAL"
    elif utilization >= 0.75:
        return "HIGH"
    elif utilization >= 0.5:
        return "MODERATE"
    else:
        return "LOW"


def calculate_mm1_metrics(
    queue_length: int,
    avg_service_time: float,
    capacity: int = 1,
    time_window: float = 60.0,
) -> QueueMetrics:
    """
    M/M/1待ち行列モデルによる混雑指標を計算する。

    数式定義（Kleinrock, 1975）：
        λ（到着率）      = queue_length / time_window     [人/分]
        μ（サービス率）  = capacity / avg_service_time    [人/分]
        ρ（サーバー利用率）= λ / μ                        [無次元、0≦ρ＜1 が安定条件]

        安定条件（ρ＜1）が満たされる場合：
        Lq（平均キュー長）    = ρ² / (1 - ρ)              [人]
        L（平均システム内人数）= ρ / (1 - ρ)               [人]
        Wq（平均待ち時間）    = ρ / (μ × (1 - ρ))         [分]
        W（平均滞在時間）     = Wq + 1/μ                   [分]

    ρ≧1.0（飽和状態）では待ち時間が理論上無限大となるため、
    queue_lengthに基づく単純な待ち時間推定にフォールバックする。

    Args:
        queue_length (int): 現在の行列人数（0人以上）
        avg_service_time (float): 平均サービス時間（分、0より大きい値）
        capacity (int): 並列処理能力（窓口数、デフォルト1）
        time_window (float): 観測時間ウィンドウ（分、デフォルト60分）

    Returns:
        QueueMetrics: 計算された混雑指標データクラス

    Raises:
        ValueError: avg_service_time が 0 以下、または capacity が 0 以下の場合

    Examples:
        >>> metrics = calculate_mm1_metrics(30, 5.0, capacity=1)
        >>> print(f"待ち時間: {metrics.wait_minutes}分, 利用率: {metrics.utilization:.2f}")
    """
    # ── 入力バリデーション ──────────────────────────────
    if avg_service_time <= 0:
        raise ValueError(f"avg_service_time は正の値である必要があります: {avg_service_time}")
    if capacity <= 0:
        raise ValueError(f"capacity は1以上である必要があります: {capacity}")
    if queue_length < 0:
        queue_length = 0

    # ── M/M/1 基本パラメータ計算 ──────────────────────
    # λ: ポアソン到着過程の到着率（人/分）
    # time_window分の観測で queue_length 人が観察されたと仮定
    arrival_rate: float = queue_length / time_window if time_window > 0 else 0.0

    # μ: 指数分布サービス時間のサービス率（人/分）
    # capacity台の窓口が並列稼働する場合は容量分だけスループット向上
    service_rate: float = capacity / avg_service_time

    # ρ: サーバー利用率（トラフィック強度）
    if service_rate == 0:
        utilization = float("inf")
    else:
        utilization: float = arrival_rate / service_rate

    # ── 安定条件の確認とメトリクス計算 ────────────────
    status = determine_status(utilization)

    if utilization >= 1.0:
        # 飽和状態：理論上 Lq→∞, Wq→∞
        # 実用的な推定値として行列人数 × サービス時間 / 窓口数 で近似
        fallback_wait = math.ceil((queue_length * avg_service_time) / max(capacity, 1))
        return QueueMetrics(
            wait_minutes=fallback_wait,
            utilization=round(utilization, 4),
            avg_queue_length=float("inf"),
            avg_system_length=float("inf"),
            status=status,
            throughput=service_rate,
            arrival_rate=arrival_rate,
            service_rate=service_rate,
        )

    # 安定状態（ρ < 1）での正確な計算
    # Lq = ρ² / (1 - ρ)：平均キュー長（待ち行列の平均人数）
    avg_queue_length: float = (utilization ** 2) / (1 - utilization)

    # L = ρ / (1 - ρ)：システム内平均人数（待ち + サービス中）
    avg_system_length: float = utilization / (1 - utilization)

    # Wq = ρ / (μ × (1 - ρ))：平均待ち時間（分）
    # リトルの法則（Little's Law）: Lq = λ × Wq より導出可能
    avg_wait_time: float = utilization / (service_rate * (1 - utilization))

    # W = Wq + 1/μ：平均滞在時間（待ち + サービス時間）
    # avg_system_time: float = avg_wait_time + (1 / service_rate)  # 参考値

    # 実効スループット（安定状態ではλと等しい）
    throughput: float = arrival_rate

    # 待ち時間を分（切り上げ整数）に変換
    wait_minutes: int = math.ceil(avg_wait_time)

    return QueueMetrics(
        wait_minutes=max(0, wait_minutes),
        utilization=round(utilization, 4),
        avg_queue_length=round(avg_queue_length, 2),
        avg_system_length=round(avg_system_length, 2),
        status=status,
        throughput=round(throughput, 4),
        arrival_rate=round(arrival_rate, 4),
        service_rate=round(service_rate, 4),
    )


def calculate_trend(history: list) -> str:
    """
    直近の履歴データからトレンドを算出し、矢印記号を返す。

    直近5件の行列人数の傾きを線形回帰（最小二乗法）で計算する。
    傾きが正（増加傾向）なら↑、負（減少傾向）なら↓、±閾値内なら→を返す。

    Args:
        history (list): HistoryRecord のリスト（最新順）

    Returns:
        str: トレンド矢印（"↑" | "↓" | "→"）
    """
    if len(history) < 2:
        return "→"

    # 直近5件を使用（新しい順に並んでいると仮定）
    recent = history[-5:] if len(history) >= 5 else history

    # 行列人数を時系列順（古い→新しい）で抽出
    values = [r["queue_length"] if isinstance(r, dict) else r.queue_length for r in recent]

    if len(values) < 2:
        return "→"

    n = len(values)
    x_mean = (n - 1) / 2
    y_mean = sum(values) / n

    # 線形回帰の傾き b = Σ(xi - x̄)(yi - ȳ) / Σ(xi - x̄)²
    numerator = sum((i - x_mean) * (values[i] - y_mean) for i in range(n))
    denominator = sum((i - x_mean) ** 2 for i in range(n))

    if denominator == 0:
        return "→"

    slope = numerator / denominator

    # 傾きの閾値：±2人/更新 を基準とする
    if slope > 2.0:
        return "↑"
    elif slope < -2.0:
        return "↓"
    else:
        return "→"


def simulate_scaled_metrics(
    queue_length: int,
    avg_service_time: float,
    capacity: int,
    scale_factor: float,
) -> QueueMetrics:
    """
    スケールファクターを適用したシミュレーション用メトリクスを計算する。

    来場者数が scale_factor 倍になった場合の混雑度を試算する。
    管理者画面のシミュレーションパネルで使用。

    Args:
        queue_length (int): 現在の行列人数
        avg_service_time (float): 平均サービス時間（分）
        capacity (int): 窓口数
        scale_factor (float): スケール倍率（例：1.5 = 来場者50%増）

    Returns:
        QueueMetrics: スケール適用後の混雑指標
    """
    scaled_queue = int(queue_length * scale_factor)
    return calculate_mm1_metrics(scaled_queue, avg_service_time, capacity)


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 【設計ドキュメント】queue_models.py
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#
# ■ 採用した数理モデルと根拠
#   M/M/1キューを採用した理由：
#   - 文化祭来場者の到着間隔はポアソン過程に近似できる（ランダム独立到着）
#   - サービス時間（アトラクション体験時間）は指数分布に近似
#   - 単一サーバー（1窓口）仮定が多くの出し物に合致
#   M/M/cへの拡張が必要なケース（飲食ブースの複数カウンター）は
#   capacity引数で対応できるよう設計済み
#
# ■ 限界と注意事項
#   - ρ≧1.0（飽和状態）では理論的に待ち時間が無限大になるため、
#     実用的なフォールバック計算にスイッチする
#   - M/M/1は「無限キュー容量」を前提とするが、実際の文化祭では
#     行列が廊下をはみ出す等の物理的制約があることに留意
#
# ■ 今後の改善ロードマップ
#   Phase 1（3ヶ月）：LSTMによる時系列予測（過去データから30分後の混雑を予測）
#   Phase 2（6ヶ月）：M/G/1モデルへの拡張（一般分布サービス時間対応）
#   Phase 3（1年）：強化学習による動的スタッフ配置最適化
