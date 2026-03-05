"""
モンテカルロ法シミュレーションエンジン

M/M/1待ち行列モデルに不確実性を加味したモンテカルロシミュレーションを実行する。
来場者数の変動・サービス時間のばらつきを確率的に扱い、
信頼区間付きの予測を提供する。

参考：
    Ross, S.M. (2006). Simulation (4th ed.). Academic Press.
"""

import numpy as np
import plotly.graph_objects as go
import streamlit as st
from dataclasses import dataclass
from typing import List

from core.queue_models import calculate_mm1_metrics, QueueMetrics


@dataclass
class SimulationResult:
    """
    モンテカルロシミュレーション結果を保持するデータクラス。

    Attributes:
        mean_wait (float): 平均待ち時間（分）
        std_wait (float): 待ち時間の標準偏差
        ci_lower_95 (float): 95%信頼区間の下限（分）
        ci_upper_95 (float): 95%信頼区間の上限（分）
        mean_utilization (float): 平均サーバー利用率 ρ
        ci_lower_util (float): 利用率の95%信頼区間下限
        ci_upper_util (float): 利用率の95%信頼区間上限
        saturation_probability (float): 飽和状態（ρ≧1.0）の発生確率
        samples (list[float]): 全試行の待ち時間サンプル
    """
    mean_wait: float
    std_wait: float
    ci_lower_95: float
    ci_upper_95: float
    mean_utilization: float
    ci_lower_util: float
    ci_upper_util: float
    saturation_probability: float
    samples: List[float]


def run_monte_carlo(
    queue_length: int,
    avg_service_time: float,
    capacity: int,
    scale_factor: float = 1.0,
    n_trials: int = 1000,
    queue_variation_pct: float = 0.2,
    service_variation_pct: float = 0.15,
    random_seed: int = 42,
) -> SimulationResult:
    """
    モンテカルロ法による待ち行列シミュレーションを実行する。

    手法：
    1. 行列人数を正規分布でサンプリング（平均: queue_length×scale_factor, σ: variation_pct）
    2. サービス時間を正規分布でサンプリング（平均: avg_service_time, σ: variation_pct）
    3. 各試行でM/M/1モデルを計算
    4. 統計量（平均・分散・信頼区間）を算出

    Args:
        queue_length (int): 現在の行列人数
        avg_service_time (float): 平均サービス時間（分）
        capacity (int): 窓口数
        scale_factor (float): 来場者スケール倍率（シミュレーション用）
        n_trials (int): モンテカルロ試行回数（デフォルト1000）
        queue_variation_pct (float): 行列人数の変動係数（デフォルト±20%）
        service_variation_pct (float): サービス時間の変動係数（デフォルト±15%）
        random_seed (int): 乱数シード（再現性確保）

    Returns:
        SimulationResult: シミュレーション統計結果
    """
    rng = np.random.default_rng(random_seed)

    base_queue = queue_length * scale_factor
    queue_sigma = base_queue * queue_variation_pct
    service_sigma = avg_service_time * service_variation_pct

    wait_samples = []
    util_samples = []
    saturation_count = 0

    for _ in range(n_trials):
        # 確率的サンプリング（正規分布）
        sampled_queue = max(0, int(rng.normal(base_queue, queue_sigma)))
        sampled_service = max(0.5, rng.normal(avg_service_time, service_sigma))

        try:
            metrics = calculate_mm1_metrics(sampled_queue, sampled_service, capacity)
            wait_samples.append(float(metrics.wait_minutes))
            util_samples.append(metrics.utilization)

            if metrics.status == "SATURATED":
                saturation_count += 1
        except Exception:
            # 計算失敗時はスキップ
            continue

    if not wait_samples:
        # フォールバック（全試行失敗時）
        return SimulationResult(
            mean_wait=0.0, std_wait=0.0,
            ci_lower_95=0.0, ci_upper_95=0.0,
            mean_utilization=0.0, ci_lower_util=0.0, ci_upper_util=0.0,
            saturation_probability=0.0, samples=[],
        )

    wait_arr = np.array(wait_samples)
    util_arr = np.array(util_samples)

    # 統計量計算
    mean_wait = float(np.mean(wait_arr))
    std_wait = float(np.std(wait_arr))
    sem = std_wait / np.sqrt(len(wait_arr))

    # 95%信頼区間（Z値 = 1.96）
    ci_lower_95 = max(0.0, mean_wait - 1.96 * sem)
    ci_upper_95 = mean_wait + 1.96 * sem

    mean_util = float(np.mean(util_arr))
    util_sem = float(np.std(util_arr)) / np.sqrt(len(util_arr))
    ci_lower_util = max(0.0, mean_util - 1.96 * util_sem)
    ci_upper_util = mean_util + 1.96 * util_sem

    saturation_prob = saturation_count / len(wait_samples)

    return SimulationResult(
        mean_wait=round(mean_wait, 1),
        std_wait=round(std_wait, 1),
        ci_lower_95=round(ci_lower_95, 1),
        ci_upper_95=round(ci_upper_95, 1),
        mean_utilization=round(mean_util, 4),
        ci_lower_util=round(ci_lower_util, 4),
        ci_upper_util=round(ci_upper_util, 4),
        saturation_probability=round(saturation_prob, 4),
        samples=wait_samples[:200],  # 表示用に200件に間引き
    )


def render_monte_carlo_panel(events: list, metrics_map: dict) -> None:
    """
    モンテカルロシミュレーションパネルを表示する。

    管理者画面のシミュレーションタブに配置される。
    スライダーで来場者倍率を調整し、全イベントの予測混雑度を表示する。

    Args:
        events (list[dict]): 全イベントリスト
        metrics_map (dict): {event_id: QueueMetrics}
    """
    st.markdown("### 🔮 モンテカルロシミュレーション（1000試行）")
    st.markdown("来場者数の変動を確率的に考慮した混雑予測を行います。")

    col1, col2 = st.columns([2, 1])

    with col1:
        scale_factor = st.slider(
            "来場者数倍率",
            min_value=0.5,
            max_value=3.0,
            value=1.0,
            step=0.1,
            help="1.0 = 現状維持、2.0 = 来場者2倍",
            key="mc_scale_factor",
        )

    with col2:
        n_trials = st.selectbox(
            "試行回数",
            options=[500, 1000, 2000],
            index=1,
            key="mc_n_trials",
        )

    # 代表イベントを選択
    event_names = [f"{e['emoji']} {e['name']}" for e in events if e.get("is_open", True)]
    selected_name = st.selectbox("詳細分析するイベント", event_names, key="mc_selected_event")

    selected_event = next(
        (e for e in events if f"{e['emoji']} {e['name']}" == selected_name),
        events[0] if events else None,
    )

    if not selected_event:
        return

    # シミュレーション実行
    with st.spinner("🎲 モンテカルロシミュレーション実行中..."):
        result = run_monte_carlo(
            queue_length=selected_event["queue_length"],
            avg_service_time=selected_event["avg_service_time"],
            capacity=selected_event["capacity"],
            scale_factor=scale_factor,
            n_trials=n_trials,
        )

    # 結果表示
    col1, col2, col3, col4 = st.columns(4)

    with col1:
        st.metric("平均待ち時間", f"{result.mean_wait:.1f}分", delta=None)
    with col2:
        st.metric("95%信頼区間", f"{result.ci_lower_95:.1f}〜{result.ci_upper_95:.1f}分")
    with col3:
        st.metric("平均利用率 ρ", f"{result.mean_utilization:.3f}")
    with col4:
        st.metric("飽和発生確率", f"{result.saturation_probability*100:.1f}%")

    # ヒストグラム表示
    if result.samples:
        fig = go.Figure()

        fig.add_trace(go.Histogram(
            x=result.samples,
            nbinsx=30,
            name="待ち時間分布",
            marker_color="#0EA5E9",
            opacity=0.7,
        ))

        # 信頼区間の縦線
        fig.add_vline(x=result.mean_wait, line_dash="solid", line_color="#0F172A",
                      annotation_text=f"平均 {result.mean_wait:.1f}分")
        fig.add_vline(x=result.ci_lower_95, line_dash="dash", line_color="#22C55E",
                      annotation_text="95%CI下限")
        fig.add_vline(x=result.ci_upper_95, line_dash="dash", line_color="#EF4444",
                      annotation_text="95%CI上限")

        fig.update_layout(
            title=f"🎲 待ち時間分布（{n_trials}試行）",
            xaxis_title="待ち時間（分）",
            yaxis_title="頻度",
            height=320,
            plot_bgcolor="#FAFAFA",
            paper_bgcolor="white",
            margin=dict(t=50, b=40, l=40, r=20),
            showlegend=False,
        )

        st.plotly_chart(fig, use_container_width=True)

    # 感度分析テーブル
    st.markdown("#### 📊 スケール別感度分析")
    sensitivity_data = []

    for sf in [0.5, 0.75, 1.0, 1.25, 1.5, 2.0]:
        res = run_monte_carlo(
            selected_event["queue_length"],
            selected_event["avg_service_time"],
            selected_event["capacity"],
            scale_factor=sf,
            n_trials=200,  # 感度分析は高速化のため200試行
        )
        status = "🟢" if res.mean_utilization < 0.5 else (
            "🟡" if res.mean_utilization < 0.75 else (
            "🟠" if res.mean_utilization < 0.9 else (
            "🔴" if res.mean_utilization < 1.0 else "🚫")))
        sensitivity_data.append({
            "倍率": f"×{sf:.2f}",
            "平均待ち時間": f"{res.mean_wait:.1f}分",
            "95%CI": f"{res.ci_lower_95:.1f}〜{res.ci_upper_95:.1f}",
            "利用率 ρ": f"{res.mean_utilization:.3f}",
            "飽和確率": f"{res.saturation_probability*100:.1f}%",
            "状態": status,
        })

    import pandas as pd
    st.dataframe(
        pd.DataFrame(sensitivity_data),
        use_container_width=True,
        hide_index=True,
    )
