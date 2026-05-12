"""
RefrigerAI - KG 쿼리 모듈 (냉장고 재료 매칭)
──────────────────────────────────────────────
Mode 1: Neo4j Aura 직접 연결 (본 서버)
Mode 2: CSV 기반 pandas 매칭 (fallback / 로컬 개발)

Neo4j 연결 실패 시 자동으로 CSV fallback 전환.
"""
from __future__ import annotations
import os
import pandas as pd
from pathlib import Path
from typing import Optional

# ── Neo4j 설정 (환경변수 또는 기본값) ──────────────────────
NEO4J_URI = os.getenv("NEO4J_URI", "neo4j+s://7fd59d9c.databases.neo4j.io")
NEO4J_USER = os.getenv("NEO4J_USER", "neo4j")
NEO4J_PASSWORD = os.getenv("NEO4J_PASSWORD", "")  # .env에서 로드 권장

# ── CSV 경로 ───────────────────────────────────────────────
BASE = Path(__file__).parent.parent / "data"
MASTER_CSV = BASE / "mini_recipes_master.csv"
INGR_CSV = BASE / "mini_recipes_ingredients.csv"
SUBS_CSV = BASE / "mini_substitutes.csv"


# ══════════════════════════════════════════════════════════
# CSV 기반 매칭 (fallback)
# ══════════════════════════════════════════════════════════
class CSVMatcher:
    """CSV 파일 기반 냉장고 매칭 — Neo4j 없이 동작"""

    def __init__(self, master_csv=None, ingr_csv=None, subs_csv=None):
        self.master = pd.read_csv(master_csv or MASTER_CSV)
        self.ingr = pd.read_csv(ingr_csv or INGR_CSV)
        try:
            self.subs = pd.read_csv(subs_csv or SUBS_CSV)
        except FileNotFoundError:
            self.subs = pd.DataFrame(columns=["from", "to", "final_similarity"])

    def get_all_ingredients(self) -> list[str]:
        """전체 재료 목록 (양념 제외)"""
        return sorted(
            self.ingr[self.ingr["section_type"] == "ingredient"]["unique"]
            .dropna()
            .unique()
            .tolist()
        )

    def match_recipes(self, fridge: list[str], include_seasoning: bool = False) -> list[dict]:
        """냉장고 재료로 만들 수 있는 레시피 매칭

        Args:
            fridge: 보유 재료 리스트 (unique 컬럼 기준)
            include_seasoning: True면 양념도 매칭 대상에 포함

        Returns:
            [{"recipe_id", "recipe_name", "method", "dish_type",
              "matched", "missing", "total_required",
              "match_rate", "kcal"}]
            match_rate 내림차순 정렬
        """
        fridge_set = set(fridge)

        # 필터: ingredient만 or ingredient+seasoning
        if include_seasoning:
            df = self.ingr.dropna(subset=["unique"])
        else:
            df = self.ingr[self.ingr["section_type"] == "ingredient"].dropna(subset=["unique"])

        results = []
        for rid in df["recipe_id"].unique():
            recipe_ingr = df[df["recipe_id"] == rid]
            required = set(recipe_ingr["unique"].tolist())
            matched = required & fridge_set
            missing = required - fridge_set

            meta = self.master[self.master["recipe_id"] == rid].iloc[0]

            results.append({
                "recipe_id": int(rid),
                "recipe_name": meta["name"],
                "method": meta["method"],
                "dish_type": meta["dish_type"],
                "matched": sorted(matched),
                "missing": sorted(missing),
                "total_required": len(required),
                "matched_count": len(matched),
                "match_rate": round(len(matched) / len(required), 2) if required else 0,
                "kcal": meta["kcal"],
            })

        results.sort(key=lambda x: (-x["match_rate"], -x["matched_count"]))
        return results

    def get_recipe_detail(self, recipe_id: int) -> Optional[dict]:
        """레시피 상세 정보 반환"""
        row = self.master[self.master["recipe_id"] == recipe_id]
        if row.empty:
            return None
        r = row.iloc[0]
        ingr_df = self.ingr[self.ingr["recipe_id"] == recipe_id]

        return {
            "recipe_id": int(r["recipe_id"]),
            "name": r["name"],
            "method": r["method"],
            "dish_type": r["dish_type"],
            "kcal": r["kcal"],
            "protein_g": r["protein_g"],
            "fat_g": r["fat_g"],
            "carb_g": r["carb_g"],
            "cooking_steps": r["cooking_steps"],
            "ingredients": [
                {"name": row["name"], "unique": row["unique"],
                 "qty_g": row["qty_g"], "section_type": row["section_type"]}
                for _, row in ingr_df.iterrows()
            ],
        }

    def get_substitutes(self, ingredient: str) -> list[dict]:
        """대체 재료 조회 (실제 CSV 헤더 반영)"""
        if self.subs.empty or "ingredient_a" not in self.subs.columns:
            return []
            
        matches = self.subs[self.subs["ingredient_a"] == ingredient]
        return [
            {"substitute": row["ingredient_b"], "similarity": row.get("final_similarity", 0)}
            for _, row in matches.iterrows()
        ]


# ══════════════════════════════════════════════════════════
# Neo4j 매칭 (본 서버용)
# ══════════════════════════════════════════════════════════
class Neo4jMatcher:
    """Neo4j 직접 연결 매칭"""

    def __init__(self, uri=None, user=None, password=None):
        from neo4j import GraphDatabase
        self.driver = GraphDatabase.driver(
            uri or NEO4J_URI,
            auth=(user or NEO4J_USER, password or NEO4J_PASSWORD),
        )
        # 연결 테스트
        with self.driver.session() as s:
            s.run("RETURN 1")

    def close(self):
        self.driver.close()

    def get_all_ingredients(self) -> list[str]:
        with self.driver.session() as s:
            result = s.run(
                "MATCH (i:Ingredient) RETURN i.name AS name ORDER BY name"
            )
            return [r["name"] for r in result]

    def match_recipes(self, fridge: list[str], include_seasoning: bool = False) -> list[dict]:
        section_filter = "" if include_seasoning else "{section_type: 'ingredient'}"
        query = f"""
        MATCH (r:Recipe)-[:CONTAINS {section_filter}]->(i:Ingredient)
        WITH r, collect(DISTINCT i.name) AS required, $fridge AS fridge
        WITH r, required,
             [x IN required WHERE x IN fridge] AS matched,
             [x IN required WHERE NOT x IN fridge] AS missing
        RETURN r.name AS recipe_name, r.recipe_id AS recipe_id,
               r.method AS method, r.dish_type AS dish_type,
               r.kcal AS kcal,
               matched, missing, required,
               size(matched) AS matched_count,
               size(required) AS total_required,
               round(toFloat(size(matched)) / size(required), 2) AS match_rate
        ORDER BY match_rate DESC, matched_count DESC
        """
        with self.driver.session() as s:
            result = s.run(query, fridge=fridge)
            return [
                {
                    "recipe_id": r["recipe_id"],
                    "recipe_name": r["recipe_name"],
                    "method": r["method"],
                    "dish_type": r["dish_type"],
                    "matched": r["matched"],
                    "missing": r["missing"],
                    "total_required": r["total_required"],
                    "matched_count": r["matched_count"],
                    "match_rate": r["match_rate"],
                    "kcal": r["kcal"],
                }
                for r in result
            ]

    def get_substitutes(self, ingredient: str) -> list[dict]:
        query = """
        MATCH (a:Ingredient {name: $name})-[r:SUBSTITUTE]->(b:Ingredient)
        RETURN b.name AS substitute, r.final_similarity AS similarity
        ORDER BY r.final_similarity DESC
        """
        with self.driver.session() as s:
            result = s.run(query, name=ingredient)
            return [{"substitute": r["substitute"], "similarity": r["similarity"]} for r in result]


# ══════════════════════════════════════════════════════════
# 팩토리: 자동으로 Neo4j 또는 CSV 선택
# ══════════════════════════════════════════════════════════
def create_matcher(csv_dir: str = None):
    """Neo4j 연결 시도 → 실패 시 CSV fallback 반환"""
    if NEO4J_PASSWORD:
        try:
            matcher = Neo4jMatcher()
            print("✅ Neo4j 연결 성공")
            return matcher
        except Exception as e:
            print(f"⚠️ Neo4j 연결 실패 ({e}), CSV fallback 사용")

    if csv_dir:
        return CSVMatcher(
            master_csv=os.path.join(csv_dir, "mini_recipes_master.csv"),
            ingr_csv=os.path.join(csv_dir, "mini_recipes_ingredients.csv"),
            subs_csv=os.path.join(csv_dir, "mini_substitutes.csv"),
        )
    return CSVMatcher()


# ══════════════════════════════════════════════════════════
# 테스트
# ══════════════════════════════════════════════════════════
if __name__ == "__main__":
    import sys

    csv_dir = sys.argv[1] if len(sys.argv) > 1 else None
    matcher = CSVMatcher(
        master_csv=csv_dir and os.path.join(csv_dir, "mini_recipes_master.csv"),
        ingr_csv=csv_dir and os.path.join(csv_dir, "mini_recipes_ingredients.csv"),
        subs_csv=csv_dir and os.path.join(csv_dir, "mini_substitutes.csv"),
    ) if csv_dir else CSVMatcher()

    print("=== 전체 재료 목록 ===")
    all_ingr = matcher.get_all_ingredients()
    print(f"  {len(all_ingr)}개: {all_ingr}\n")

    # 시나리오 1: 재료 많음
    fridge1 = ["두부", "달걀", "양파", "마늘", "표고버섯", "당근"]
    print(f"🧊 냉장고: {fridge1}")
    for r in matcher.match_recipes(fridge1):
        status = "✅ 가능" if r["match_rate"] == 1.0 else f"⚠️ 부족 {r['missing']}"
        print(f"  [{r['match_rate']:.0%}] {r['recipe_name']} — {status}")

    # 시나리오 2: 재료 적음
    print()
    fridge2 = ["두부", "양파"]
    print(f"🧊 냉장고: {fridge2}")
    for r in matcher.match_recipes(fridge2):
        print(f"  [{r['match_rate']:.0%}] {r['recipe_name']} — 부족: {r['missing']}")