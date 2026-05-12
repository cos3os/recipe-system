"""
app/lp/pipeline.py
KG 쿼리 결과 → LP 입력 변환 → 최적화 실행 오케스트레이터
user_id 기반으로 DB에서 자동으로 재료/목표/유통기한 조회
"""

from .kg_queries import fetch_candidate_recipes
from .lp_engine import (
    RecipeCandidate, NutritionGoal, LPResult,
    compute_expiry_weight, solve_recipe_lp
)
from typing import Optional


def kg_records_to_candidates(
    kg_records: list[dict],
    expiry_info: Optional[dict[str, int]] = None,
    allergy_list: Optional[list[str]] = None,
) -> list[RecipeCandidate]:
    candidates = []
    for r in kg_records:
        all_ingredients = r.get("all_ingredients", [])

        # 알레르기 필터
        if allergy_list:
            skip = False
            for ing in all_ingredients:
                allergens = ing.get("allergens") or ""
                for allergy in allergy_list:
                    if allergy in str(allergens):
                        skip = True
                        break
                if skip:
                    break
            if skip:
                continue

        # 비용 추정
        cost = 0.0
        for ing in all_ingredients:
            price = ing.get("price_per100") or 0
            qty = ing.get("qty_g") or 0
            try:
                cost += float(price) * float(qty) / 100
            except Exception:
                pass

        # 유통기한 가중치
        expiry_weight = 1.0
        if expiry_info and all_ingredients:
            weights = [
                compute_expiry_weight(expiry_info.get(ing["name"]))
                for ing in all_ingredients
            ]
            expiry_weight = max(weights)

        candidates.append(RecipeCandidate(
            recipe_id=str(r.get("recipe_id", "")),
            recipe_name=r.get("recipe_name", ""),
            total_kcal=float(r.get("total_kcal") or 0),
            total_protein=float(r.get("total_protein") or 0),
            total_fat=float(r.get("total_fat") or 0),
            estimated_cost=round(cost, 1),
            expiry_weight=expiry_weight,
            missing_count=int(r.get("missing_count") or r.get("unresolved_count") or 0),
            cuisine_type=r.get("cuisine_type", ""),
        ))

    return candidates


def run_recommendation_pipeline(
    owned_ingredients: list[str],
    goal: NutritionGoal,
    expiry_info: Optional[dict[str, int]] = None,
    allergy_list: Optional[list[str]] = None,
    exclude_recipe_ids: Optional[list[str]] = None,
    max_missing: int = 2,
    use_substitutes: bool = False,
    max_recipes: int = 3,
    w_nutrition: float = 0.5,
    w_cost: float = 0.3,
    w_expiry: float = 0.2,
) -> dict:
    log = []
    log.append(f"[Step 1] KG 쿼리 — 보유 재료 {len(owned_ingredients)}개")
    kg_records = fetch_candidate_recipes(
        owned_ingredients=owned_ingredients,
        max_missing=max_missing,
        use_substitutes=use_substitutes,
    )
    log.append(f"[Step 1] 후보 {len(kg_records)}개 발견")

    if not kg_records:
        return {"candidates_count": 0, "lp_result": None, "pipeline_log": log}

    log.append("[Step 2] RecipeCandidate 변환 (알레르기 필터)")
    candidates = kg_records_to_candidates(kg_records, expiry_info, allergy_list)
    log.append(f"[Step 2] 필터 후 {len(candidates)}개")

    log.append("[Step 3] LP 최적화")
    lp_result = solve_recipe_lp(
        candidates=candidates,
        goal=goal,
        max_recipes=max_recipes,
        w_nutrition=w_nutrition,
        w_cost=w_cost,
        w_expiry=w_expiry,
        exclude_recipe_ids=exclude_recipe_ids,
    )
    log.append(f"[Step 3] 상태: {lp_result.status}, 선택: {lp_result.selected_recipes}")

    return {
        "candidates_count": len(candidates),
        "lp_result": lp_result,
        "pipeline_log": log,
    }


def run_pipeline_for_user(
    user_id: int,
    db,
    max_missing: int = 2,
    max_recipes: int = 3,
    exclude_recent_days: int = 3,
) -> dict:
    """
    user_id만 넣으면 DB에서 모든 정보 자동 조회 후 LP 실행

    DB(User)          → NutritionGoal (TDEE, 단백질, 예산)
    DB(FridgeStock)   → owned_ingredients + expiry_info
    DB(CookHistory)   → exclude_recipe_ids (최근 N일 제외)
    DB(User.allergies)→ allergy_list
    """
    from app.services.user_service import (
        get_nutrition_goal,
        get_owned_ingredients,
        get_expiry_info,
        get_recent_recipe_ids,
        get_user_allergies,
    )

    goal        = get_nutrition_goal(user_id, db)
    owned       = get_owned_ingredients(user_id, db)
    expiry_info = get_expiry_info(user_id, db)
    exclude_ids = get_recent_recipe_ids(user_id, db, days=exclude_recent_days)
    allergies   = get_user_allergies(user_id, db)

    return run_recommendation_pipeline(
        owned_ingredients=owned,
        goal=goal,
        expiry_info=expiry_info,
        allergy_list=allergies,
        exclude_recipe_ids=exclude_ids,
        max_missing=max_missing,
        max_recipes=max_recipes,
    )
