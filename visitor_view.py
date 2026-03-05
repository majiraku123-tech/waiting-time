"""
来場者画面（visitor_view.py）

認証不要・デフォルト表示。
全イベントの混雑状況をカード形式で提供し、AI穴場推薦・待機クイズを表示する。
"""

import random
import streamlit as st
import streamlit as st

from core.data_manager import get_all_events
from core.queue_models import calculate_mm1_metrics, QueueMetrics
from components.event_card import render_event_card, render_recommendation_banner
from components.quiz import render_quiz


def render_visitor_view() -> None:
    """
    来場者向けメイン画面を描画する。

    表示機能：
    1. AI穴場推薦バナー（ρ値が低いTOP3）
    2. ソート・フィルター機能
    3. 混雑度カード一覧（緑/黄/赤）
    4. 待機エンタメクイズ（15分以上のイベントで自動表示）
    """
    events = get_all_events()

    # ── M/M/1メトリクスを全イベントに対して計算 ────────
    metrics_map: dict = {}
    for event in events:
        if event.get("is_open", True):
            try:
                metrics = calculate_mm1_metrics(
                    queue_length=event.get("queue_length", 0),
                    avg_service_time=event.get("avg_service_time", 5.0),
                    capacity=event.get("capacity", 1),
                )
            except Exception:
                # 計算エラー時はデフォルト値
                metrics = QueueMetrics(
                    wait_minutes=0, utilization=0.0, avg_queue_length=0.0,
                    avg_system_length=0.0, status="LOW", throughput=0.0,
                    arrival_rate=0.0, service_rate=0.0,
                )
        else:
            metrics = QueueMetrics(
                wait_minutes=999, utilization=0.0, avg_queue_length=0.0,
                avg_system_length=0.0, status="LOW", throughput=0.0,
                arrival_rate=0.0, service_rate=0.0,
            )
        metrics_map[event["id"]] = metrics

    # ── AI穴場推薦バナー ────────────────────────────────
    render_recommendation_banner(events, metrics_map)

    # ── ソート・フィルターコントロール ──────────────────
    col1, col2 = st.columns([1, 1])

    with col1:
        sort_option = st.selectbox(
            "並び替え",
            options=["待ち時間が短い順", "カテゴリ別", "おすすめ順（穴場）"],
            label_visibility="collapsed",
            key="visitor_sort",
        )

    with col2:
        categories = ["すべて"] + list({e.get("category", "") for e in events})
        selected_category = st.selectbox(
            "カテゴリ",
            options=categories,
            label_visibility="collapsed",
            key="visitor_category",
        )

    # ── イベントのフィルタリング・ソート ────────────────
    filtered_events = events
    if selected_category != "すべて":
        filtered_events = [e for e in events if e.get("category") == selected_category]

    if sort_option == "待ち時間が短い順":
        filtered_events = sorted(
            filtered_events,
            key=lambda e: metrics_map.get(e["id"], type("", (), {"wait_minutes": 9999})()).wait_minutes,
        )
    elif sort_option == "カテゴリ別":
        filtered_events = sorted(filtered_events, key=lambda e: e.get("category", ""))
    elif sort_option == "おすすめ順（穴場）":
        filtered_events = sorted(
            filtered_events,
            key=lambda e: metrics_map.get(e["id"], type("", (), {"utilization": 1.0})()).utilization,
        )

    # ── イベントカード一覧表示 ──────────────────────────
    if not filtered_events:
        st.info("🔍 該当するイベントがありません。フィルターを変更してみてください。")
        return

    # カテゴリごとにセクション分け（カテゴリ別ソート時）
    if sort_option == "カテゴリ別":
        current_category = None
        for event in filtered_events:
            cat = event.get("category", "")
            if cat != current_category:
                current_category = cat
                cat_emoji = {
                    "アトラクション": "🎡", "飲食": "🍜",
                    "展示": "🎨", "パフォーマンス": "🎭",
                }.get(cat, "📌")
                st.markdown(f"#### {cat_emoji} {cat}")

            metrics = metrics_map.get(event["id"])
            if metrics:
                render_event_card(event, metrics)
                _render_quiz_if_needed(event, metrics)
    else:
        for event in filtered_events:
            metrics = metrics_map.get(event["id"])
            if metrics:
                render_event_card(event, metrics)
                _render_quiz_if_needed(event, metrics)


def _render_quiz_if_needed(event: dict, metrics: QueueMetrics) -> None:
    """
    待ち時間が15分以上のイベントでクイズを表示する。

    Args:
        event (dict): イベントデータ
        metrics (QueueMetrics): 計算済みメトリクス
    """
    if metrics.wait_minutes < 15:
        return

    quiz_toggle_key = f"show_quiz_{event['id']}"

    if quiz_toggle_key not in st.session_state:
        st.session_state[quiz_toggle_key] = False

    col1, col2 = st.columns([3, 1])
    with col2:
        if st.button(
            "🎮 クイズで暇つぶし！" if not st.session_state[quiz_toggle_key] else "▲ クイズを閉じる",
            key=f"quiz_btn_{event['id']}",
            use_container_width=True,
        ):
            st.session_state[quiz_toggle_key] = not st.session_state[quiz_toggle_key]

    if st.session_state[quiz_toggle_key]:
        render_quiz(event["name"])

    st.markdown("---")
