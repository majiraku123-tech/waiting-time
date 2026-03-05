"""
FestivalFlow AI — メインエントリーポイント

文化祭リアルタイム混雑管理システム
M/M/1待ち行列理論 × ゼロトラストセキュリティ × クリーンアーキテクチャ

起動方法：
    $ streamlit run app.py

Streamlit Cloud デプロイ：
    リポジトリ直下の app.py が自動検出される。
    requirements.txt の依存ライブラリが自動インストールされる。
"""

import streamlit as st

from core.data_manager import load_initial_events
from core.security import (
    ROLES, verify_pin, create_session, validate_session,
    logout, get_current_role_info,
)
from core.validators import validate_pin
from views.visitor_view import render_visitor_view
from views.staff_view import render_staff_view
from views.admin_view import render_admin_view


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# ページ設定（st.set_page_config は必ず最初に呼ぶ）
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
st.set_page_config(
    page_title="🎪 FestivalFlow AI",
    page_icon="🎪",
    layout="wide",
    initial_sidebar_state="expanded",
    menu_items={
        "Get Help": "https://github.com/your-repo/festivalflow-ai",
        "About": "FestivalFlow AI — 文化祭リアルタイム混雑管理システム v1.0",
    },
)


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# グローバルCSS（ブランドカラー・フォント・カスタムスタイル）
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
GLOBAL_CSS = """
<style>
    /* フォント・背景 */
    html, body, [class*="css"] {
        font-family: 'Noto Sans JP', 'Hiragino Kaku Gothic ProN', sans-serif !important;
    }
    .stApp {
        background-color: #F0F9FF;
    }

    /* メインコンテンツ幅 */
    .block-container {
        max-width: 1100px;
        padding-top: 1.5rem;
        padding-bottom: 2rem;
    }

    /* サイドバー */
    [data-testid="stSidebar"] {
        background: linear-gradient(180deg, #0F172A 0%, #1E293B 100%);
    }
    [data-testid="stSidebar"] * {
        color: #E2E8F0 !important;
    }
    [data-testid="stSidebar"] .stSelectbox label,
    [data-testid="stSidebar"] .stRadio label {
        color: #CBD5E1 !important;
        font-size: 0.85rem;
    }

    /* ボタン */
    .stButton > button {
        border-radius: 8px;
        font-weight: 600;
        transition: all 0.2s;
    }
    .stButton > button:hover {
        transform: translateY(-1px);
        box-shadow: 0 4px 12px rgba(14, 165, 233, 0.3);
    }

    /* タブ */
    .stTabs [data-baseweb="tab"] {
        font-weight: 600;
        border-radius: 8px 8px 0 0;
    }

    /* メトリクスカード */
    [data-testid="stMetric"] {
        background: white;
        border-radius: 12px;
        padding: 12px;
        box-shadow: 0 1px 4px rgba(0,0,0,0.06);
    }

    /* 数値入力 */
    .stNumberInput input {
        border-radius: 8px;
        font-size: 1.1rem;
        font-weight: 600;
        text-align: center;
    }

    /* 成功・警告・エラートースト */
    .stSuccess {
        border-radius: 10px;
    }

    /* ヘッダー非表示（クリーンUI） */
    header[data-testid="stHeader"] {
        background: transparent;
    }

    /* フッター非表示 */
    footer {visibility: hidden;}

    /* スクロールバー */
    ::-webkit-scrollbar { width: 6px; }
    ::-webkit-scrollbar-track { background: #F1F5F9; }
    ::-webkit-scrollbar-thumb { background: #94A3B8; border-radius: 3px; }
</style>
"""


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# session_state 初期化（KeyError 防止）
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
def initialize_session_state() -> None:
    """
    アプリ起動時に全session_stateキーを初期化する。

    React の useState に相当する Streamlit の状態管理。
    全キーをここで一元管理することで KeyError を防止する。
    グローバル変数は使用禁止（マルチセッション競合防止）。
    """
    defaults = {
        "role": "VISITOR",
        "authenticated": False,
        "session_info": None,
        "events": load_initial_events(),
        "last_updated": None,
        "anomaly_alerts": [],
        "demo_mode": False,
        "simulation_scale": 1.0,
        "login_error": None,
        "login_attempts": 0,
    }
    for key, value in defaults.items():
        if key not in st.session_state:
            st.session_state[key] = value


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# サイドバー：ナビゲーション・認証UI
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
def render_sidebar() -> str:
    """
    サイドバーを描画し、選択された画面名を返す。

    認証済みロールに応じてアクセス可能なメニューを表示する。
    未認証ユーザー（VISITOR）はPIN入力フォームを表示する。

    Returns:
        str: 選択された画面名（"visitor" | "staff" | "admin"）
    """
    with st.sidebar:
        # ── ロゴ・タイトル ──────────────────────────────
        st.markdown("""
        <div style="text-align: center; padding: 16px 0 24px;">
            <div style="font-size: 2.5rem;">🎪</div>
            <div style="font-size: 1.3rem; font-weight: 800; color: #F8FAFC;">
                FestivalFlow AI
            </div>
            <div style="font-size: 0.75rem; color: #94A3B8; margin-top: 4px;">
                リアルタイム混雑管理システム
            </div>
        </div>
        """, unsafe_allow_html=True)

        st.divider()

        # ── 現在のロール表示 ────────────────────────────
        role_info = get_current_role_info()
        st.markdown(f"""
        <div style="
            background: rgba(255,255,255,0.1);
            border-radius: 8px;
            padding: 8px 12px;
            margin-bottom: 16px;
            font-size: 0.85rem;
        ">
            {role_info['emoji']} 現在のロール：<strong>{role_info['label']}</strong>
        </div>
        """, unsafe_allow_html=True)

        # ── 画面ナビゲーション ──────────────────────────
        current_role = st.session_state.get("role", "VISITOR")
        accessible_views = ROLES.get(current_role, ROLES["VISITOR"])["accessible_views"]

        view_options = []
        view_labels = []

        if "visitor" in accessible_views:
            view_options.append("visitor")
            view_labels.append("🙋 来場者画面")
        if "staff" in accessible_views:
            view_options.append("staff")
            view_labels.append("📋 担当者画面")
        if "admin" in accessible_views:
            view_options.append("admin")
            view_labels.append("🔐 管理者画面")

        selected_index = 0
        if "selected_view" in st.session_state:
            try:
                selected_index = view_options.index(st.session_state["selected_view"])
            except ValueError:
                selected_index = 0

        selected_label = st.radio(
            "画面を選択",
            options=view_labels,
            index=selected_index,
            key="nav_radio",
            label_visibility="collapsed",
        )

        selected_view = view_options[view_labels.index(selected_label)]
        st.session_state["selected_view"] = selected_view

        st.divider()

        # ── PIN認証フォーム ─────────────────────────────
        if current_role == "VISITOR":
            _render_login_form()
        else:
            # ログアウトボタン
            if st.button("🚪 ログアウト", use_container_width=True, key="logout_btn"):
                logout()
                st.session_state["selected_view"] = "visitor"
                st.rerun()

        st.divider()

        # ── 統計サマリー（サイドバー下部） ──────────────
        events = st.session_state.get("events", [])
        open_count = sum(1 for e in events if e.get("is_open", True))
        total_queue = sum(e.get("queue_length", 0) for e in events)

        st.markdown(f"""
        <div style="font-size: 0.8rem; color: #94A3B8;">
            <div>📊 開催中: <strong style="color: #E2E8F0;">{open_count}件</strong></div>
            <div>👥 総行列: <strong style="color: #E2E8F0;">{total_queue:,}人</strong></div>
        </div>
        """, unsafe_allow_html=True)

    return selected_view


def _render_login_form() -> None:
    """
    PIN認証フォームを表示する。

    【セキュリティ注意】
    - PIN値をst.session_stateに保存してはならない
    - 連続失敗回数を記録するが、ブロック機能はデモ版では省略
    """
    st.markdown("#### 🔑 ログイン")

    login_tab1, login_tab2 = st.tabs(["担当者", "管理者"])

    with login_tab1:
        _render_pin_input("STAFF", "1234（デモ）")

    with login_tab2:
        _render_pin_input("ADMIN", "9999（デモ）")


def _render_pin_input(target_role: str, hint: str) -> None:
    """
    PIN入力UI（1ロール分）を表示する。

    Args:
        target_role (str): 認証対象ロール（"STAFF" or "ADMIN"）
        hint (str): ヒントテキスト（デモ用）
    """
    pin_key = f"pin_input_{target_role}"
    hint_text = f"PIN: {hint}"

    pin = st.text_input(
        hint_text,
        type="password",
        key=pin_key,
        placeholder="PINを入力...",
        label_visibility="visible",
    )

    if st.button(f"ログイン", key=f"login_btn_{target_role}", use_container_width=True):
        # バリデーション
        val_result = validate_pin(pin)
        if not val_result.is_valid:
            st.error(val_result.errors[0])
            return

        # PIN照合（bcrypt）
        if verify_pin(pin, target_role):
            session = create_session(target_role)
            st.session_state["role"] = target_role
            st.session_state["authenticated"] = True
            st.session_state["session_info"] = session
            st.session_state["login_error"] = None

            role_label = ROLES[target_role]["label"]
            st.success(f"✅ {role_label}としてログインしました！")
            st.rerun()
        else:
            st.session_state["login_attempts"] = st.session_state.get("login_attempts", 0) + 1
            st.error("❌ PINが正しくありません。")


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# メインヘッダー
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
def render_main_header(current_view: str) -> None:
    """
    メインコンテンツエリアのヘッダーを描画する。

    Args:
        current_view (str): 現在の画面名
    """
    view_config = {
        "visitor": {
            "title": "🙋 来場者ガイド",
            "subtitle": "リアルタイム混雑状況をチェックして、スマートに楽しもう！",
            "color": "#0EA5E9",
        },
        "staff": {
            "title": "📋 担当者ダッシュボード",
            "subtitle": "行列の実際の人数を入力・更新してください",
            "color": "#22C55E",
        },
        "admin": {
            "title": "🔐 管理者コントロールパネル",
            "subtitle": "イベント全体の混雑状況を分析・管理できます",
            "color": "#F97316",
        },
    }

    config = view_config.get(current_view, view_config["visitor"])

    st.markdown(f"""
    <div style="
        background: linear-gradient(135deg, {config['color']}15, {config['color']}05);
        border-bottom: 3px solid {config['color']};
        padding: 20px 0 16px;
        margin-bottom: 24px;
    ">
        <h1 style="margin: 0; color: #0F172A; font-size: 1.75rem;">{config['title']}</h1>
        <p style="margin: 6px 0 0; color: #475569; font-size: 0.9rem;">{config['subtitle']}</p>
    </div>
    """, unsafe_allow_html=True)


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# メインルーティング
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
def main() -> None:
    """
    アプリケーションのメインエントリーポイント。

    処理フロー：
    1. グローバルCSSの適用
    2. session_stateの初期化
    3. サイドバーの描画（認証UI含む）
    4. 選択された画面に対応するviewを描画
    """
    # グローバルスタイル適用
    st.markdown(GLOBAL_CSS, unsafe_allow_html=True)

    # session_state 初期化
    initialize_session_state()

    # サイドバー描画（選択画面名を返す）
    selected_view = render_sidebar()

    # メインヘッダー
    render_main_header(selected_view)

    # ── ルーティング ────────────────────────────────────
    if selected_view == "visitor":
        render_visitor_view()

    elif selected_view == "staff":
        # RBAC確認はstaff_view内部でも行うが、ここでも事前チェック
        if st.session_state.get("role", "VISITOR") not in ["STAFF", "ADMIN"]:
            st.warning("⚠️ 担当者画面にアクセスするにはログインが必要です。")
            st.info("📌 左サイドバーの「担当者」タブからPINでログインしてください。")
        else:
            render_staff_view()

    elif selected_view == "admin":
        if st.session_state.get("role", "VISITOR") != "ADMIN":
            st.warning("⚠️ 管理者画面にアクセスするには管理者ログインが必要です。")
            st.info("📌 左サイドバーの「管理者」タブからPINでログインしてください。")
        else:
            render_admin_view()

    else:
        render_visitor_view()


if __name__ == "__main__":
    main()
