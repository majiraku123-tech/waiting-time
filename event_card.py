"""
イベントカードコンポーネント

混雑度・待ち時間・トレンド矢印を含むイベントカードのHTMLを生成する。
unsafe_allow_html=True を使用するが、全ての変数はサニタイズ済みであること。
"""

import streamlit as st
# core. を消す
from queue_models import QueueMetrics, STATUS_CONFIG, calculate_trend
from validators import sanitize_text_input


def get_status_style(status: str) -> dict:
    """
    混雑ステータスに対応するスタイル設定を返す。

    Args:
        status (str): 混雑ステータス

    Returns:
        dict: color, bg_color, border_color を含む辞書
    """
    styles = {
        "LOW":       {"color": "#15803D", "bg": "#F0FDF4", "border": "#22C55E"},
        "MODERATE":  {"color": "#A16207", "bg": "#FEFCE8", "border": "#EAB308"},
        "HIGH":      {"color": "#C2410C", "bg": "#FFF7ED", "border": "#F97316"},
        "CRITICAL":  {"color": "#991B1B", "bg": "#FEF2F2", "border": "#EF4444"},
        "SATURATED": {"color": "#5B21B6", "bg": "#FAF5FF", "border": "#7C3AED"},
    }
    return styles.get(status, styles["LOW"])


def render_event_card(event: dict, metrics: QueueMetrics, show_details: bool = True) -> None:
    """
    イベント情報を視覚的なカードとして表示する。

    Args:
        event (dict): イベントデータ
        metrics (QueueMetrics): M/M/1計算結果
        show_details (bool): 詳細情報（利用率・スループット）を表示するか
    """
    # ── サニタイズ（XSS対策：全変数をエスケープ） ────
    name = sanitize_text_input(event.get("name", ""), 50)
    classroom = sanitize_text_input(event.get("classroom", ""), 20)
    emoji = event.get("emoji", "🎪")
    category = sanitize_text_input(event.get("category", ""), 20)

    # 数値型のみを使用（文字列化はformat関数で制御）
    queue_length = int(event.get("queue_length", 0))
    status = metrics.status
    wait_minutes = metrics.wait_minutes
    utilization = metrics.utilization

    # スタイル設定
    style = get_status_style(status)
    status_info = STATUS_CONFIG.get(status, STATUS_CONFIG["LOW"])

    # トレンド計算
    history = event.get("history", [])
    trend_arrow = calculate_trend(history)
    trend_color = "#EF4444" if trend_arrow == "↑" else ("#22C55E" if trend_arrow == "↓" else "#6B7280")

    # 待ち時間表示
    if status == "SATURATED":
        wait_display = "待機不可"
        wait_color = "#7C3AED"
    elif wait_minutes == 0:
        wait_display = "待ち時間なし"
        wait_color = "#15803D"
    else:
        wait_display = f"約{wait_minutes}分待ち"
        wait_color = style["color"]

    # 利用率バーの幅（最大100%）
    util_pct = min(int(utilization * 100), 100)
    util_bar_color = style["border"]

    # 異常値フラグ
    anomaly_badge = "⚠️ " if event.get("anomaly_flag", False) else ""

    # 最終更新時刻
    last_updated = event.get("last_updated_at", "")
    last_updated_display = last_updated[11:16] if last_updated and len(last_updated) >= 16 else "未更新"

    full_card_html = f"""
    <div style="
        background: {style['bg']};
        border: 2px solid {style['border']};
        border-radius: 16px;
        padding: 18px 20px;
        margin-bottom: 12px;
        box-shadow: 0 2px 8px rgba(0,0,0,0.08);
        font-family: sans-serif;
    ">
        <div style="display: flex; justify-content: space-between; align-items: flex-start; margin-bottom: 10px;">
            <div>
                <span style="font-size: 1.5rem;">{emoji}</span>
                <span style="font-size: 1.15rem; font-weight: 700; color: #0F172A; margin-left: 8px;">
                    {anomaly_badge}{name}
                </span>
                <br>
                <span style="font-size: 0.82rem; color: #64748B; margin-left: 4px;">
                    📍 {classroom} ・ {category}
                </span>
            </div>
            <div style="
                background: {style['border']};
                color: white;
                border-radius: 20px;
                padding: 4px 12px;
                font-size: 0.8rem;
                font-weight: 600;
            ">
                {status_info['emoji']} {status_info['label']}
            </div>
        </div>

        <div style="display: flex; gap: 24px; margin-bottom: 10px; align-items: baseline;">
            <span style="font-size: 1.5rem; font-weight: 800; color: {wait_color};">{wait_display}</span>
            <span style="color: #64748B; font-size: 0.9rem;">
                👥 <strong>{queue_length}人</strong> 並び中
                &nbsp;&nbsp;
                <span style="color: {trend_color}; font-size: 1.1rem; font-weight: 700;">{trend_arrow}</span>
            </span>
        </div>

        <div style="margin-bottom: 6px;">
            <div style="display: flex; justify-content: space-between; margin-bottom: 4px;">
                <span style="font-size: 0.78rem; color: #64748B;">混雑度 ρ = {utilization:.2f}</span>
                <span style="font-size: 0.75rem; color: #94A3B8;">更新: {last_updated_display}</span>
            </div>
            <div style="background: #E2E8F0; border-radius: 999px; height: 8px; overflow: hidden;">
                <div style="
                    width: {util_pct}%;
                    height: 100%;
                    background: {util_bar_color};
                    transition: width 0.5s ease;
                "></div>
            </div>
        </div>
    </div>
    """
    st.markdown(full_card_html, unsafe_allow_html=True)


def render_recommendation_banner(events: list, metrics_map: dict) -> None:
    # 営業中のイベントをρ値で昇順ソート
    open_events = [e for e in events if e.get("is_open", True)]
    sorted_events = sorted(
        open_events,
        key=lambda e: metrics_map.get(e["id"], type("", (), {"utilization": 1.0})()).utilization
    )

    # しきい値を 0.8 に上げ、TOP3を取得
    recommendations = [
        e for e in sorted_events
        if metrics_map.get(e["id"], type("", (), {"utilization": 1.0})()).utilization < 0.8
    ][:3]

    if not recommendations:
        return

    # --- ここから修正：HTMLを一つの変数に溜め込む ---
    full_html = """
    <div style="
        background: linear-gradient(135deg, #0EA5E9 0%, #0284C7 100%);
        border-radius: 16px;
        padding: 20px 24px;
        margin-bottom: 20px;
        color: white;
    ">
        <div style="font-size: 1.1rem; font-weight: 700; margin-bottom: 12px;">
            🤖 AI穴場レコメンド — 今すぐ行くべきイベント！
        </div>
        <div style="display: flex; gap: 12px; flex-wrap: wrap;">
    """

    reason_templates = [
        "到着率が低く、安定状態を維持しています。",
        "サービス容量に対して来場者が少なく、穴場です。",
        "現在の行列は{queue}人のみ。すぐに体験できます！",
    ]

    for i, event in enumerate(recommendations):
        metrics = metrics_map.get(event["id"])
        if not metrics: continue
        
        reason = reason_templates[i % len(reason_templates)].format(queue=event['queue_length'])
        
        # 各カードのHTMLを追加
        full_html += f"""
            <div style="
                flex: 1;
                min-width: 200px;
                background: rgba(255,255,255,0.2);
                border-radius: 12px;
                padding: 14px;
                text-align: center;
                border: 1px solid rgba(255,255,255,0.3);
            ">
                <div style="font-size: 2rem;">{event['emoji']}</div>
                <div style="font-weight: 700; font-size: 1rem; margin: 6px 0;">{event['name']}</div>
                <div style="font-size: 0.85rem; opacity: 0.9; margin-bottom: 6px;">
                    {event['classroom']} | 待ち約{metrics.wait_minutes}分
                </div>
                <div style="font-size: 0.78rem; opacity: 0.8; line-height: 1.4;">{reason}</div>
            </div>
        """

    full_html += "</div></div>" # 全てのタグを閉じる

    # 最後に一回だけ表示
    st.markdown(full_html, unsafe_allow_html=True)
