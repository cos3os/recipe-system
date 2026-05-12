"""
app/api/recipes.py
FastAPI 레시피 추천 엔드포인트
"""

from fastapi import APIRouter, Query, HTTPException
from pydantic import BaseModel, Field
from typing import Optional

from app.lp.pipeline import run_recommendation_pipeline
from app.lp.lp_engine import NutritionGoal
from app.lp.kg_queries import fetch_recipe_detail

router = APIRouter(prefix="/recipes", tags=["recipes"])


# ─────────────────────────────────────────────
# 요청/응답 스키마
# ─────────────────────────────────────────────

class RecommendRequest(BaseModel):
    owned_ingredients: list[str] = Field(
        ..., example=["표고버섯", "마늘", "간장", "두부", "청경채"],
        description="보유 재료 목록"
    )
    tdee_kcal: float = Field(2000, description="하루 TDEE (kcal)")
    protein_g: float = Field(50, description="이 식사 최소 단백질 (g)")
    budget_krw: float = Field(5000, description="1회 식사 예산 (원)")
    meal_fraction: float = Field(0.35, description="식사가 하루 칼로리에서 차지하는 비율")
    expiry_info: Optional[dict[str, int]] = Field(
        None, example={"표고버섯": 2, "두부": 5},
        description="재료별 유통기한 남은 일수 (FridgeStock 연동)"
    )
    max_missing: int = Field(2, description="허용 미보유 재료 수")
    use_substitutes: bool = Field(True, description="대체재 활용 여부")
    max_recipes: int = Field(3, description="최대 추천 레시피 수")


class RecipeDetail(BaseModel):
    recipe_id: str
    recipe_name: str
    total_kcal: float
    total_protein: float
    estimated_cost: float
    expiry_weight: float
    missing_count: int
    objective_score: float


class RecommendResponse(BaseModel):
    status: str
    candidates_count: int
    selected_recipes: list[str]
    total_kcal: float
    total_protein: float
    total_cost: float
    objective_value: float
    details: list[RecipeDetail]
    pipeline_log: list[str]


# ─────────────────────────────────────────────
# 엔드포인트
# ─────────────────────────────────────────────

@router.post("/recommend", response_model=RecommendResponse, summary="LP 기반 레시피 추천")
async def recommend_recipes(req: RecommendRequest):
    """
    보유 재료 + 영양 목표 기반으로 최적 레시피 조합을 추천합니다.
    
    - KG에서 후보 레시피 필터링 (Cypher 쿼리)
    - LP 최적화로 영양/비용/유통기한 동시 고려
    """
    goal = NutritionGoal(
        tdee_kcal=req.tdee_kcal,
        protein_g=req.protein_g,
        budget_krw=req.budget_krw,
        meal_fraction=req.meal_fraction,
    )

    result = run_recommendation_pipeline(
        owned_ingredients=req.owned_ingredients,
        goal=goal,
        expiry_info=req.expiry_info,
        max_missing=req.max_missing,
        use_substitutes=req.use_substitutes,
        max_recipes=req.max_recipes,
    )

    lp = result["lp_result"]

    if lp is None:
        return RecommendResponse(
            status="NO_CANDIDATES",
            candidates_count=0,
            selected_recipes=[],
            total_kcal=0, total_protein=0, total_cost=0, objective_value=0,
            details=[],
            pipeline_log=result["pipeline_log"],
        )

    if lp.status not in ("Optimal", "Feasible"):
        raise HTTPException(
            status_code=422,
            detail={
                "message": f"LP 풀이 실패: {lp.status}",
                "hint": "예산/칼로리 조건을 완화하거나 재료를 추가해 주세요.",
                "pipeline_log": result["pipeline_log"],
            }
        )

    return RecommendResponse(
        status=lp.status,
        candidates_count=result["candidates_count"],
        selected_recipes=lp.selected_recipes,
        total_kcal=lp.total_kcal,
        total_protein=lp.total_protein,
        total_cost=lp.total_cost,
        objective_value=lp.objective_value,
        details=[RecipeDetail(**d) for d in lp.details],
        pipeline_log=result["pipeline_log"],
    )


@router.get(
    "",
    summary="GET 방식 간단 레시피 추천 (Swagger 테스트용)",
)
async def recommend_recipes_get(
    ingredients: str = Query(..., examples=["표고버섯,마늘,간장"], description="쉼표 구분 재료"),
    tdee: float = Query(2000),
    protein: float = Query(50),
    budget: float = Query(5000),
):
    """
    GET /recipes?ingredients=표고버섯,마늘,간장
    Swagger에서 빠르게 테스트할 수 있는 단순 버전
    """
    owned = [i.strip() for i in ingredients.split(",") if i.strip()]
    goal = NutritionGoal(tdee_kcal=tdee, protein_g=protein, budget_krw=budget)
    result = run_recommendation_pipeline(owned_ingredients=owned, goal=goal)
    lp = result["lp_result"]

    return {
        "candidates_count": result["candidates_count"],
        "status": lp.status if lp else "NO_CANDIDATES",
        "selected_recipes": lp.selected_recipes if lp else [],
        "total_kcal": lp.total_kcal if lp else 0,
        "total_protein": lp.total_protein if lp else 0,
        "total_cost": lp.total_cost if lp else 0,
        "details": lp.details if lp else [],
    }


@router.get("/{recipe_id}/substitute", summary="재료 대체재 조회")
async def get_substitutes(recipe_id: str):
    """
    특정 레시피의 재료 상세 + 대체재 정보 반환
    KG SUBSTITUTE 관계에서 직접 조회
    """
    from app.lp.kg_queries import get_driver

    query = """
    MATCH (r:Recipe {recipe_id: $recipe_id})-[c:CONTAINS]->(i:Ingredient)
    OPTIONAL MATCH (i)-[s:SUBSTITUTE]->(sub:Ingredient)
    RETURN
      i.name           AS ingredient,
      c.qty_g          AS qty_g,
      c.section_type   AS section_type,
      collect({
        name: sub.name,
        final_similarity: s.final_similarity,
        cost_diff: s.cost_diff,
        shared_taste: s.shared_taste
      }) AS substitutes
    ORDER BY c.section_type DESC
    """

    driver = get_driver()
    with driver.session() as session:
        result = session.run(query, recipe_id=recipe_id)
        records = [dict(r) for r in result]
    driver.close()

    if not records:
        raise HTTPException(status_code=404, detail=f"레시피 {recipe_id}를 찾을 수 없습니다.")

    return {"recipe_id": recipe_id, "ingredients": records}


# ─────────────────────────────────────────────
# user_id 기반 자동 추천 (동적 레이어)
# ─────────────────────────────────────────────

class UserRecommendResponse(BaseModel):
    user_id: int
    tdee_kcal: float
    target_kcal: float
    protein_goal: float
    budget: float
    owned_count: int
    allergy_list: list[str]
    status: str
    selected_recipes: list[str]
    total_kcal: float
    total_protein: float
    total_cost: float
    details: list[RecipeDetail]
    pipeline_log: list[str]


@router.post("/recommend/user/{user_id}", response_model=UserRecommendResponse,
             summary="user_id 기반 자동 추천 (동적 레이어)")
async def recommend_for_user(
    user_id: int,
    max_missing: int = Query(2, description="허용 미보유 재료 수"),
    max_recipes: int = Query(3, description="최대 추천 레시피 수"),
    exclude_recent_days: int = Query(3, description="최근 N일 요리한 레시피 제외"),
):
    """
    user_id만 넣으면 DB에서 자동으로:
    - User → TDEE, 단백질 목표, 예산, 알레르기
    - FridgeStock → 보유 재료 + 유통기한
    - CookHistory → 최근 요리한 레시피 제외
    """
    from app.database import SessionLocal
    from app.lp.pipeline import run_pipeline_for_user
    from app.services.user_service import (
        get_nutrition_goal, get_owned_ingredients, get_user_allergies
    )

    db = SessionLocal()
    try:
        result = run_pipeline_for_user(
            user_id=user_id,
            db=db,
            max_missing=max_missing,
            max_recipes=max_recipes,
            exclude_recent_days=exclude_recent_days,
        )
        goal    = get_nutrition_goal(user_id, db)
        owned   = get_owned_ingredients(user_id, db)
        allergy = get_user_allergies(user_id, db)
    finally:
        db.close()

    lp = result["lp_result"]
    if lp is None:
        return UserRecommendResponse(
            user_id=user_id, tdee_kcal=goal.tdee_kcal,
            target_kcal=goal.target_kcal, protein_goal=goal.protein_g,
            budget=goal.budget_krw, owned_count=len(owned),
            allergy_list=allergy, status="NO_CANDIDATES",
            selected_recipes=[], total_kcal=0, total_protein=0, total_cost=0,
            details=[], pipeline_log=result["pipeline_log"],
        )

    return UserRecommendResponse(
        user_id=user_id,
        tdee_kcal=goal.tdee_kcal,
        target_kcal=goal.target_kcal,
        protein_goal=goal.protein_g,
        budget=goal.budget_krw,
        owned_count=len(owned),
        allergy_list=allergy,
        status=lp.status,
        selected_recipes=lp.selected_recipes,
        total_kcal=lp.total_kcal,
        total_protein=lp.total_protein,
        total_cost=lp.total_cost,
        details=[RecipeDetail(**d) for d in lp.details],
        pipeline_log=result["pipeline_log"],
    )
