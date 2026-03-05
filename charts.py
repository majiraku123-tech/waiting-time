"""
グラフコンポーネント（Plotly / Altair）

時系列グラフ・KPIメトリクス・ランキングテーブルを提供する。
全グラフはインタラクティブ（ホバー・ズーム・フィルター対応）。
"""

import pandas as pd
import plotly.graph_objects as go
import plotly.express as px
import streamlit as st
from datetime import datetime

# core. を消す
from queue_models import STATUS_CONFIG


# カラーパレット（ブランドカラーと一致）
COLORS = [
    "#0EA5E9", "#F97316", "#22C55E", "#EAB308", "#EF4444",
    "#7C3AED", "#EC4899", "#14B8A6", "#F59E0B", "#6366F1",
]


def render_kpi_cards(events: list, metrics_map: dict) -> None:
    """
    管理者向けKPIカード×4を表示する。

    表示項目：
    1. 総来場推定人数
    2. 平均混雑度ρ
    3. 最混雑イベント名
    4. 異常値検知件数

    Args:
        events (list[dict]): 全イベントリスト
        metrics_map (dict): {event_id: QueueMetrics}
    """
    if not events:
        return

    # KPI計算
    total_queue = sum(e.get("queue_length", 0) for e in events)
    open_events = [e for e in events if e.get("is_open", True)]

    if open_events:
        avg_rho = sum(
            metrics_map.get(e["id"], type("", (), {"utilization": 0.0})()).utilization
            for e in open_events
        ) / len(open_events)

        max_congestion_event = max(
            open_events,
            key=lambda e: metrics_map.get(e["id"], type("", (), {"utilization": 0.0})()).utilization,
        )
        most_congested_name = f"{max_congestion_event['emoji']} {max_congestion_event['name']}"
    else:
        avg_rho = 0.0
        most_congested_name = "なし"

    anomaly_count = sum(1 for e in events if e.get("anomaly_flag", False))

    col1, col2, col3, col4 = st.columns(4)

    kpi_style = """
    <div style="
        background: {bg};
        border-left: 4px solid {color};
        border-radius: 12px;
        padding: 16px;
        text-align: center;
    ">
        <div style="font-size: 0.82rem; color: #64748B; margin-bottom: 4px;">{label}</div>
        <div style="font-size: 1.8rem; font-weight: 800; color: {color};">{value}</div>
        <div style="font-size: 0.75rem; color: #94A3B8; margin-top: 2px;">{sub}</div>
    </div>
    """

    with col1:
        st.markdown(kpi_style.format(
            bg="#EFF6FF", color="#0EA5E9",
            label="👥 総来場推定人数",
            value=f"{total_queue:,}人",
            sub="全イベント行列合計",
        ), unsafe_allow_html=True)

    with col2:
        rho_color = "#22C55E" if avg_rho < 0.5 else ("#EAB308" if avg_rho < 0.75 else "#EF4444")
        st.markdown(kpi_style.format(
            bg="#F0FDF4", color=rho_color,
            label="📊 平均混雑度 ρ",
            value=f"{avg_rho:.2f}",
            sub="全イベント平均利用率",
        ), unsafe_allow_html=True)

    with col3:
        st.markdown(kpi_style.format(
            bg="#FFF7ED", color="#F97316",
            label="🔥 最混雑イベント",
            value=most_congested_name,
            sub="現在最も混雑中",
        ), unsafe_allow_html=True)

    with col4:
        alert_color = "#EF4444" if anomaly_count > 0 else "#22C55E"
        st.markdown(kpi_style.format(
            bg="#FEF2F2" if anomaly_count > 0 else "#F0FDF4",
            color=alert_color,
            label="⚠️ 異常値検知",
            value=f"{anomaly_count}件",
            sub="管理者確認が必要",
        ), unsafe_allow_html=True)

    st.markdown("<br>", unsafe_allow_html=True)


def render_time_series_chart(events: list, selected_event_ids: list = None) -> None:
    """
    全イベントの行列人数推移を折れ線グラフで表示する（Plotly）。

    Args:
        events (list[dict]): 全イベントリスト
        selected_event_ids (list[str]): 表示するイベントIDリスト（Noneで全表示）
    """
    fig = go.Figure()

    has_data = False

    for i, event in enumerate(events):
        if selected_event_ids and event["id"] not in selected_event_ids:
            continue

        history = event.get("history", [])
        if not history:
            # 履歴がない場合は現在値を1点表示
            fig.add_trace(go.Scatter(
                x=[datetime.now().strftime("%H:%M")],
                y=[event.get("queue_length", 0)],
                mode="markers+lines",
                name=f"{event['emoji']} {event['name']}",
                line=dict(color=COLORS[i % len(COLORS)], width=2),
                marker=dict(size=8),
            ))
        else:
            timestamps = [h.get("timestamp", "")[:16].replace("T", " ") for h in history]
            queue_lengths = [h.get("queue_length", 0) for h in history]

            # 現在値を末尾に追加
            timestamps.append(datetime.now().strftime("%Y-%m-%d %H:%M"))
            queue_lengths.append(event.get("queue_length", 0))

            fig.add_trace(go.Scatter(
                x=timestamps,
                y=queue_lengths,
                mode="lines+markers",
                name=f"{event['emoji']} {event['name']}",
                line=dict(color=COLORS[i % len(COLORS)], width=2),
                marker=dict(size=6),
                hovertemplate="<b>%{fullData.name}</b><br>時刻: %{x}<br>行列: %{y}人<extra></extra>",
            ))
            has_data = True

    fig.update_layout(
        title=dict(text="📈 行列人数推移", font=dict(size=16, color="#0F172A")),
        xaxis_title="時刻",
        yaxis_title="行列人数（人）",
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
        hovermode="x unified",
        plot_bgcolor="#FAFAFA",
        paper_bgcolor="white",
        height=380,
        margin=dict(t=60, b=40, l=40, r=20),
        font=dict(family="sans-serif"),
    )

    fig.update_xaxes(showgrid=True, gridcolor="#E2E8F0")
    fig.update_yaxes(showgrid=True, gridcolor="#E2E8F0", rangemode="tozero")

    st.plotly_chart(fig, use_container_width=True)


def render_ranking_table(events: list, metrics_map: dict) -> None:
    """
    混雑度ランキング（上位5件）と空き状況ランキング（下位5件）を並列表示。

    Args:
        events (list[dict]): 全イベントリスト
        metrics_map (dict): {event_id: QueueMetrics}
    """
    open_events = [e for e in events if e.get("is_open", True)]

    sorted_by_congestion = sorted(
        open_events,
        key=lambda e: metrics_map.get(e["id"], type("", (), {"utilization": 0.0})()).utilization,
        reverse=True,
    )

    col1, col2 = st.columns(2)

    with col1:
        st.markdown("#### 🔥 混雑ランキング TOP5")
        for rank, event in enumerate(sorted_by_congestion[:5], 1):
            metrics = metrics_map.get(event["id"])
            if not metrics:
                continue
            status_info = STATUS_CONFIG.get(metrics.status, STATUS_CONFIG["LOW"])
            st.markdown(f"""
            <div style="
                display: flex; align-items: center; justify-content: space-between;
                padding: 8px 12px; margin-bottom: 6px;
                background: #FFF7ED; border-radius: 8px;
                border-left: 3px solid {status_info['color']};
            ">
                <span style="color: #64748B; font-weight: 700; min-width: 24px;">#{rank}</span>
                <span style="flex: 1; margin: 0 8px;">{event['emoji']} {event['name']}</span>
                <span style="color: {status_info['color']}; font-weight: 600;">{metrics.wait_minutes}分</span>
            </div>
            """, unsafe_allow_html=True)

    with col2:
        st.markdown("#### 🟢 空き状況 BOTTOM5")
        for rank, event in enumerate(sorted_by_congestion[-5:][::-1], 1):
            metrics = metrics_map.get(event["id"])
            if not metrics:
                continue
            status_info = STATUS_CONFIG.get(metrics.status, STATUS_CONFIG["LOW"])
            st.markdown(f"""
            <div style="
                display: flex; align-items: center; justify-content: space-between;
                padding: 8px 12px; margin-bottom: 6px;
                background: #F0FDF4; border-radius: 8px;
                border-left: 3px solid {status_info['color']};
            ">
                <span style="color: #64748B; font-weight: 700; min-width: 24px;">#{rank}</span>
                <span style="flex: 1; margin: 0 8px;">{event['emoji']} {event['name']}</span>
                <span style="color: {status_info['color']}; font-weight: 600;">ρ={metrics.utilization:.2f}</span>
            </div>
            """, unsafe_allow_html=True)


def render_simulation_chart(events: list, metrics_map: dict, scale_factor: float) -> None:
    """
    スケールファクター適用後の予測混雑度を棒グラフで表示。

    Args:
        events (list[dict]): 全イベントリスト
        metrics_map (dict): {event_id: QueueMetrics}（スケール適用済み）
        scale_factor (float): スケール倍率
    """
    from core.queue_models import simulate_scaled_metrics

    names = []
    current_utils = []
    scaled_utils = []

    for event in events:
        if not event.get("is_open", True):
            continue
        current = metrics_map.get(event["id"])
        scaled = simulate_scaled_metrics(
            event["queue_length"], event["avg_service_time"],
            event["capacity"], scale_factor
        )
        if current:
            names.append(f"{event['emoji']} {event['name']}")
            current_utils.append(min(current.utilization, 1.5))
            scaled_utils.append(min(scaled.utilization, 1.5))

    fig = go.Figure()

    fig.add_trace(go.Bar(
        name="現在",
        x=names,
        y=current_utils,
        marker_color="#0EA5E9",
        opacity=0.8,
    ))

    fig.add_trace(go.Bar(
        name=f"×{scale_factor:.1f}倍シミュレーション",
        x=names,
        y=scaled_utils,
        marker_color="#F97316",
        opacity=0.8,
    ))

    # ρ=1.0 の危険ライン
    fig.add_hline(y=1.0, line_dash="dash", line_color="#EF4444", annotation_text="飽和ライン (ρ=1.0)")

    fig.update_layout(
        title=dict(text=f"🔮 来場者 ×{scale_factor:.1f}倍 シミュレーション", font=dict(size=15)),
        barmode="group",
        yaxis_title="サーバー利用率 ρ",
        height=360,
        plot_bgcolor="#FAFAFA",
        paper_bgcolor="white",
        margin=dict(t=50, b=80, l=40, r=20),
        font=dict(family="sans-serif"),
        xaxis=dict(tickangle=-30),
    )

    st.plotly_chart(fig, use_container_width=True)
