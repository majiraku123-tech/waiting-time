"""
フロアマップヒートマップコンポーネント（Plotly）

3×4グリッドで各教室の混雑度をカラーマップ表示する。
緑（空き）→ 赤（混雑）のグラデーション。
"""

import plotly.graph_objects as go
import numpy as np
import streamlit as st

# core. を消す
from queue_models import QueueMetrics


# フロアマップのグリッド定義
# 行：フロア（1〜4）、列：教室位置（A〜C + 特別室）
FLOOR_GRID = {
    4: {"4-A": (0, 0), "4-B": (0, 1), "4-C": (0, 2), "4-特": (0, 3)},
    3: {"3-A": (1, 0), "3-B": (1, 1), "3-C": (1, 2), "3-特": (1, 3)},
    2: {"2-A": (2, 0), "2-B": (2, 1), "2-C": (2, 2), "理科室": (2, 3)},
    1: {"1-A": (3, 0), "1-B": (3, 1), "1-C": (3, 2), "屋外広場": (3, 3)},
}

# 特別会場のマッピング
SPECIAL_ROOM_MAP = {
    "体育館": (3, 0),
    "ステージ": (3, 1),
    "屋外広場": (3, 2),
}


def render_floor_heatmap(events: list, metrics_map: dict) -> None:
    """
    フロアマップのヒートマップを表示する。

    各セルの色はサーバー利用率 ρ で決まる：
    - 0.0〜0.5：緑（空いている）
    - 0.5〜0.75：黄（やや混雑）
    - 0.75〜1.0：赤（混雑）

    Args:
        events (list[dict]): 全イベントリスト
        metrics_map (dict): {event_id: QueueMetrics}
    """
    # 4行×4列のグリッドを初期化（-1は未使用セル）
    rows, cols = 4, 4
    heat_values = np.full((rows, cols), -0.1)  # -0.1 = 空室（薄いグレー）
    hover_texts = [[""] * cols for _ in range(rows)]
    cell_labels = [[""] * cols for _ in range(rows)]

    # イベントデータをグリッドにマッピング
    for event in events:
        classroom = event.get("classroom", "")
        metrics = metrics_map.get(event["id"])
        if not metrics:
            continue

        # 教室位置を検索
        grid_pos = _find_grid_position(classroom)
        if grid_pos is None:
            continue

        row, col = grid_pos
        utilization = metrics.utilization
        heat_values[row][col] = min(utilization, 1.2)  # 飽和は1.2で上限

        # ホバーテキスト生成
        status_label = {
            "LOW": "空いている", "MODERATE": "やや混雑",
            "HIGH": "混雑", "CRITICAL": "非常に混雑", "SATURATED": "飽和"
        }.get(metrics.status, "")

        hover_texts[row][col] = (
            f"<b>{event['emoji']} {event['name']}</b><br>"
            f"教室: {classroom}<br>"
            f"行列: {event['queue_length']}人<br>"
            f"待ち: 約{metrics.wait_minutes}分<br>"
            f"利用率 ρ: {utilization:.2f}<br>"
            f"状態: {status_label}"
        )
        cell_labels[row][col] = f"{event['emoji']}<br>{event['name'][:4]}<br>ρ={utilization:.2f}"

    # フロアラベル
    y_labels = ["4F", "3F", "2F", "1F"]
    x_labels = ["A棟", "B棟", "C棟", "特別室"]

    # カスタムカラースケール（緑→黄→赤、-0.1は薄いグレー）
    colorscale = [
        [0.0, "#E5E7EB"],   # -0.1〜0.0: 空室（グレー）
        [0.1, "#E5E7EB"],   # 未使用
        [0.1, "#22C55E"],   # 0.0〜0.5: 緑（LOW）
        [0.35, "#86EFAC"],
        [0.46, "#EAB308"],  # 0.5〜0.75: 黄（MODERATE〜HIGH）
        [0.54, "#F97316"],
        [0.65, "#EF4444"],  # 0.75〜1.0: 赤（CRITICAL）
        [0.75, "#991B1B"],
        [1.0, "#7C3AED"],   # 1.0+: 紫（SATURATED）
    ]

    fig = go.Figure(data=go.Heatmap(
        z=heat_values,
        text=cell_labels,
        texttemplate="%{text}",
        hovertext=hover_texts,
        hovertemplate="%{hovertext}<extra></extra>",
        colorscale=colorscale,
        zmin=-0.1,
        zmax=1.2,
        showscale=True,
        colorbar=dict(
            title="混雑度 ρ",
            titleside="right",
            thickness=15,
            len=0.8,
            tickvals=[0.0, 0.5, 0.75, 1.0, 1.2],
            ticktext=["空き", "やや混雑", "混雑", "飽和", "超過"],
        ),
        xgap=3,
        ygap=3,
    ))

    fig.update_layout(
        title=dict(text="🗺️ フロアマップ混雑ヒートマップ", font=dict(size=16)),
        xaxis=dict(
            tickvals=list(range(cols)),
            ticktext=x_labels,
            side="top",
            showgrid=False,
        ),
        yaxis=dict(
            tickvals=list(range(rows)),
            ticktext=y_labels,
            showgrid=False,
            autorange="reversed",
        ),
        height=400,
        margin=dict(t=80, b=20, l=60, r=80),
        paper_bgcolor="white",
        plot_bgcolor="white",
        font=dict(family="sans-serif"),
    )

    st.plotly_chart(fig, use_container_width=True)


def _find_grid_position(classroom: str) -> tuple:
    """
    教室名からグリッド位置(row, col)を返す。

    Args:
        classroom (str): 教室名

    Returns:
        tuple: (row, col) または None
    """
    # 通常教室
    for floor, rooms in FLOOR_GRID.items():
        if classroom in rooms:
            return rooms[classroom]

    # 特別会場
    if classroom in SPECIAL_ROOM_MAP:
        return SPECIAL_ROOM_MAP[classroom]

    # フロア番号から推定（例："体育館"→1F）
    room_floor_map = {
        "体育館": (3, 0), "ステージ": (3, 1),
        "理科室": (2, 3), "屋外広場": (3, 2),
    }
    return room_floor_map.get(classroom, None)
