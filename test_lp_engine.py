"""
test_lp_engine.py
LP 엔진 단독 테스트 — Neo4j 없이 목 데이터로 동작 확인
실행: python test_lp_engine.py
"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app.lp.lp_engine import (
    RecipeCandidate, NutritionGoal, solve_recipe_lp,
    compute_expiry_weight, build_objective_coefficients
)


# ─── 목 데이터: KG 미니 프로토타입 10개 레시피 기반 ───

MOCK_CANDIDATES = [
    RecipeCandidate("R001", "표고버섯볶음", total_kcal=320, total_protein=18, total_fat=12,
                    estimated_cost=2800, expiry_weight=compute_expiry_weight(2), missing_count=0),
    RecipeCandidate("R002", "두부된장국", total_kcal=280, total_protein=22, total_fat=8,
                    estimated_cost=3200, expiry_weight=compute_expiry_weight(7), missing_count=0),
    RecipeCandidate("R003", "청경채무침", total_kcal=150, total_protein=6, total_fat=4,
                    estimated_cost=1500, expiry_weight=compute_expiry_weight(1), missing_count=0),
    RecipeCandidate("R004", "참깨두부샐러드", total_kcal=240, total_protein=16, total_fat=14,
                    estimated_cost=2200, expiry_weight=compute_expiry_weight(5), missing_count=1),
    RecipeCandidate("R005", "무나물볶음", total_kcal=180, total_protein=4, total_fat=6,
                    estimated_cost=1200, expiry_weight=compute_expiry_weight(None), missing_count=0),
    RecipeCandidate("R006", "팽이버섯된장볶음", total_kcal=200, total_protein=10, total_fat=7,
                    estimated_cost=1800, expiry_weight=compute_expiry_weight(3), missing_count=0),
    RecipeCandidate("R007", "죽순잣무침", total_kcal=260, total_protein=8, total_fat=18,
                    estimated_cost=4200, expiry_weight=compute_expiry_weight(10), missing_count=2),
    RecipeCandidate("R008", "마늘간장비빔밥", total_kcal=520, total_protein=20, total_fat=10,
                    estimated_cost=3800, expiry_weight=compute_expiry_weight(14), missing_count=1),
    RecipeCandidate("R009", "들깨청경채볶음", total_kcal=210, total_protein=9, total_fat=11,
                    estimated_cost=2100, expiry_weight=compute_expiry_weight(4), missing_count=0),
    RecipeCandidate("R010", "잣두부조림", total_kcal=380, total_protein=24, total_fat=22,
                    estimated_cost=5500, expiry_weight=compute_expiry_weight(6), missing_count=1),
]

# 사용자 영양 목표 (TDEE 2000kcal, 35% 식사, 단백질 ≥ 30g, 예산 8000원)
GOAL = NutritionGoal(
    tdee_kcal=2000,
    protein_g=30,
    budget_krw=8000,
    meal_fraction=0.35,
)

print("=" * 60)
print("RefrigerAI LP 엔진 테스트")
print("=" * 60)
print(f"목표 칼로리: {GOAL.target_kcal:.0f}kcal (상한 {GOAL.max_kcal:.0f}kcal)")
print(f"단백질 최소: {GOAL.protein_g}g")
print(f"예산 상한:   {GOAL.budget_krw}원")
print()

# 목적함수 계수 확인
print("[목적함수 계수]")
coeffs = build_objective_coefficients(MOCK_CANDIDATES, GOAL)
for r in sorted(MOCK_CANDIDATES, key=lambda c: -coeffs[c.recipe_id]):
    print(f"  {r.recipe_name:20s} score={coeffs[r.recipe_id]:.4f}  "
          f"kcal={r.total_kcal}  protein={r.total_protein}g  "
          f"cost={r.estimated_cost}원  expiry_w={r.expiry_weight}")

print()

# LP 풀기
print("[LP 최적화 실행]")
result = solve_recipe_lp(
    candidates=MOCK_CANDIDATES,
    goal=GOAL,
    max_recipes=3,
    use_highs=False,  # CBC fallback (CI 환경 대응)
)

print(f"  상태: {result.status}")
print(f"  선택 레시피: {result.selected_recipes}")
print(f"  총 칼로리:  {result.total_kcal} kcal")
print(f"  총 단백질:  {result.total_protein} g")
print(f"  총 비용:    {result.total_cost} 원")
print(f"  목적함수값: {result.objective_value}")

print()
print("[선택된 레시피 상세]")
for d in result.details:
    print(f"  {d['recipe_name']:20s}  kcal={d['total_kcal']}  "
          f"protein={d['total_protein']}g  cost={d['estimated_cost']}원  "
          f"score={d['objective_score']}")

# 검증
print()
print("[제약조건 검증]")
kcal_ok = GOAL.target_kcal * 0.7 <= result.total_kcal <= GOAL.max_kcal
protein_ok = result.total_protein >= GOAL.protein_g
budget_ok = result.total_cost <= GOAL.budget_krw

print(f"  칼로리 범위 ({GOAL.target_kcal*0.7:.0f}~{GOAL.max_kcal:.0f}): "
      f"{result.total_kcal}kcal → {'✅' if kcal_ok else '❌'}")
print(f"  단백질 ≥ {GOAL.protein_g}g: {result.total_protein}g → {'✅' if protein_ok else '❌'}")
print(f"  예산 ≤ {GOAL.budget_krw}원: {result.total_cost}원 → {'✅' if budget_ok else '❌'}")
print(f"  레시피 수 ≤ 3: {len(result.selected_recipes)}개 → {'✅' if len(result.selected_recipes) <= 3 else '❌'}")
