"""
seed_db.py
테스트용 더미 데이터 삽입 스크립트
실행: python seed_db.py
"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app.database import SessionLocal, Base, engine, User, FridgeStock, CookHistory
from datetime import datetime, timedelta

# 테이블 초기화 후 재생성
Base.metadata.drop_all(bind=engine)
Base.metadata.create_all(bind=engine)

db = SessionLocal()

# ── 유저 1: 체중감량 목표 20대 여성 ──────────────────────
user1 = User(
    id=1,
    email="sumin@test.com",
    password="test1234",
    height=163.0,
    weight=55.0,
    age=24,
    gender="female",
    goal="체중감량",
    activity=1.375,      # 가벼운 운동
    budget=8000.0,
    meal_fraction=0.35,
    allergies="",        # 알레르기 없음
)

# ── 유저 2: 근육증가 목표 20대 남성 (알레르기 있음) ──────
user2 = User(
    id=2,
    email="junho@test.com",
    password="test1234",
    height=178.0,
    weight=75.0,
    age=26,
    gender="male",
    goal="근육증가",
    activity=1.55,       # 보통 운동
    budget=10000.0,
    meal_fraction=0.35,
    allergies="갑각류",   # 새우 포함 레시피 제외
)

db.add_all([user1, user2])
db.commit()

print(f"✅ User 2명 생성")
print(f"   수민 TDEE: {user1.calc_tdee():.0f}kcal, 단백질목표: {user1.calc_protein_goal()}g")
print(f"   준호 TDEE: {user2.calc_tdee():.0f}kcal, 단백질목표: {user2.calc_protein_goal()}g")

# ── 수민 냉장고 재료 ──────────────────────────────────────
today = datetime.now()

sumin_fridge = [
    # (재료명, 수량, 단위, 유통기한 D+N)
    ("두부",       1,   "모",   2),    # D+2 임박
    ("표고버섯",   100, "g",    3),    # D+3
    ("청경채",     80,  "g",    2),    # D+2 임박
    ("팽이버섯",   100, "g",    4),
    ("마늘",       50,  "g",    14),
    ("간장",       200, "ml",   None), # 유통기한 없음
    ("된장",       100, "g",    None),
    ("들깨",       50,  "g",    30),
    ("참기름",     100, "ml",   None),
    ("소금",       200, "g",    None),
    ("멥쌀밥",     200, "g",    1),    # D+1 오늘 먹어야 함
    ("닭고기",     200, "g",    2),    # D+2 임박
    ("대파",       100, "g",    5),
    ("당근",       100, "g",    7),
    ("다시마",     20,  "g",    None),
    ("멸치",       30,  "g",    None),
    ("양파",       100, "g",    10),
    ("고추",       50,  "g",    5),
    ("감자",       150, "g",    14),
    ("애호박",     100, "g",    4),
]

for name, qty, unit, days in sumin_fridge:
    expiry = (today + timedelta(days=days)).strftime("%Y-%m-%d") if days else None
    db.add(FridgeStock(
        user_id=1,
        ingredient_name=name,
        quantity=qty,
        unit=unit,
        expiry_date=expiry,
    ))

db.commit()
print(f"\n✅ 수민 냉장고 {len(sumin_fridge)}개 재료 등록")
print(f"   유통기한 임박 재료: 두부(D+2), 청경채(D+2), 멥쌀밥(D+1), 닭고기(D+2), 표고버섯(D+3)")

# ── 준호 냉장고 재료 ──────────────────────────────────────
junho_fridge = [
    ("닭고기",     300, "g",    3),
    ("달걀",       6,   "개",   7),
    ("두부",       1,   "모",   5),
    ("양파",       150, "g",    10),
    ("마늘",       50,  "g",    14),
    ("간장",       200, "ml",   None),
    ("참기름",     100, "ml",   None),
    ("소금",       200, "g",    None),
    ("고추장",     150, "g",    None),
    ("된장",       100, "g",    None),
    ("멥쌀밥",     200, "g",    1),
    ("당근",       80,  "g",    6),
    ("대파",       80,  "g",    4),
    ("표고버섯",   60,  "g",    3),
]

for name, qty, unit, days in junho_fridge:
    expiry = (today + timedelta(days=days)).strftime("%Y-%m-%d") if days else None
    db.add(FridgeStock(
        user_id=2,
        ingredient_name=name,
        quantity=qty,
        unit=unit,
        expiry_date=expiry,
    ))

db.commit()
print(f"\n✅ 준호 냉장고 {len(junho_fridge)}개 재료 등록")

# ── 수민 요리 이력 (최근 3일 — 이 레시피들은 추천에서 제외됨) ──
db.add(CookHistory(
    user_id=1,
    recipe_id="329",   # 채소비빔밥 — 어제 먹었으니 제외
    cooked_at=datetime.now() - timedelta(days=1),
    calories=380,
    cost=1524,
))
db.commit()
print(f"\n✅ 수민 요리이력 1개 (채소비빔밥 — 추천 제외 대상)")

# ── 최종 확인 ─────────────────────────────────────────────
print("\n" + "="*50)
print("📊 DB 삽입 결과")
print(f"  User:        {db.query(User).count()}명")
print(f"  FridgeStock: {db.query(FridgeStock).count()}개")
print(f"  CookHistory: {db.query(CookHistory).count()}개")
print("\n▶ 테스트 방법:")
print("  POST /recipes/recommend/user/1  ← 수민 (체중감량, 유통기한 임박재료 우선)")
print("  POST /recipes/recommend/user/2  ← 준호 (근육증가, 갑각류 알레르기)")

db.close()
