import streamlit as st
import json
import math

# ──────────────────────────────────────────────
# 1. 스케일링 로직 (core/scaling.py 기반)
# ──────────────────────────────────────────────
ALPHA_MAP = {
    "썰다": 0.9,
    "갈다": 0.9,
    "볶다": 0.3,
    "끓이다": 0.5,
    "삶다": 0.5,
    "찌다": 0.5,
    "굽다": 0.2,
    "마무리": 0.1,
    "간하기": 0.1,
}
DEFAULT_ALPHA = 0.5


def scale_time(t_base, base_servings, target_servings, action):
    if t_base == 0 or base_servings == target_servings:
        return t_base
    alpha = ALPHA_MAP.get(action, DEFAULT_ALPHA)
    ratio = target_servings / base_servings
    return round(t_base * (ratio ** alpha), 1)


# ──────────────────────────────────────────────
# 2. 데이터 로드
# ──────────────────────────────────────────────
@st.cache_data
def load_recipe(path):
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


recipe = load_recipe("data/structured_steps/137_된장두부찌개.json")

# ──────────────────────────────────────────────
# 3. 커스텀 CSS
# ──────────────────────────────────────────────
st.markdown("""
<style>
/* 전체 폰트 */
@import url('https://fonts.googleapis.com/css2?family=Noto+Sans+KR:wght@300;400;500;700&display=swap');
html, body, [class*="css"] { font-family: 'Noto Sans KR', sans-serif; }

/* 스텝 카드 */
.step-card {
    background: #fafafa;
    border-left: 4px solid #ff6b35;
    border-radius: 8px;
    padding: 20px 24px;
    margin-bottom: 16px;
}
.step-header {
    display: flex;
    align-items: center;
    gap: 12px;
    margin-bottom: 12px;
}
.step-number {
    background: #ff6b35;
    color: white;
    font-weight: 700;
    font-size: 14px;
    width: 32px; height: 32px;
    border-radius: 50%;
    display: flex; align-items: center; justify-content: center;
    flex-shrink: 0;
}
.step-action {
    font-size: 18px;
    font-weight: 700;
    color: #1a1a1a;
}
.step-detail {
    font-size: 15px;
    color: #333;
    margin-bottom: 12px;
    line-height: 1.6;
}

/* 메타 정보 (화력, 시간, 상태조건) */
.meta-row {
    display: flex;
    gap: 10px;
    flex-wrap: wrap;
    margin-bottom: 10px;
}
.meta-chip {
    font-size: 13px;
    padding: 4px 12px;
    border-radius: 20px;
    font-weight: 500;
}
.chip-heat-강 { background: #ffe0e0; color: #c62828; }
.chip-heat-중 { background: #fff3e0; color: #e65100; }
.chip-heat-약 { background: #e8f5e9; color: #2e7d32; }
.chip-heat-없음 { background: #f5f5f5; color: #757575; }
.chip-time { background: #e3f2fd; color: #1565c0; }
.chip-condition { background: #f3e5f5; color: #6a1b9a; }

/* 팁 박스 */
.tip-box {
    background: #fff8e1;
    border-radius: 6px;
    padding: 10px 14px;
    font-size: 13px;
    color: #5d4037;
    margin-top: 8px;
}
.tip-box::before {
    content: "💡 ";
}

/* 도구 태그 */
.tool-tag {
    display: inline-block;
    font-size: 12px;
    background: #eceff1;
    color: #546e7a;
    padding: 2px 10px;
    border-radius: 12px;
    margin-right: 6px;
    margin-top: 6px;
}

/* 총 시간 배너 */
.time-banner {
    background: linear-gradient(135deg, #ff6b35, #ff8a5c);
    color: white;
    border-radius: 12px;
    padding: 20px 28px;
    text-align: center;
    margin-bottom: 24px;
}
.time-banner-label { font-size: 14px; font-weight: 400; opacity: 0.9; }
.time-banner-value { font-size: 36px; font-weight: 700; margin-top: 4px; }

/* 레시피 헤더 */
.recipe-title { font-size: 28px; font-weight: 700; margin-bottom: 4px; }
.recipe-sub { font-size: 14px; color: #888; margin-bottom: 20px; }
</style>
""", unsafe_allow_html=True)


# ──────────────────────────────────────────────
# 4. 헤더
# ──────────────────────────────────────────────
st.markdown(f'<div class="recipe-title">{recipe["recipe_name"]}</div>', unsafe_allow_html=True)
st.markdown(f'<div class="recipe-sub">기준 {recipe["base_servings"]}인분 · {recipe["method"]} · 약 {recipe["total_time_min"]}분</div>', unsafe_allow_html=True)

st.divider()

# ──────────────────────────────────────────────
# 5. 인분 조절 + 총 시간
# ──────────────────────────────────────────────
col_serving, col_time = st.columns([1, 1])

with col_serving:
    target_servings = st.slider(
        "🍽️ 인분 조절",
        min_value=1,
        max_value=8,
        value=recipe["base_servings"],
        step=1,
    )

# 스케일된 시간 계산
scaled_steps = []
for step in recipe["steps"]:
    t_scaled = scale_time(
        step["estimated_time_min"],
        recipe["base_servings"],
        target_servings,
        step["action"],
    )
    scaled_steps.append({**step, "scaled_time": t_scaled})

total_scaled = sum(s["scaled_time"] for s in scaled_steps)
total_scaled_rounded = math.ceil(total_scaled)

with col_time:
    if target_servings != recipe["base_servings"]:
        st.markdown(f"""
        <div class="time-banner">
            <div class="time-banner-label">{target_servings}인분 예상 조리시간</div>
            <div class="time-banner-value">약 {total_scaled_rounded}분</div>
        </div>
        """, unsafe_allow_html=True)
    else:
        st.markdown(f"""
        <div class="time-banner">
            <div class="time-banner-label">예상 조리시간</div>
            <div class="time-banner-value">약 {recipe["total_time_min"]}분</div>
        </div>
        """, unsafe_allow_html=True)

st.divider()

# ──────────────────────────────────────────────
# 6. 단계별 요리 가이드
# ──────────────────────────────────────────────
st.markdown("### 📋 조리 단계")

for s in scaled_steps:
    heat = s.get("heat_level", "없음")
    heat_class = f"chip-heat-{heat}"
    time_display = s["scaled_time"]

    # 시간 표시: 정수면 정수로, 소수면 소수점 1자리
    if time_display == int(time_display):
        time_str = f"{int(time_display)}분"
    else:
        time_str = f"{time_display:.1f}분"

    # 메타 칩 조립
    meta_chips = f'<span class="meta-chip {heat_class}">🔥 {heat}</span>'
    meta_chips += f'<span class="meta-chip chip-time">⏱ {time_str}</span>'
    if s.get("end_condition"):
        meta_chips += f'<span class="meta-chip chip-condition">🎯 {s["end_condition"]}</span>'

    # 도구 태그
    tools_html = ""
    if s.get("tools_used"):
        tools_html = "".join(f'<span class="tool-tag">🔧 {t}</span>' for t in s["tools_used"])

    # 팁 박스
    tip_html = ""
    if s.get("technique_note"):
        tip_html = f'<div class="tip-box">{s["technique_note"]}</div>'

    # 인분 변경 시 시간 변화 표시
    time_delta = ""
    if target_servings != recipe["base_servings"]:
        orig = s["estimated_time_min"]
        diff = s["scaled_time"] - orig
        if abs(diff) >= 0.1:
            sign = "+" if diff > 0 else ""
            time_delta = f' <span style="font-size:12px;color:#888;">(기준 {orig}분 → {sign}{diff:.1f}분)</span>'

    card_html = f"""
    <div class="step-card">
        <div class="step-header">
            <div class="step-number">{s["step_number"]}</div>
            <div class="step-action">{s["action"]} — {s["target"]}</div>
        </div>
        <div class="step-detail">{s["detail"]}</div>
        <div class="meta-row">{meta_chips}</div>
        {f'<div style="margin-top:2px;font-size:12px;color:#888;">{time_delta}</div>' if time_delta else ""}
        {tools_html}
        {tip_html}
    </div>
    """
    st.markdown(card_html, unsafe_allow_html=True)

    # 타이머 버튼
    timer_seconds = int(s["scaled_time"] * 60)
    with st.expander(f"⏱ Step {s['step_number']} 타이머 ({time_str})"):
        st.components.v1.html(f"""
        <div id="timer-{s['step_number']}" style="font-family:'Noto Sans KR',sans-serif; text-align:center; padding:12px;">
            <div id="display-{s['step_number']}" style="font-size:48px; font-weight:700; color:#1565c0; margin:8px 0;">
                {timer_seconds // 60:02d}:{timer_seconds % 60:02d}
            </div>
            <div style="display:flex; gap:8px; justify-content:center; margin-top:8px;">
                <button onclick="startTimer{s['step_number']}()"
                    style="padding:8px 20px; border:none; background:#ff6b35; color:white;
                           border-radius:8px; font-size:14px; cursor:pointer; font-weight:500;">
                    ▶ 시작
                </button>
                <button onclick="stopTimer{s['step_number']}()"
                    style="padding:8px 20px; border:none; background:#eceff1; color:#333;
                           border-radius:8px; font-size:14px; cursor:pointer; font-weight:500;">
                    ⏸ 정지
                </button>
                <button onclick="resetTimer{s['step_number']}()"
                    style="padding:8px 20px; border:none; background:#eceff1; color:#333;
                           border-radius:8px; font-size:14px; cursor:pointer; font-weight:500;">
                    ↺ 리셋
                </button>
            </div>
        </div>
        <script>
            var remaining{s['step_number']} = {timer_seconds};
            var interval{s['step_number']} = null;
            function startTimer{s['step_number']}() {{
                if (interval{s['step_number']}) return;
                interval{s['step_number']} = setInterval(function() {{
                    if (remaining{s['step_number']} <= 0) {{
                        clearInterval(interval{s['step_number']});
                        interval{s['step_number']} = null;
                        document.getElementById('display-{s["step_number"]}').style.color = '#c62828';
                        document.getElementById('display-{s["step_number"]}').innerText = '완료!';
                        return;
                    }}
                    remaining{s['step_number']}--;
                    var m = Math.floor(remaining{s['step_number']} / 60);
                    var sec = remaining{s['step_number']} % 60;
                    document.getElementById('display-{s["step_number"]}').innerText =
                        String(m).padStart(2,'0') + ':' + String(sec).padStart(2,'0');
                }}, 1000);
            }}
            function stopTimer{s['step_number']}() {{
                clearInterval(interval{s['step_number']});
                interval{s['step_number']} = null;
            }}
            function resetTimer{s['step_number']}() {{
                clearInterval(interval{s['step_number']});
                interval{s['step_number']} = null;
                remaining{s['step_number']} = {timer_seconds};
                var m = Math.floor({timer_seconds} / 60);
                var sec = {timer_seconds} % 60;
                document.getElementById('display-{s["step_number"]}').style.color = '#1565c0';
                document.getElementById('display-{s["step_number"]}').innerText =
                    String(m).padStart(2,'0') + ':' + String(sec).padStart(2,'0');
            }}
        </script>
        """, height=140)


# ──────────────────────────────────────────────
# 7. 푸터
# ──────────────────────────────────────────────
st.divider()
st.caption(f"🔬 시간 스케일링: t_scaled = t_base × (인분비)^α | 기준 {recipe['base_servings']}인분 → {target_servings}인분")
