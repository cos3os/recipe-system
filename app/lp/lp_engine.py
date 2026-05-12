"""
lp_engine.py
RefrigerAI LP 최적화 엔진
목적함수: 영양 충족도 최대화 + 비용 최소화 + 유통기한 가중치
솔버: PuLP + HiGHS
"""

from pulp import (
    LpProblem, LpMaximize, LpVariable, LpBinary,
    lpSum, value, PULP_CBC_CMD, HiGHS_CMD, LpStatus
)
from dataclasses import dataclass, field
from typing import Optional
import math


# ─────────────────────────────────────────────
# 데이터 클래스 정의
# ─────────────────────────────────────────────

@dataclass
class NutritionGoal:
    """사용자 영양 목표 (TDEE 기반)"""
    tdee_kcal: float          # 하루 총 칼로리 목표
    protein_g: float          # 최소 단백질 (g)
    budget_krw: float         # 1회 식사 예산 (원)
    meal_fraction: float = 0.35   # 이 식사가 하루 중 차지하는 비율 (기본 35%)

    @property
    def target_kcal(self) -> float:
        return self.tdee_kcal * self.meal_fraction

    @property
    def max_kcal(self) -> float:
        return self.tdee_kcal * self.meal_fraction * 1.3   # 30% 오버 허용 (레시피 조합 여유)


@dataclass
class RecipeCandidate:
    """LP 입력용 레시피 후보"""
    recipe_id: str
    recipe_name: str
    total_kcal: float
    total_protein: float
    total_fat: float
    total_carb: float = 0.0
    estimated_cost: float = 0.0       # 원 단위 (재료 합산)
    expiry_weight: float = 1.0        # 유통기한 가중치 (D-day 가까울수록 높음)
    missing_count: int = 0            # 미보유 필수 재료 수
    cuisine_type: str = ""


@dataclass
class LPResult:
    """LP 결과"""
    status: str
    selected_recipes: list[str]
    total_kcal: float
    total_protein: float
    total_cost: float
    objective_value: float
    details: list[dict] = field(default_factory=list)


# ─────────────────────────────────────────────
# 비용 추정 함수
# ─────────────────────────────────────────────

def estimate_recipe_cost(recipe_detail: list[dict]) -> float:
    """
    레시피 재료 상세로 총 비용 추정
    price_per100g * qty_g / 100
    """
    total = 0.0
    for item in recipe_detail:
        price = item.get("price_per100g") or 0
        qty = item.get("qty_g") or 0
        total += price * qty / 100
    return round(total, 1)


# ─────────────────────────────────────────────
# 유통기한 가중치 계산
# ─────────────────────────────────────────────

def compute_expiry_weight(days_left: Optional[int]) -> float:
    """
    유통기한 D-day 기준 가중치
    days_left=None → 가중치 1.0 (정보 없음, 중립)
    days_left<=0   → 3.0 (오늘까지 / 이미 지남, 최우선)
    days_left<=2   → 2.5
    days_left<=5   → 2.0
    days_left<=10  → 1.5
    else           → 1.0
    """
    if days_left is None:
        return 1.0
    if days_left <= 0:
        return 3.0
    if days_left <= 2:
        return 2.5
    if days_left <= 5:
        return 2.0
    if days_left <= 10:
        return 1.5
    return 1.0


# ─────────────────────────────────────────────
# 정규화 유틸
# ─────────────────────────────────────────────

def _normalize(values: list[float]) -> list[float]:
    """Min-max 정규화 (0~1). 동일값이면 모두 1.0 반환."""
    mn, mx = min(values), max(values)
    if mx == mn:
        return [1.0] * len(values)
    return [(v - mn) / (mx - mn) for v in values]


# ─────────────────────────────────────────────
# LP 목적함수 계수 계산
# ─────────────────────────────────────────────

def build_objective_coefficients(
    candidates: list[RecipeCandidate],
    goal: NutritionGoal,
    w_nutrition: float = 0.5,
    w_cost: float = 0.3,
    w_expiry: float = 0.2,
) -> dict[str, float]:
    """
    레시피별 LP 목적함수 계수 계산
    
    score_i = w_nutrition * nutrition_score_i
            + w_cost * (1 - cost_score_i)     ← 비용은 낮을수록 좋음
            + w_expiry * expiry_weight_i       ← 유통기한은 높을수록 우선

    Args:
        w_nutrition: 영양 충족도 가중치
        w_cost: 비용 최소화 가중치
        w_expiry: 유통기한 가중치
    
    Returns:
        {recipe_id: coefficient} dict
    """
    assert abs(w_nutrition + w_cost + w_expiry - 1.0) < 1e-6, "가중치 합이 1이어야 합니다"

    # 영양 충족도: target_kcal 대비 얼마나 가까운가 (거리가 작을수록 좋음)
    kcal_diffs = [abs(c.total_kcal - goal.target_kcal) for c in candidates]
    protein_ratios = [min(c.total_protein / max(goal.protein_g, 1), 1.0) for c in candidates]

    norm_kcal_diffs = _normalize(kcal_diffs)
    # kcal_diff는 낮을수록 좋으므로 반전
    nutrition_scores = [
        0.6 * (1 - norm_kcal_diffs[i]) + 0.4 * protein_ratios[i]
        for i in range(len(candidates))
    ]

    # 비용 정규화
    costs = [c.estimated_cost for c in candidates]
    norm_costs = _normalize(costs)

    # 유통기한 정규화
    expiry_weights = [c.expiry_weight for c in candidates]
    norm_expiry = _normalize(expiry_weights)

    coefficients = {}
    for i, c in enumerate(candidates):
        score = (
            w_nutrition * nutrition_scores[i]
            + w_cost * (1 - norm_costs[i])
            + w_expiry * norm_expiry[i]
        )
        # 미보유 재료가 많을수록 페널티
        penalty = 0.1 * c.missing_count
        coefficients[c.recipe_id] = max(score - penalty, 0.0)

    return coefficients


# ─────────────────────────────────────────────
# LP 솔버
# ─────────────────────────────────────────────

def solve_recipe_lp(
    candidates: list[RecipeCandidate],
    goal: NutritionGoal,
    max_recipes: int = 3,
    w_nutrition: float = 0.5,
    w_cost: float = 0.3,
    w_expiry: float = 0.2,
    use_highs: bool = True,
    exclude_recipe_ids: list[str] = None,   # 최근 요리한 레시피 제외
) -> LPResult:
    """
    LP 최적화 실행
    
    결정변수: x_i ∈ {0, 1}  (레시피 i 선택 여부, Binary)
    
    목적함수 (최대화):
        max Σ score_i * x_i
    
    제약조건:
        (C1) Σ total_kcal_i * x_i <= max_kcal          (칼로리 상한)
        (C2) Σ total_kcal_i * x_i >= target_kcal * 0.7 (칼로리 하한 - 너무 적게 먹지 않도록)
        (C3) Σ total_protein_i * x_i >= protein_g       (단백질 최소)
        (C4) Σ estimated_cost_i * x_i <= budget_krw     (예산 상한)
        (C5) Σ x_i <= max_recipes                       (최대 레시피 수)
        (C6) Σ x_i >= 1                                 (최소 1개 선택)
    """
    # 최근 요리한 레시피 제외
    if exclude_recipe_ids:
        candidates = [c for c in candidates if c.recipe_id not in exclude_recipe_ids]

    if not candidates:
        return LPResult(
            status="NO_CANDIDATES",
            selected_recipes=[],
            total_kcal=0, total_protein=0, total_cost=0, objective_value=0
        )

    # 목적함수 계수
    obj_coeff = build_objective_coefficients(candidates, goal, w_nutrition, w_cost, w_expiry)

    # LP 문제 정의
    prob = LpProblem("RefrigerAI_Recipe_Selection", LpMaximize)

    # 결정변수: x_i (Binary)
    x = {c.recipe_id: LpVariable(f"x_{c.recipe_id}", cat=LpBinary) for c in candidates}

    # 목적함수
    prob += lpSum(obj_coeff[c.recipe_id] * x[c.recipe_id] for c in candidates)

    # 제약조건
    # C1: 칼로리 상한
    prob += lpSum(c.total_kcal * x[c.recipe_id] for c in candidates) <= goal.max_kcal, "칼로리_상한"

    # C3: 단백질 최소
    prob += lpSum(c.total_protein * x[c.recipe_id] for c in candidates) >= goal.protein_g, "단백질_최소"

    # C4: 예산 상한
    prob += lpSum(c.estimated_cost * x[c.recipe_id] for c in candidates) <= goal.budget_krw, "예산_상한"

    # C5: 최대 레시피 수
    prob += lpSum(x[c.recipe_id] for c in candidates) <= max_recipes, "최대_레시피"

    # C6: 최소 1개 선택
    prob += lpSum(x[c.recipe_id] for c in candidates) >= 1, "최소_레시피"

    # 솔버 선택 (HiGHS 시도 → 실패시 CBC fallback)
    solved = False
    if use_highs:
        try:
            prob.solve(HiGHS_CMD(msg=False))
            solved = True
        except Exception:
            pass
    if not solved:
        prob.solve(PULP_CBC_CMD(msg=False))

    # 결과 추출
    status = LpStatus[prob.status]
    selected = [c for c in candidates if value(x[c.recipe_id]) == 1.0]

    total_kcal = sum(c.total_kcal for c in selected)
    total_protein = sum(c.total_protein for c in selected)
    total_cost = sum(c.estimated_cost for c in selected)
    obj_val = value(prob.objective) or 0.0

    details = [
        {
            "recipe_id": c.recipe_id,
            "recipe_name": c.recipe_name,
            "total_kcal": c.total_kcal,
            "total_protein": c.total_protein,
            "estimated_cost": c.estimated_cost,
            "expiry_weight": c.expiry_weight,
            "missing_count": c.missing_count,
            "objective_score": round(obj_coeff[c.recipe_id], 4),
        }
        for c in selected
    ]

    return LPResult(
        status=status,
        selected_recipes=[c.recipe_id for c in selected],
        total_kcal=round(total_kcal, 1),
        total_protein=round(total_protein, 1),
        total_cost=round(total_cost, 1),
        objective_value=round(obj_val, 4),
        details=details,
    )
