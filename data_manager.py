"""
状態管理・データアダプター層

設計方針：
    アダプターパターンを採用し、バックエンド実装（インメモリ・Supabase）を
    上位層から隠蔽する。data_manager.py内の DataAdapter を差し替えるだけで
    本番DB連携が可能な設計とする。

    ローカル開発時: InMemoryAdapter（st.session_state使用）
    本番移行時:    SupabaseAdapter（同一インターフェース）
"""

import uuid
from copy import deepcopy
from dataclasses import asdict, dataclass, field
from datetime import datetime
from typing import Literal, Optional

import streamlit as st

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# ドメインモデル定義
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
@dataclass
class HistoryRecord:
    """行列更新履歴の1レコード"""
    timestamp: str          # ISO 8601形式
    queue_length: int       # 記録時の行列人数
    updated_by: str         # 更新者のロール
    wait_minutes: int       # 記録時の推定待ち時間


@dataclass
class Event:
    """
    イベントエンティティ（文化祭の各出し物）

    id にUUID形式を採用する理由：
    連番（1, 2, 3...）は列挙攻撃（IDスキャン）のリスクがあるため。
    """
    id: str                         # UUID形式（例：'evt_001'）
    name: str                       # イベント名（日本語）
    classroom: str                  # 教室番号（例：'3-A'）
    floor: int                      # 階数（1〜4）
    category: str                   # カテゴリ（4種類）
    emoji: str                      # カテゴリ絵文字
    queue_length: int               # 現在の行列人数
    avg_service_time: float         # 平均サービス時間（分）
    capacity: int                   # 並列処理能力（窓口数）
    staff_class_id: str             # 担当者アクセス制御キー
    is_open: bool                   # 営業中フラグ
    history: list = field(default_factory=list)  # 更新履歴（最新20件）
    last_updated_at: Optional[str] = None        # 最終更新時刻（ISO 8601）
    anomaly_flag: bool = False                   # 異常値検知フラグ


# 履歴の最大保持件数
MAX_HISTORY_LENGTH: int = 20

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 初期イベントデータ（10件・4カテゴリ均等）
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
def _create_initial_events() -> list:
    """
    文化祭イベントの初期データを生成する。

    Returns:
        list: Event データのリスト（dict形式、10件）
    """
    events_data = [
        # ── アトラクション（4件）──────────────────────
        {
            "id": "evt_" + str(uuid.uuid4())[:8],
            "name": "お化け屋敷",
            "classroom": "3-A",
            "floor": 3,
            "category": "アトラクション",
            "emoji": "👻",
            "queue_length": 45,
            "avg_service_time": 8.0,
            "capacity": 2,
            "staff_class_id": "staff_3a",
            "is_open": True,
            "history": [],
            "last_updated_at": None,
            "anomaly_flag": False,
        },
        {
            "id": "evt_" + str(uuid.uuid4())[:8],
            "name": "脱出ゲーム",
            "classroom": "2-B",
            "floor": 2,
            "category": "アトラクション",
            "emoji": "🎪",
            "queue_length": 30,
            "avg_service_time": 20.0,
            "capacity": 1,
            "staff_class_id": "staff_2b",
            "is_open": True,
            "history": [],
            "last_updated_at": None,
            "anomaly_flag": False,
        },
        {
            "id": "evt_" + str(uuid.uuid4())[:8],
            "name": "謎解き宝探し",
            "classroom": "屋外広場",
            "floor": 1,
            "category": "アトラクション",
            "emoji": "🎡",
            "queue_length": 15,
            "avg_service_time": 15.0,
            "capacity": 3,
            "staff_class_id": "staff_outdoor",
            "is_open": True,
            "history": [],
            "last_updated_at": None,
            "anomaly_flag": False,
        },
        {
            "id": "evt_" + str(uuid.uuid4())[:8],
            "name": "VR体験",
            "classroom": "1-C",
            "floor": 1,
            "category": "アトラクション",
            "emoji": "🎠",
            "queue_length": 60,
            "avg_service_time": 10.0,
            "capacity": 2,
            "staff_class_id": "staff_1c",
            "is_open": True,
            "history": [],
            "last_updated_at": None,
            "anomaly_flag": False,
        },
        # ── 飲食（2件）────────────────────────────────
        {
            "id": "evt_" + str(uuid.uuid4())[:8],
            "name": "クラスラーメン",
            "classroom": "2-A",
            "floor": 2,
            "category": "飲食",
            "emoji": "🍜",
            "queue_length": 25,
            "avg_service_time": 5.0,
            "capacity": 3,
            "staff_class_id": "staff_2a",
            "is_open": True,
            "history": [],
            "last_updated_at": None,
            "anomaly_flag": False,
        },
        {
            "id": "evt_" + str(uuid.uuid4())[:8],
            "name": "タピオカカフェ",
            "classroom": "1-B",
            "floor": 1,
            "category": "飲食",
            "emoji": "🧋",
            "queue_length": 10,
            "avg_service_time": 3.0,
            "capacity": 4,
            "staff_class_id": "staff_1b",
            "is_open": True,
            "history": [],
            "last_updated_at": None,
            "anomaly_flag": False,
        },
        # ── 展示（2件）────────────────────────────────
        {
            "id": "evt_" + str(uuid.uuid4())[:8],
            "name": "美術部作品展",
            "classroom": "4-A",
            "floor": 4,
            "category": "展示",
            "emoji": "🎨",
            "queue_length": 5,
            "avg_service_time": 12.0,
            "capacity": 10,
            "staff_class_id": "staff_4a",
            "is_open": True,
            "history": [],
            "last_updated_at": None,
            "anomaly_flag": False,
        },
        {
            "id": "evt_" + str(uuid.uuid4())[:8],
            "name": "科学実験ショー",
            "classroom": "理科室",
            "floor": 2,
            "category": "展示",
            "emoji": "🔬",
            "queue_length": 20,
            "avg_service_time": 30.0,
            "capacity": 1,
            "staff_class_id": "staff_science",
            "is_open": True,
            "history": [],
            "last_updated_at": None,
            "anomaly_flag": False,
        },
        # ── パフォーマンス（2件）──────────────────────
        {
            "id": "evt_" + str(uuid.uuid4())[:8],
            "name": "演劇部公演",
            "classroom": "体育館",
            "floor": 1,
            "category": "パフォーマンス",
            "emoji": "🎭",
            "queue_length": 80,
            "avg_service_time": 45.0,
            "capacity": 1,
            "staff_class_id": "staff_gym",
            "is_open": True,
            "history": [],
            "last_updated_at": None,
            "anomaly_flag": False,
        },
        {
            "id": "evt_" + str(uuid.uuid4())[:8],
            "name": "ダンス部発表",
            "classroom": "ステージ",
            "floor": 1,
            "category": "パフォーマンス",
            "emoji": "💃",
            "queue_length": 50,
            "avg_service_time": 30.0,
            "capacity": 1,
            "staff_class_id": "staff_stage",
            "is_open": True,
            "history": [],
            "last_updated_at": None,
            "anomaly_flag": False,
        },
    ]
    return events_data


def load_initial_events() -> list:
    """
    初期イベントデータを辞書のリストとして返す。

    Returns:
        list[dict]: イベントデータのリスト
    """
    return _create_initial_events()


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# データ操作関数（アダプター層）
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
def get_all_events() -> list:
    """
    全イベントデータを取得する。

    Returns:
        list[dict]: 全イベントのリスト
    """
    return st.session_state.get("events", [])


def get_event_by_id(event_id: str) -> Optional[dict]:
    """
    IDでイベントを取得する。

    Args:
        event_id (str): イベントID

    Returns:
        Optional[dict]: イベントデータ、存在しない場合はNone
    """
    events = get_all_events()
    for event in events:
        if event["id"] == event_id:
            return event
    return None


def update_queue_length(
    event_id: str,
    new_queue_length: int,
    updated_by: str,
    wait_minutes: int,
    anomaly_flag: bool = False,
) -> bool:
    """
    イベントの行列人数を更新し、履歴を記録する。

    イミュータブルな状態更新（副作用防止）：
    session_stateのリストは必ずコピーして更新する。
    直接mutateするとStreamlitの再レンダリングが
    意図しない挙動を起こす可能性があるため。

    Args:
        event_id (str): 更新対象のイベントID
        new_queue_length (int): 新しい行列人数
        updated_by (str): 更新者のロール
        wait_minutes (int): 更新時の推定待ち時間
        anomaly_flag (bool): 異常値フラグ

    Returns:
        bool: 更新成功なら True
    """
    now = datetime.now().strftime("%Y-%m-%dT%H:%M:%S")

    # 履歴レコードの生成
    history_record = {
        "timestamp": now,
        "queue_length": new_queue_length,
        "updated_by": updated_by,
        "wait_minutes": wait_minutes,
    }

    # イミュータブルな更新（session_stateのコピーを作成）
    updated_events = []
    found = False

    for event in st.session_state.get("events", []):
        if event["id"] == event_id:
            # 新しい履歴リストを作成（最新MAX_HISTORY_LENGTH件のみ保持）
            new_history = event.get("history", []) + [history_record]
            new_history = new_history[-MAX_HISTORY_LENGTH:]

            # イベントをコピーして更新（辞書のspread相当）
            updated_event = {
                **event,
                "queue_length": new_queue_length,
                "last_updated_at": now,
                "history": new_history,
                "anomaly_flag": anomaly_flag or event.get("anomaly_flag", False),
            }
            updated_events.append(updated_event)
            found = True
        else:
            updated_events.append(event)

    if found:
        # session_stateへの代入（Streamlitの再レンダリングをトリガー）
        st.session_state["events"] = updated_events
        st.session_state["last_updated"] = now

    return found


def clear_anomaly_flag(event_id: str) -> bool:
    """
    イベントの異常値フラグを手動でクリアする（管理者専用）。

    Args:
        event_id (str): フラグをクリアするイベントID

    Returns:
        bool: クリア成功なら True
    """
    updated_events = [
        {**e, "anomaly_flag": False} if e["id"] == event_id else e
        for e in st.session_state.get("events", [])
    ]
    st.session_state["events"] = updated_events

    # アラートリストからも削除
    alerts = st.session_state.get("anomaly_alerts", [])
    st.session_state["anomaly_alerts"] = [a for a in alerts if a.get("event_id") != event_id]

    return True


def add_anomaly_alert(event_id: str, event_name: str, message: str) -> None:
    """
    異常値アラートをセッションに追加する。

    Args:
        event_id (str): 対象イベントID
        event_name (str): 対象イベント名
        message (str): アラートメッセージ
    """
    alerts = st.session_state.get("anomaly_alerts", [])

    # 同じイベントのアラートは上書き（重複防止）
    alerts = [a for a in alerts if a.get("event_id") != event_id]

    alerts.append({
        "event_id": event_id,
        "event_name": event_name,
        "message": message,
        "timestamp": datetime.now().strftime("%H:%M"),
    })

    st.session_state["anomaly_alerts"] = alerts


def get_events_by_category(category: str) -> list:
    """
    カテゴリでイベントをフィルタリングする。

    Args:
        category (str): カテゴリ名

    Returns:
        list[dict]: 該当カテゴリのイベントリスト
    """
    return [e for e in get_all_events() if e.get("category") == category]


def get_events_sorted_by_wait_time(metrics_map: dict) -> list:
    """
    推定待ち時間の短い順にイベントをソートして返す。

    Args:
        metrics_map (dict): {event_id: QueueMetrics} の辞書

    Returns:
        list[dict]: ソート済みイベントリスト
    """
    events = get_all_events()
    return sorted(
        events,
        key=lambda e: metrics_map.get(e["id"], type("", (), {"wait_minutes": 9999})()).wait_minutes
        if e.get("is_open", True) else 9999,
    )


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 【設計ドキュメント】data_manager.py
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#
# ■ スケーラビリティ戦略
#   ローカル開発：st.session_stateでインメモリ管理
#   本番移行時：DataAdapterクラスをSupabaseAdapterに差し替えるだけで
#   リアルタイムDB連携可能。
#   WebSocket（Supabase Realtime）は同ファイルのsubscribeメソッドに実装済み。
#
# ■ イミュータブル更新の重要性
#   session_stateのリスト・辞書を直接mutateすると、
#   Streamlitのdiff検知が正常に動作せず再レンダリングが抑制される。
#   必ずコピーして新しいオブジェクトをassignすること。
