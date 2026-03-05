"""
管理者画面（admin_view.py）

PIN認証（PIN: 9999）でアクセス可能。
KPIダッシュボード・時系列グラフ・ヒートマップ・
シミュレーション・CSVエクスポートを提供する。
"""

import time
import random
import pandas as pd
import streamlit as st
from datetime import datetime

# core. を消す
from data_manager import (
    get_all_events, update_queue_length, clear_anomaly_flag, add_anomaly_alert
)
from queue_models import calculate_mm1_metrics, QueueMetrics
from security import validate_permission
from validators import validate_export_request

# components. を消す
from charts import render_kpi_cards, render_time_series_chart, render_ranking_table, render_simulation_chart
from heatmap import render_floor_heatmap

# simulation. を消す
from monte_carlo import render_monte_carlo_panel


def render_admin_view() -> None:
    """
    管理者向けダッシュボード画面を描画する。

    タブ構成：
    1. 📊 ダッシュボード（KPI・ランキング）
    2. 📈 時系列グラフ
    3. 🗺️ フロアマップ
    4. 🔮 シミュレーション
    5. ⚙️ 管理設定
    """
    if not validate_permission("read:analytics"):
        st.error("⛔ この画面にアクセスする権限がありません。")
        return

    events = get_all_events()

    # ── 全イベントのM/M/1メトリクスを計算 ──────────────
    metrics_map: dict = {}
    for event in events:
        try:
            m = calculate_mm1_metrics(
                event.get("queue_length", 0),
                event.get("avg_service_time", 5.0),
                event.get("capacity", 1),
            )
        except Exception:
            m = QueueMetrics(
                wait_minutes=0, utilization=0.0, avg_queue_length=0.0,
                avg_system_length=0.0, status="LOW", throughput=0.0,
                arrival_rate=0.0, service_rate=0.0,
            )
        metrics_map[event["id"]] = m

    # ── タブ表示 ────────────────────────────────────────
    tab1, tab2, tab3, tab4, tab5 = st.tabs([
        "📊 ダッシュボード",
        "📈 時系列グラフ",
        "🗺️ フロアマップ",
        "🔮 シミュレーション",
        "⚙️ 管理設定",
    ])

    with tab1:
        _render_dashboard(events, metrics_map)

    with tab2:
        _render_time_series_tab(events, metrics_map)

    with tab3:
        _render_heatmap_tab(events, metrics_map)

    with tab4:
        _render_simulation_tab(events, metrics_map)

    with tab5:
        _render_settings_tab(events, metrics_map)


def _render_dashboard(events: list, metrics_map: dict) -> None:
    """ダッシュボードタブを描画する。"""
    # KPIカード×4
    render_kpi_cards(events, metrics_map)

    # 異常値アラート表示
    alerts = st.session_state.get("anomaly_alerts", [])
    if alerts:
        st.markdown("#### ⚠️ 異常値アラート")
        for alert in alerts:
            col1, col2 = st.columns([5, 1])
            with col1:
                st.warning(f"**{alert['event_name']}** （{alert['timestamp']}）: {alert['message']}")
            with col2:
                if st.button("✅ 解除", key=f"clear_alert_{alert['event_id']}", use_container_width=True):
                    clear_anomaly_flag(alert["event_id"])
                    st.rerun()

    # ランキングテーブル
    render_ranking_table(events, metrics_map)

    # デモモードボタン
    st.markdown("---")
    col1, col2 = st.columns(2)

    with col1:
        demo_active = st.session_state.get("demo_mode", False)
        if st.button(
            "⏹️ デモ停止" if demo_active else "▶️ デモ開始（5秒自動更新）",
            key="demo_toggle",
            use_container_width=True,
        ):
            st.session_state["demo_mode"] = not demo_active
            st.rerun()

    if st.session_state.get("demo_mode", False):
        _run_demo_mode(events)


def _render_time_series_tab(events: list, metrics_map: dict) -> None:
    """時系列グラフタブを描画する。"""
    # イベントフィルター
    event_options = {f"{e['emoji']} {e['name']}": e["id"] for e in events}
    selected_names = st.multiselect(
        "表示するイベントを選択",
        options=list(event_options.keys()),
        default=list(event_options.keys())[:5],
        key="ts_filter",
    )

    selected_ids = [event_options[n] for n in selected_names]
    render_time_series_chart(events, selected_ids if selected_names else None)


def _render_heatmap_tab(events: list, metrics_map: dict) -> None:
    """フロアマップタブを描画する。"""
    render_floor_heatmap(events, metrics_map)

    # 凡例
    st.markdown("""
    <div style="display: flex; gap: 16px; flex-wrap: wrap; margin-top: 12px; font-size: 0.85rem;">
        <span>🟢 空いている（ρ&lt;0.5）</span>
        <span>🟡 やや混雑（ρ=0.5〜0.75）</span>
        <span>🟠 混雑（ρ=0.75〜0.9）</span>
        <span>🔴 非常に混雑（ρ=0.9〜1.0）</span>
        <span>🚫 飽和（ρ≧1.0）</span>
    </div>
    """, unsafe_allow_html=True)


def _render_simulation_tab(events: list, metrics_map: dict) -> None:
    """シミュレーションタブを描画する。"""
    st.markdown("### 📊 来場者数スケールシミュレーション")

    scale = st.slider(
        "来場者数倍率（現在の行列に対して）",
        min_value=0.5, max_value=3.0, value=1.0, step=0.1,
        key="sim_scale_slider",
    )

    render_simulation_chart(events, metrics_map, scale)

    st.markdown("---")
    render_monte_carlo_panel(events, metrics_map)


def _render_settings_tab(events: list, metrics_map: dict) -> None:
    """管理設定タブを描画する。"""
    st.markdown("### ⚙️ 管理設定")

    # ── CSVエクスポート ─────────────────────────────────
    st.markdown("#### 📥 データエクスポート")

    export_validation = validate_export_request(st.session_state.get("role", "VISITOR"))
    if not export_validation.is_valid:
        st.error(export_validation.errors[0])
        return

    if st.button("📊 全履歴データをCSVでダウンロード", key="csv_export", use_container_width=False):
        csv_data = _generate_csv(events, metrics_map)
        st.download_button(
            label="⬇️ CSVダウンロード",
            data=csv_data,
            file_name=f"festivalflow_export_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv",
            mime="text/csv",
            key="csv_download",
        )

    # ── 異常値フラグ管理 ────────────────────────────────
    st.markdown("#### 🚩 異常値フラグ管理")

    flagged_events = [e for e in events if e.get("anomaly_flag", False)]
    if not flagged_events:
        st.success("✅ 現在、異常値フラグが立っているイベントはありません。")
    else:
        for event in flagged_events:
            col1, col2 = st.columns([4, 1])
            with col1:
                st.markdown(f"⚠️ **{event['emoji']} {event['name']}** — 異常値フラグ ON")
            with col2:
                if st.button("解除", key=f"admin_clear_{event['id']}", use_container_width=True):
                    clear_anomaly_flag(event["id"])
                    st.success(f"✅ {event['name']} のフラグを解除しました")
                    st.rerun()

    # ── システム情報 ────────────────────────────────────
    st.markdown("#### ℹ️ システム情報")
    total_history = sum(len(e.get("history", [])) for e in events)
    last_updated = st.session_state.get("last_updated", "未更新")

    st.markdown(f"""
    | 項目 | 値 |
    |------|-----|
    | 登録イベント数 | {len(events)} 件 |
    | 総履歴レコード数 | {total_history} 件 |
    | 最終更新 | {last_updated} |
    | 現在のロール | {st.session_state.get('role', 'VISITOR')} |
    | デモモード | {'ON' if st.session_state.get('demo_mode') else 'OFF'} |
    """)


def _generate_csv(events: list, metrics_map: dict) -> str:
    """
    全イベントの現在状態と履歴をCSV形式で生成する。

    Args:
        events (list[dict]): 全イベントリスト
        metrics_map (dict): 計算済みメトリクス

    Returns:
        str: CSV文字列
    """
    rows = []

    for event in events:
        metrics = metrics_map.get(event["id"])
        base_row = {
            "イベントID": event["id"],
            "イベント名": event["name"],
            "教室": event["classroom"],
            "フロア": event["floor"],
            "カテゴリ": event["category"],
            "現在の行列人数": event["queue_length"],
            "推定待ち時間（分）": metrics.wait_minutes if metrics else 0,
            "利用率ρ": metrics.utilization if metrics else 0.0,
            "混雑ステータス": metrics.status if metrics else "LOW",
            "最終更新": event.get("last_updated_at", ""),
            "異常値フラグ": event.get("anomaly_flag", False),
        }

        # 履歴レコードも含める
        for record in event.get("history", []):
            row = {
                **base_row,
                "履歴タイムスタンプ": record.get("timestamp", ""),
                "履歴行列人数": record.get("queue_length", 0),
                "履歴待ち時間": record.get("wait_minutes", 0),
                "更新者ロール": record.get("updated_by", ""),
            }
            rows.append(row)

        if not event.get("history"):
            rows.append({**base_row, "履歴タイムスタンプ": "", "履歴行列人数": "", "履歴待ち時間": "", "更新者ロール": ""})

    df = pd.DataFrame(rows)
    return df.to_csv(index=False, encoding="utf-8-sig")  # UTF-8 BOM（Excel対応）


def _run_demo_mode(events: list) -> None:
    """
    デモ自動変動モード：5秒ごとにランダムな行列変動をシミュレートする。

    st.empty()プレースホルダーで必要な箇所のみ更新し、
    ページ全体の再レンダリングを避ける。

    Args:
        events (list[dict]): 更新対象のイベントリスト
    """
    placeholder = st.empty()

    with placeholder.container():
        st.info("🎬 デモモード稼働中... 5秒後に自動更新されます")

    time.sleep(5)

    # ランダムに3イベントの行列を更新
    selected_events = random.sample(events, min(3, len(events)))

    for event in selected_events:
        current = event.get("queue_length", 0)
        # ±10〜30人のランダム変動（急激な変化は避ける）
        delta = random.randint(-15, 20)
        new_queue = max(0, min(300, current + delta))

        try:
            metrics = calculate_mm1_metrics(
                new_queue, event.get("avg_service_time", 5.0), event.get("capacity", 1)
            )
            wait_minutes = metrics.wait_minutes
        except Exception:
            wait_minutes = 0

        update_queue_length(
            event_id=event["id"],
            new_queue_length=new_queue,
            updated_by="DEMO",
            wait_minutes=wait_minutes,
        )

    placeholder.empty()
    st.rerun()
