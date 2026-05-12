"""
kg_queries.py
KG(Neo4j)에서 LP 입력 데이터를 추출하는 Cypher 쿼리 모듈
"""

from neo4j import GraphDatabase
from typing import Optional
import os

NEO4J_URI = os.getenv("NEO4J_URI", "neo4j+s://7fd59d9c.databases.neo4j.io")
NEO4J_USER = os.getenv("NEO4J_USER", "neo4j")
NEO4J_PASSWORD = os.getenv("NEO4J_PASSWORD", "Av413XCAB4Sr8bk2evir0KAeam5ysVnq8Ir2WLVXfAU")


def get_driver():
    return GraphDatabase.driver(NEO4J_URI, auth=(NEO4J_USER, NEO4J_PASSWORD))


# ─────────────────────────────────────────────
# 1. 보유 재료 기반 후보 레시피 필터링
# ─────────────────────────────────────────────
QUERY_CANDIDATE_RECIPES = """
MATCH (r:Recipe)-[c:CONTAINS]->(i:Ingredient)
WHERE c.section_type = 'ingredient'

WITH r,
     collect(i.name) AS required_ingredients

WITH r,
     required_ingredients,
     [x IN required_ingredients WHERE NOT x IN $owned] AS missing

WHERE size(missing) <= $max_missing

MATCH (r)-[c2:CONTAINS]->(i2:Ingredient)

WITH r,
     required_ingredients,
     missing,
     collect({
       name:           i2.name,
       qty_g:          c2.qty_g,
       section_type:   c2.section_type,
       kcal_per100:    i2.kcal,
       protein_per100: i2.protein_g,
       carb_per100:    i2.carb_g,
       fat_per100:     i2.fat_g,
       sodium_per100:  i2.sodium_mg,
       price_per100:   i2.price_per_100g,
       allergens:      i2.allergy
     }) AS all_ingredients

RETURN
  r.recipe_id    AS recipe_id,
  r.name         AS recipe_name,
  r.dish_type    AS cuisine_type,
  r.kcal         AS total_kcal,
  r.protein_g    AS total_protein,
  r.carb_g       AS total_carb,
  r.fat_g        AS total_fat,
  required_ingredients,
  missing,
  size(missing)  AS missing_count,
  all_ingredients

ORDER BY missing_count ASC, r.kcal ASC
"""


# ─────────────────────────────────────────────
# 2. 대체재 포함 후보 레시피 필터링 (SUBSTITUTE 활용)
# ─────────────────────────────────────────────
QUERY_CANDIDATE_WITH_SUBSTITUTES = """
MATCH (r:Recipe)-[c:CONTAINS]->(i:Ingredient)
WHERE c.section_type = 'ingredient'

OPTIONAL MATCH (i)<-[:SUBSTITUTE]-(sub:Ingredient)
WHERE NOT i.name IN $owned AND sub.name IN $owned

WITH r,
     i,
     c,
     sub,
     CASE WHEN i.name IN $owned THEN i.name
          WHEN sub IS NOT NULL THEN sub.name
          ELSE NULL END AS resolvable_as

WITH r,
     collect({
       original:      i.name,
       resolved:      resolvable_as,
       qty_g:         c.qty_g,
       is_substitute: (sub IS NOT NULL AND NOT i.name IN $owned)
     }) AS ingredient_resolution

WITH r,
     ingredient_resolution,
     [x IN ingredient_resolution WHERE x.resolved IS NULL] AS unresolved

WHERE size(unresolved) <= $max_missing

RETURN
  r.recipe_id        AS recipe_id,
  r.name             AS recipe_name,
  r.kcal             AS total_kcal,
  r.protein_g        AS total_protein,
  r.fat_g            AS total_fat,
  ingredient_resolution,
  size(unresolved)   AS unresolved_count

ORDER BY unresolved_count ASC
"""


# ─────────────────────────────────────────────
# 3. 특정 레시피 상세 재료 조회 (LP용)
# ─────────────────────────────────────────────
QUERY_RECIPE_DETAIL = """
MATCH (r:Recipe {recipe_id: $recipe_id})-[c:CONTAINS]->(i:Ingredient)
RETURN
  i.name           AS name,
  c.qty_g          AS qty_g,
  c.section_type   AS section_type,
  i.kcal           AS kcal_per100g,
  i.protein_g      AS protein_per100g,
  i.carb_g         AS carb_per100g,
  i.fat_g          AS fat_per100g,
  i.sodium_mg      AS sodium_per100g,
  i.price_per_100g AS price_per100g,
  i.allergy        AS allergens
ORDER BY c.section_type DESC
"""


# ─────────────────────────────────────────────
# 실행 함수
# ─────────────────────────────────────────────

def fetch_candidate_recipes(
    owned_ingredients: list[str],
    max_missing: int = 2,
    use_substitutes: bool = False
) -> list[dict]:
    """
    보유 재료 기반으로 만들 수 있는 후보 레시피 반환
    
    Args:
        owned_ingredients: 보유 재료 이름 리스트
        max_missing: 허용할 미보유 필수 재료 최대 개수
        use_substitutes: 대체재로 해결 가능한 레시피도 포함할지 여부
    
    Returns:
        후보 레시피 dict 리스트
    """
    query = QUERY_CANDIDATE_WITH_SUBSTITUTES if use_substitutes else QUERY_CANDIDATE_RECIPES

    driver = get_driver()
    with driver.session() as session:
        result = session.run(
            query,
            owned=owned_ingredients,
            max_missing=max_missing
        )
        records = [dict(r) for r in result]
    driver.close()
    return records


def fetch_recipe_detail(recipe_id: str) -> list[dict]:
    """특정 레시피의 재료 상세 정보 반환 (LP 입력용)"""
    driver = get_driver()
    with driver.session() as session:
        result = session.run(QUERY_RECIPE_DETAIL, recipe_id=recipe_id)
        records = [dict(r) for r in result]
    driver.close()
    return records