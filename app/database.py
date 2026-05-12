from sqlalchemy import create_engine, Column, Integer, String, Float, DateTime
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
from datetime import datetime
import math

DATABASE_URL = "sqlite:///./refrigerai.db"

engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False})
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()


# ── 사용자 테이블 ──────────────────────────────────────────
class User(Base):
    __tablename__ = "users"
    id            = Column(Integer, primary_key=True)
    email         = Column(String, unique=True)
    password      = Column(String)
    height        = Column(Float)           # cm
    weight        = Column(Float)           # kg
    age           = Column(Integer)
    gender        = Column(String)          # 'male' | 'female'
    goal          = Column(String)          # '체중감량' | '근육증가' | '유지'
    activity      = Column(Float, default=1.55)   # 활동계수 (1.2~1.9)
    protein_goal  = Column(Float)           # 1회 식사 단백질 목표 (g), None이면 자동 계산
    budget        = Column(Float, default=8000.0)  # 1회 식사 예산 (원)
    meal_fraction = Column(Float, default=0.35)    # 식사 비율 (하루 칼로리 중)
    allergies     = Column(String, default="")     # 쉼표 구분 "난류,대두"
    created_at    = Column(DateTime, default=datetime.now)

    def calc_tdee(self) -> float:
        """Mifflin-St Jeor 공식으로 TDEE 계산"""
        if not all([self.height, self.weight, self.age, self.gender]):
            return 2000.0  # 기본값
        if self.gender == 'male':
            bmr = 10 * self.weight + 6.25 * self.height - 5 * self.age + 5
        else:
            bmr = 10 * self.weight + 6.25 * self.height - 5 * self.age - 161
        activity = self.activity or 1.55
        tdee = bmr * activity
        # 목표별 조정
        if self.goal == '체중감량':
            tdee *= 0.85
        elif self.goal == '근육증가':
            tdee *= 1.1
        return round(tdee, 1)

    def calc_protein_goal(self) -> float:
        """1회 식사 단백질 목표 (g)"""
        if self.protein_goal:
            return self.protein_goal
        if not self.weight:
            return 20.0
        # 목표별 단백질 계수 (g/kg/day)
        coeff = {'근육증가': 2.0, '체중감량': 1.8, '유지': 1.4}.get(self.goal, 1.4)
        daily = self.weight * coeff
        fraction = self.meal_fraction or 0.35
        return round(daily * fraction, 1)

    def get_allergies(self) -> list[str]:
        if not self.allergies:
            return []
        return [a.strip() for a in self.allergies.split(',') if a.strip()]


# ── 냉장고 재고 테이블 ────────────────────────────────────
class FridgeStock(Base):
    __tablename__ = "fridge_stocks"
    id              = Column(Integer, primary_key=True)
    user_id         = Column(Integer)
    ingredient_name = Column(String)   # KG Ingredient.name과 일치해야 함
    quantity        = Column(Float)
    unit            = Column(String)
    expiry_date     = Column(String)   # "YYYY-MM-DD" 또는 None
    created_at      = Column(DateTime, default=datetime.now)

    def days_left(self) -> int | None:
        """오늘 기준 유통기한까지 남은 일수"""
        if not self.expiry_date:
            return None
        try:
            exp = datetime.strptime(self.expiry_date, "%Y-%m-%d")
            return (exp - datetime.now()).days
        except Exception:
            return None


# ── 요리 이력 테이블 ──────────────────────────────────────
class CookHistory(Base):
    __tablename__ = "cook_history"
    id         = Column(Integer, primary_key=True)
    user_id    = Column(Integer)
    recipe_id  = Column(String)
    cooked_at  = Column(DateTime, default=datetime.now)
    calories   = Column(Float)
    cost       = Column(Float)


# ── 테이블 생성 ───────────────────────────────────────────
Base.metadata.create_all(bind=engine)
