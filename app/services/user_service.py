"""
app/services/user_service.py
User DB → NutritionGoal 변환 서비스
"""

from sqlalchemy.orm import Session
from app.database import User, FridgeStock, CookHistory, SessionLocal
from app.lp.lp_engine import NutritionGoal
from datetime import datetime, timedelta
from typing import Optional


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def get_nutrition_goal(user_id: int, db: Session) -> NutritionGoal:
    """
    User DB 레코드 → LP용 NutritionGoal 자동 생성
    """
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise ValueError(f"User {user_id} not found")

    return NutritionGoal(
        tdee_kcal=user.calc_tdee(),
        protein_g=user.calc_protein_goal(),
        budget_krw=user.budget or 8000.0,
        meal_fraction=user.meal_fraction or 0.35,
    )


def get_owned_ingredients(user_id: int, db: Session) -> list[str]:
    """
    FridgeStock → 보유 재료 이름 리스트
    """
    stocks = db.query(FridgeStock).filter(FridgeStock.user_id == user_id).all()
    return [s.ingredient_name for s in stocks]


def get_expiry_info(user_id: int, db: Session) -> dict[str, int]:
    """
    FridgeStock → {재료명: days_left} 딕셔너리
    유통기한 없는 재료는 포함하지 않음
    """
    stocks = db.query(FridgeStock).filter(FridgeStock.user_id == user_id).all()
    result = {}
    for s in stocks:
        days = s.days_left()
        if days is not None:
            result[s.ingredient_name] = days
    return result


def get_recent_recipe_ids(
    user_id: int,
    db: Session,
    days: int = 3,
) -> list[str]:
    """
    최근 N일간 요리한 레시피 ID 목록 (LP에서 제외용)
    """
    since = datetime.now() - timedelta(days=days)
    histories = (
        db.query(CookHistory)
        .filter(CookHistory.user_id == user_id, CookHistory.cooked_at >= since)
        .all()
    )
    return list({h.recipe_id for h in histories})


def get_user_allergies(user_id: int, db: Session) -> list[str]:
    """
    User.allergies → 알레르기 항목 리스트
    """
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        return []
    return user.get_allergies()
