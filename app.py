import streamlit as st
import pandas as pd
import json
import os
import sys
# --- [추가할 Import 코드] ---
from app.lp.lp_engine import solve_recipe_lp, NutritionGoal
from test_lp_engine import MOCK_CANDIDATES  # 일단 테스트용 후보 데이터 활용

# core 폴더 모듈 경로 추가
sys.path.append(os.path.dirname(os.path.abspath(__file__)))
from core.scaling import scale_recipe
from core.kg_query import create_matcher

# Matcher 초기화 (캐싱)
@st.cache_resource
def get_matcher():
    data_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data")
    return create_matcher(csv_dir=data_dir)

matcher = get_matcher()

st.set_page_config(layout="wide")
st.title("RefrigerAI v2 기술 검증 프로토타입")

tab1, tab2, tab3 = st.tabs(["1. 구조화 추출 결과", "2. 시간 스케일링 데모", "3. KG 냉장고 매칭"])

# 데이터 경로 설정
steps_folder = "data/structured_steps"

# --- 화면 1: 구조화 추출 결과 ---
with tab1:
    st.header("LLM 레시피 구조화 추출 검증")
    st.markdown("LLM이 원문에서 **시간·화력·상태·기법**을 추출한 결과입니다.")
    
    if not os.path.exists(steps_folder):
        st.error(f"'{steps_folder}' 폴더가 없습니다.")
    else:
        file_list = sorted([f for f in os.listdir(steps_folder) if f.endswith('.json')])
        if not file_list:
            st.warning("JSON 파일이 없습니다.")
        else:
            selected_file = st.selectbox("레시피 선택:", file_list, key='tab1_select')
            with open(os.path.join(steps_folder, selected_file), "r", encoding="utf-8") as f:
                recipe_data = json.load(f)
            
            col1, col2 = st.columns(2)
            with col1:
                st.subheader("재구성된 원문")
                raw_text = f"[{recipe_data['recipe_name']}] ({recipe_data['base_servings']}인분)\n\n"
                for s in recipe_data['steps']:
                    raw_text += f"{s['step_number']}. {s['target']} {s['action']}: {s['detail']}\n"
                st.info(raw_text)
            with col2:
                st.subheader("추출 JSON")
                st.json(recipe_data)

# --- 화면 2: 시간 스케일링 데모 ---
with tab2:
    st.header("인분 기반 시간 스케일링")
    st.markdown("공식: $t_{step}(s) = t_{base} \\times (s / s_{base})^\\alpha$")
    
    # tab1에서 선택된 recipe_data 사용
    if 'recipe_data' in locals():
        st.subheader(f"📍 {recipe_data['recipe_name']}")
        col_in1, col_in2 = st.columns([1, 2])
        with col_in1:
            st.write(f"**기준:** {recipe_data['base_servings']}인분 / {recipe_data['total_time_min']}분")
        with col_in2:
            target_srv = st.slider("목표 인분:", 1, 10, 1)
        
        res = scale_recipe(recipe_data, target_srv)
        
        m1, m2, m3 = st.columns(3)
        m1.metric("기준 시간", f"{res['base_total_min']}분")
        m2.metric(f"목표({target_srv}인분)", f"{res['scaled_total_min']}분")
        m3.metric("변화율", f"{res['change_pct']}%", delta=f"{res['change_pct']}%", delta_color="inverse")
        
        st.table(pd.DataFrame(res['steps']))
        
        if recipe_data['recipe_id'] == 250:
            st.success("💡 **발표 포인트**: '재우다'(α=0.0) 단계는 인분이 변해도 시간이 고정됩니다.")
    else:
        st.warning("1번 탭에서 레시피를 먼저 로드하세요.")

# --- 화면 3: KG 냉장고 매칭 ---
with tab3:
    st.header("KG 기반 냉장고 재료 매칭")
    st.markdown("Neo4j/CSV 데이터를 통한 보유 재료 기반 레시피 탐색")
    
    all_ingr = matcher.get_all_ingredients()
    user_fridge = st.multiselect("🧊 냉장고 재료 선택:", options=all_ingr, default=["두부", "양파"] if "두부" in all_ingr else None)
    
    if user_fridge:
        matches = matcher.match_recipes(user_fridge)
        for r in matches:
            # 매칭 결과 요약 표시
            rate = int(r['match_rate'] * 100)
            label = f"[{rate}%] {r['recipe_name']}"
            
            if rate == 100:
                st.success(f"**{label}** - 조리 가능")
            elif rate >= 50:
                st.warning(f"**{label}** - 부족: {r['missing']}")
            else:
                st.error(f"**{label}** - 부족: {r['missing']}")
            
            # 상세 정보 및 대체재
            with st.expander("상세 정보 및 대체재 확인"):
                st.write(f"필요 재료: {r['total_required']}개 / 보유: {r['matched_count']}개")
                if r['missing']:
                    for m_ing in r['missing']:
                        subs = matcher.get_substitutes(m_ing)
                        sub_text = ", ".join([f"{s['substitute']}({s['similarity']})" for s in subs]) if subs else "없음"
                        st.write(f"🔍 **{m_ing}** 대체재: {sub_text}")
        # --- [Tab 3 영역에 추가할 코드] ---
    st.markdown("---")
    st.subheader("맞춤형 식단 추천")

    if st.button("✨ 최적 레시피 3개 추천받기", use_container_width=True):
        with st.spinner("영양, 비용, 유통기한을 고려해 최적의 조합을 계산 중입니다..."):
        
        # 1. 유저 목표 세팅 (현재는 하드코딩, 추후 DB 연동)
            goal = NutritionGoal(
                tdee_kcal=2000, 
                protein_g=30, 
                budget_krw=8000, 
                meal_fraction=0.35
            )
        
            # 2. LP 엔진 최적화 실행
            result = solve_recipe_lp(
                candidates=MOCK_CANDIDATES, 
                goal=goal, 
                max_recipes=3, 
                use_highs=False
            )
        
        # 3. 결과 화면에 예쁘게 서빙하기
            if result.status == "Optimal":
                st.success("🎉 완벽한 식단 조합을 찾았습니다!")
            # 요약 지표 (Metric) 보여주기
                col1, col2, col3 = st.columns(3)
                col1.metric("총 칼로리", f"{result.total_kcal} kcal", f"목표: {goal.target_kcal} kcal 이하")
                col2.metric("총 단백질", f"{result.total_protein} g", f"목표: {goal.protein_g} g 이상")
                col3.metric("총 예상 비용", f"{result.total_cost} 원", f"예산: {goal.budget_krw} 원")
            
            # 선택된 레시피 카드 형태로 출력
                st.markdown("#### 🍽️ 추천 메뉴")
                for idx, detail in enumerate(result.details):
                    with st.expander(f"Top {idx+1}. {detail['recipe_name']} (점수: {detail['objective_score']:.2f})", expanded=True):
                        st.write(f"**칼로리:** {detail['total_kcal']} kcal | **단백질:** {detail['total_protein']} g | **비용:** {detail['estimated_cost']} 원")
            else:
                st.error("조건을 모두 만족하는 레시피 조합을 찾지 못했습니다. 예산을 늘리거나 냉장고 재료를 추가해 보세요.")
    else:
        st.info("재료를 선택하세요.")