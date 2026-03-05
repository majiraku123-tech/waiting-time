"""
担当者画面（staff_view.py）

PIN認証（PIN: 1234）でアクセス可能。
自分が担当するイベントの行列人数を入力・更新できる。
全入力にリアルタイムバリデーションを適用する。
"""

import streamlit as st
from datetime import datetime

# core. をすべて削除
from data_manager import get_all_events, update_queue_length, add_anomaly_alert
from queue_models import calculate_mm1_metrics
from validators import validate_queue_input
from security import validate_permission

def render_staff_view() -> None:
    """
    担当者向けメイン画面を描画する。

    RBAC確認後、担当クラスのイベントに対して行列人数の更新UIを表示する。
    担当者は自分のstaff_class_idに一致するイベントのみ編集可能。
    """
    # ── 権限確認（ゼロトラスト：毎回検証） ────────────
    if not validate_permission("write:queue"):
        st.error("⛔ この画面にアクセスする権限がありません。")
        return

    events = get_all_events()

    # ── 担当者の担当クラスフィルター ────────────────────
    # 実際の本番環境ではセッションのstaff_class_idに基づきフィルタリングするが、
    # デモ環境では全イベントを担当として表示する
    current_role = st.session_state.get("role", "STAFF")
    staff_events = events  # デモ：全イベントを担当として扱う

    if not staff_events:
        st.info("担当するイベントがありません。")
        return

    st.markdown("""
    <div style="
        background: #F0F9FF;
        border-left: 4px solid #0EA5E9;
        border-radius: 0 12px 12px 0;
        padding: 12px 16px;
        margin-bottom: 20px;
        font-size: 0.9rem;
        color: #0369A1;
    ">
        📋 <strong>担当者モード</strong>：行列の実際の人数を入力してください。
        入力データはリアルタイムで来場者に提供されます。
    </div>
    """, unsafe_allow_html=True)

    # ── イベントごとに入力フォームを表示 ────────────────
    for event in staff_events:
        _render_event_input(event)


def _render_event_input(event: dict) -> None:
    """
    1イベント分の行列人数入力UIを表示する。

    機能：
    - ±1ボタン（即時反映）
    - 直接数値入力フォーム（Enterで確定）
    - リアルタイムバリデーション表示
    - 更新成功/失敗フィードバック

    Args:
        event (dict): イベントデータ
    """
    event_id = event["id"]
    current_queue = event.get("queue_length", 0)

    # M/M/1メトリクス計算
    try:
        metrics = calculate_mm1_metrics(
            current_queue, event.get("avg_service_time", 5.0), event.get("capacity", 1)
        )
        status_emoji = {"LOW": "🟢", "MODERATE": "🟡", "HIGH": "🟠", "CRITICAL": "🔴", "SATURATED": "🚫"}.get(metrics.status, "⚪")
        wait_text = f"約{metrics.wait_minutes}分待ち" if metrics.status != "SATURATED" else "待機不可"
    except Exception:
        status_emoji = "⚪"
        wait_text = "計算中..."
        metrics = None

    # 異常値フラグ表示
    anomaly_badge = " ⚠️" if event.get("anomaly_flag", False) else ""

    with st.container():
        st.markdown(f"""
        <div style="
            background: white;
            border: 1px solid #E2E8F0;
            border-radius: 12px;
            padding: 16px 20px;
            margin-bottom: 12px;
        ">
            <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 12px;">
                <div>
                    <span style="font-size: 1.3rem;">{event.get('emoji', '🎪')}</span>
                    <strong style="font-size: 1.05rem; margin-left: 6px;">{event.get('name', '')}{anomaly_badge}</strong>
                    <span style="color: #64748B; font-size: 0.85rem; margin-left: 8px;">
                        📍 {event.get('classroom', '')}
                    </span>
                </div>
                <div style="text-align: right;">
                    <span style="font-size: 0.9rem; color: #64748B;">
                        {status_emoji} {wait_text}
                    </span>
                </div>
            </div>
        </div>
        """, unsafe_allow_html=True)

        # ── 入力コントロール ────────────────────────────
        col_minus, col_input, col_plus = st.columns([1, 3, 1])

        with col_minus:
            if st.button("－", key=f"minus_{event_id}", use_container_width=True,
                         disabled=current_queue <= 0):
                _do_update(event, max(0, current_queue - 1))

        with col_input:
            input_key = f"queue_input_{event_id}"
            new_value = st.number_input(
                "行列人数",
                min_value=0,
                max_value=500,
                value=current_queue,
                step=1,
                key=input_key,
                label_visibility="collapsed",
            )

            # 値が変化した場合に自動更新
            if new_value != current_queue:
                _do_update(event, new_value)

        with col_plus:
            if st.button("＋", key=f"plus_{event_id}", use_container_width=True):
                _do_update(event, current_queue + 1)

        # ── 現在の人数表示 ──────────────────────────────
        st.markdown(
            f'<div style="text-align: center; color: #475569; font-size: 0.85rem; margin-top: 4px;">'
            f'現在 <strong>{current_queue}人</strong> 並び中</div>',
            unsafe_allow_html=True,
        )

        # ── フィードバックメッセージ ────────────────────
        feedback_key = f"feedback_{event_id}"
        if feedback_key in st.session_state:
            feedback = st.session_state[feedback_key]
            if feedback["type"] == "success":
                st.success(feedback["message"])
            elif feedback["type"] == "warning":
                st.warning(feedback["message"])
            elif feedback["type"] == "error":
                st.error(feedback["message"])

        st.markdown("<br>", unsafe_allow_html=True)


def _do_update(event: dict, new_queue_length: int) -> None:
    """
    バリデーション後にキュー人数を更新する内部処理。

    Args:
        event (dict): 対象イベントデータ
        new_queue_length (int): 新しい行列人数
    """
    event_id = event["id"]
    current_queue = event.get("queue_length", 0)
    feedback_key = f"feedback_{event_id}"

    # ── バリデーション ──────────────────────────────────
    validation = validate_queue_input(
        value=new_queue_length,
        current_value=current_queue,
        event_name=event.get("name", ""),
    )

    if not validation.is_valid:
        st.session_state[feedback_key] = {
            "type": "error",
            "message": "\n".join(validation.errors),
        }
        return

    # ── M/M/1メトリクス計算（履歴記録用） ──────────────
    try:
        metrics = calculate_mm1_metrics(
            new_queue_length,
            event.get("avg_service_time", 5.0),
            event.get("capacity", 1),
        )
        wait_minutes = metrics.wait_minutes
    except Exception:
        wait_minutes = 0

    # ── データ更新 ──────────────────────────────────────
    current_role = st.session_state.get("role", "STAFF")
    success = update_queue_length(
        event_id=event_id,
        new_queue_length=validation.value,
        updated_by=current_role,
        wait_minutes=wait_minutes,
        anomaly_flag=validation.requires_admin_alert,
    )

    if not success:
        st.session_state[feedback_key] = {
            "type": "error",
            "message": "❌ 更新に失敗しました。再度お試しください。",
        }
        return

    # ── 異常値アラート追加 ──────────────────────────────
    if validation.requires_admin_alert:
        for warning in validation.warnings:
            add_anomaly_alert(event_id, event.get("name", ""), warning)

        st.session_state[feedback_key] = {
            "type": "warning",
            "message": "\n".join(validation.warnings),
        }
    else:
        now_str = datetime.now().strftime("%H:%M")
        st.session_state[feedback_key] = {
            "type": "success",
            "message": f"✅ 更新しました（{now_str}）",
        }

    # ページを再描画してフィードバックを表示
    st.rerun()
