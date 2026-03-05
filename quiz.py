"""
待機時間エンタメクイズコンポーネント

推定待ち時間が15分以上のイベントで自動表示される。
大谷翔平に関する問題×3問 + K-POPに関する問題×3問（計6問）をランダム出題。
"""

import random
import streamlit as st


# クイズ問題バンク
QUIZ_QUESTIONS = [
    # ── 大谷翔平関連（3問）────────────────────────────
    {
        "id": "ohtani_1",
        "category": "⚾ 大谷翔平",
        "question": "大谷翔平選手が2023年に所属していたMLBチームはどこでしょう？",
        "options": ["ロサンゼルス・ドジャース", "ロサンゼルス・エンゼルス", "ニューヨーク・ヤンキース", "シカゴ・カブス"],
        "answer": 1,  # 0-indexed
        "explanation": "2023年までエンゼルスに所属し、2024年からドジャースに移籍しました。",
    },
    {
        "id": "ohtani_2",
        "category": "⚾ 大谷翔平",
        "question": "大谷翔平選手が2021年にア・リーグMVPを受賞した際、ピッチャーと打者の「二刀流」として評価されましたが、その年の本塁打数は何本でしょう？",
        "options": ["36本", "46本", "56本", "26本"],
        "answer": 1,
        "explanation": "2021年シーズンに46本塁打を記録し、満票でMVPを受賞しました。",
    },
    {
        "id": "ohtani_3",
        "category": "⚾ 大谷翔平",
        "question": "大谷翔平選手の出身地はどこでしょう？",
        "options": ["北海道", "岩手県", "宮城県", "福岡県"],
        "answer": 1,
        "explanation": "岩手県奥州市出身で、花巻東高校で野球を始めました。",
    },
    # ── K-POP関連（3問）───────────────────────────────
    {
        "id": "kpop_1",
        "category": "🎵 K-POP",
        "question": "BTSが2020年に初の英語シングルとしてリリースし、全米ビルボードHOT100で1位を獲得した曲は何でしょう？",
        "options": ["DNA", "Dynamite", "Butter", "Permission to Dance"],
        "answer": 1,
        "explanation": "「Dynamite」は2020年8月リリースのBTS初の全英語シングルで、HOT100で1位を記録しました。",
    },
    {
        "id": "kpop_2",
        "category": "🎵 K-POP",
        "question": "BLACKPINK の4人のメンバーのうち、日本出身のメンバーは誰でしょう？",
        "options": ["JISOO", "JENNIE", "ROSÉ", "LISA"],
        "answer": 2,
        "explanation": "ROSÉはニュージーランド育ちですが、LISAはタイ出身です。日本出身のメンバーはいませんでしたが、ROSÉが韓国籍のニュージーランド育ちです。",
    },
    {
        "id": "kpop_3",
        "category": "🎵 K-POP",
        "question": "K-POPグループ「TWICE」は何人組でしょう？",
        "options": ["7人", "8人", "9人", "10人"],
        "answer": 2,
        "explanation": "TWICEはJYPエンターテインメント所属の9人組ガールズグループです。",
    },
]


def render_quiz(event_name: str) -> None:
    """
    待機時間エンタメクイズを表示する。

    推定待ち時間が15分以上のイベントで呼び出される。
    st.session_stateでクイズの出題・回答・正解率を管理する。

    Args:
        event_name (str): 待機中のイベント名（表示用）
    """
    quiz_key = f"quiz_{event_name}"
    answered_key = f"{quiz_key}_answered"
    score_key = f"{quiz_key}_score"
    total_key = f"{quiz_key}_total"
    current_key = f"{quiz_key}_current"
    shuffled_key = f"{quiz_key}_shuffled"

    # クイズ状態の初期化
    if shuffled_key not in st.session_state:
        shuffled = QUIZ_QUESTIONS.copy()
        random.shuffle(shuffled)
        st.session_state[shuffled_key] = shuffled
        st.session_state[current_key] = 0
        st.session_state[score_key] = 0
        st.session_state[total_key] = 0
        st.session_state[answered_key] = False

    questions = st.session_state[shuffled_key]
    current_idx = st.session_state[current_key]
    score = st.session_state[score_key]
    total = st.session_state[total_key]

    # ヘッダー表示
    st.markdown(f"""
    <div style="
        background: linear-gradient(135deg, #7C3AED 0%, #5B21B6 100%);
        border-radius: 16px;
        padding: 20px 24px;
        color: white;
        margin-bottom: 16px;
    ">
        <div style="font-size: 1.2rem; font-weight: 700; margin-bottom: 4px;">
            🎮 待ち時間クイズ
        </div>
        <div style="font-size: 0.85rem; opacity: 0.85;">
            「{event_name}」を待つ間にチャレンジ！
            スコア: <strong>{score}/{total}</strong>問正解
        </div>
    </div>
    """, unsafe_allow_html=True)

    # 全問終了時
    if current_idx >= len(questions):
        percentage = int((score / total) * 100) if total > 0 else 0
        _render_quiz_result(score, total, percentage, quiz_key)
        return

    question = questions[current_idx]
    answered = st.session_state.get(f"{quiz_key}_q{current_idx}_answered", False)

    # 問題表示
    st.markdown(f"""
    <div style="
        background: white;
        border: 2px solid #E0E7FF;
        border-radius: 12px;
        padding: 18px 20px;
        margin-bottom: 14px;
    ">
        <div style="font-size: 0.8rem; color: #7C3AED; font-weight: 600; margin-bottom: 8px;">
            {question['category']} — 問題 {current_idx + 1}/{len(questions)}
        </div>
        <div style="font-size: 1rem; font-weight: 600; color: #0F172A; line-height: 1.6;">
            {question['question']}
        </div>
    </div>
    """, unsafe_allow_html=True)

    # 選択肢ボタン
    if not answered:
        cols = st.columns(2)
        for opt_idx, option in enumerate(question["options"]):
            col = cols[opt_idx % 2]
            with col:
                if st.button(f"{['A', 'B', 'C', 'D'][opt_idx]}. {option}", key=f"{quiz_key}_opt_{current_idx}_{opt_idx}", use_container_width=True):
                    # 回答処理
                    is_correct = (opt_idx == question["answer"])
                    st.session_state[f"{quiz_key}_q{current_idx}_answered"] = True
                    st.session_state[f"{quiz_key}_q{current_idx}_selected"] = opt_idx
                    st.session_state[f"{quiz_key}_q{current_idx}_correct"] = is_correct
                    st.session_state[total_key] += 1
                    if is_correct:
                        st.session_state[score_key] += 1
                    st.rerun()
    else:
        # 回答後の正誤表示
        selected = st.session_state.get(f"{quiz_key}_q{current_idx}_selected", -1)
        is_correct = st.session_state.get(f"{quiz_key}_q{current_idx}_correct", False)

        for opt_idx, option in enumerate(question["options"]):
            if opt_idx == question["answer"]:
                bg = "#F0FDF4"
                border = "#22C55E"
                icon = "✅"
            elif opt_idx == selected and not is_correct:
                bg = "#FEF2F2"
                border = "#EF4444"
                icon = "❌"
            else:
                bg = "#F8FAFC"
                border = "#E2E8F0"
                icon = "　"

            st.markdown(f"""
            <div style="
                background: {bg};
                border: 2px solid {border};
                border-radius: 8px;
                padding: 10px 14px;
                margin-bottom: 6px;
                font-size: 0.9rem;
            ">
                {icon} {['A', 'B', 'C', 'D'][opt_idx]}. {option}
            </div>
            """, unsafe_allow_html=True)

        # 解説
        result_text = "正解！🎉" if is_correct else "残念！💦"
        result_color = "#22C55E" if is_correct else "#EF4444"
        st.markdown(f"""
        <div style="
            background: #F0F9FF;
            border-left: 4px solid #0EA5E9;
            border-radius: 0 8px 8px 0;
            padding: 12px 16px;
            margin-top: 10px;
        ">
            <span style="color: {result_color}; font-weight: 700;">{result_text}</span>
            <span style="color: #334155; font-size: 0.88rem; margin-left: 8px;">{question['explanation']}</span>
        </div>
        """, unsafe_allow_html=True)

        # 次の問題へ
        st.markdown("<br>", unsafe_allow_html=True)
        if st.button("▶ 次の問題へ", key=f"{quiz_key}_next_{current_idx}", use_container_width=True):
            st.session_state[current_key] += 1
            st.rerun()


def _render_quiz_result(score: int, total: int, percentage: int, quiz_key: str) -> None:
    """
    クイズ終了後の結果画面を表示する。

    Args:
        score (int): 正解数
        total (int): 総問題数
        percentage (int): 正解率（%）
        quiz_key (str): セッションキー（リセット用）
    """
    rank_text = "天才！🏆" if percentage >= 80 else ("よくできました！👍" if percentage >= 60 else "もう一度挑戦！💪")
    share_text = f"文化祭クイズで{score}/{total}問正解（{percentage}%）！{rank_text} #文化祭 #FestivalFlow"

    st.markdown(f"""
    <div style="
        background: linear-gradient(135deg, #F0FDF4, #DCFCE7);
        border: 2px solid #22C55E;
        border-radius: 16px;
        padding: 24px;
        text-align: center;
    ">
        <div style="font-size: 2.5rem; margin-bottom: 8px;">🎊</div>
        <div style="font-size: 1.5rem; font-weight: 800; color: #15803D; margin-bottom: 8px;">
            クイズ終了！{rank_text}
        </div>
        <div style="font-size: 1.2rem; color: #166534; margin-bottom: 16px;">
            正解率 <strong>{percentage}%</strong>（{score}/{total}問）
        </div>
        <div style="
            background: white;
            border-radius: 8px;
            padding: 12px;
            font-size: 0.85rem;
            color: #374151;
            font-family: monospace;
            word-break: break-all;
        ">
            📤 シェア用テキスト：<br>{share_text}
        </div>
    </div>
    """, unsafe_allow_html=True)

    st.markdown("<br>", unsafe_allow_html=True)
    if st.button("🔄 もう一度クイズに挑戦！", use_container_width=True):
        # クイズ状態をリセット
        keys_to_delete = [k for k in st.session_state.keys() if k.startswith(quiz_key)]
        for k in keys_to_delete:
            del st.session_state[k]
        st.rerun()
