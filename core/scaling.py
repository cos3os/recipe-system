"""
RefrigerAI - 인분별 조리시간 스케일링 모듈
─────────────────────────────────────────
공식: t_step(s) = t_base × (s / s_base) ^ α_step
참고: RefrigerAI_기술총정리_v2.md 섹션 6
"""

import json
import os
from pathlib import Path

# ── α 매핑 테이블 ──────────────────────────────────────────
# action → α (조리 방식별 스케일링 계수)
ALPHA_MAP = {
    # 준비 단계 (재료량에 거의 비례)
    "썰다": 0.9,
    "다듬다": 0.9,
    "손질": 0.9,
    "갈다": 0.8,

    # 열처리 - 볶음/구이 (팬 표면적 제한)
    "볶다": 0.3,
    "굽다": 0.3,

    # 열처리 - 끓이기/조림 (열용량 영향)
    "끓이다": 0.5,
    "조리다": 0.5,
    "삶다": 0.5,
    "데치다": 0.4,

    # 찌기 (공간 여유, 끓이기와 유사)
    "찌다": 0.5,

    # 비열처리 (거의 고정)
    "섞다": 0.1,
    "간하기": 0.1,
    "마무리": 0.1,

    # 휴지 (인분 무관)
    "재우다": 0.0,
}

DEFAULT_ALPHA = 0.5


def get_alpha(action: str) -> float:
    """action 문자열에서 α 값 반환. 매핑에 없으면 기본값 0.5"""
    return ALPHA_MAP.get(action, DEFAULT_ALPHA)


def scale_step_time(t_base: float, s_base: int, s_target: int, action: str) -> float:
    """단일 step의 조리시간 스케일링

    Args:
        t_base: 기준 인분에서의 조리 시간(분)
        s_base: 기준 인분 수
        s_target: 목표 인분 수
        action: 조리 동작 (ALPHA_MAP 키)

    Returns:
        목표 인분에서의 조리 시간(분), 소수점 1자리 반올림
    """
    if s_base == s_target:
        return t_base
    alpha = get_alpha(action)
    ratio = s_target / s_base
    scaled = t_base * (ratio ** alpha)
    return round(scaled, 1)


def scale_recipe(recipe_data: dict, target_servings: int) -> dict:
    """레시피 전체의 조리시간 스케일링

    Args:
        recipe_data: 구조화 추출 JSON (structured_steps/*.json)
        target_servings: 목표 인분 수

    Returns:
        스케일링 결과 dict:
        {
            "recipe_name": str,
            "base_servings": int,
            "target_servings": int,
            "base_total_min": float,
            "scaled_total_min": float,
            "change_pct": float,  # 변화율 (%)
            "steps": [
                {
                    "step_number": int,
                    "action": str,
                    "target": str,
                    "alpha": float,
                    "base_time_min": float,
                    "scaled_time_min": float,
                },
                ...
            ]
        }
    """
    s_base = recipe_data["base_servings"]
    steps_result = []
    base_total = 0
    scaled_total = 0

    for step in recipe_data["steps"]:
        t_base = step["estimated_time_min"]
        action = step["action"]
        t_scaled = scale_step_time(t_base, s_base, target_servings, action)
        alpha = get_alpha(action)

        base_total += t_base
        scaled_total += t_scaled

        steps_result.append({
            "step_number": step["step_number"],
            "action": action,
            "target": step["target"],
            "alpha": alpha,
            "base_time_min": t_base,
            "scaled_time_min": t_scaled,
        })

    change_pct = round((scaled_total - base_total) / base_total * 100, 1) if base_total > 0 else 0

    return {
        "recipe_name": recipe_data["recipe_name"],
        "base_servings": s_base,
        "target_servings": target_servings,
        "base_total_min": round(base_total, 1),
        "scaled_total_min": round(scaled_total, 1),
        "change_pct": change_pct,
        "steps": steps_result,
    }


def load_recipe(filepath: str) -> dict:
    """JSON 파일에서 레시피 데이터 로드"""
    with open(filepath, encoding="utf-8") as f:
        return json.load(f)


# ── 테스트 ─────────────────────────────────────────────────
if __name__ == "__main__":
    # structured_steps 폴더의 모든 JSON 테스트
    steps_dir = Path(__file__).parent.parent / "data" / "structured_steps"
    if not steps_dir.exists():
        steps_dir = Path(__file__).parent / "structured_steps"

    test_servings = [1, 2, 4, 6, 8]

    for json_file in sorted(steps_dir.glob("*.json")):
        recipe = load_recipe(str(json_file))
        print(f"\n{'='*60}")
        print(f"📍 {recipe['recipe_name']} (기준 {recipe['base_servings']}인분)")
        print(f"{'='*60}")

        # step별 상세 (1인분 예시)
        result = scale_recipe(recipe, 1)
        print(f"\n  {'step':>5} | {'action':8s} | {'α':>4} | {'기준':>5} | {'1인분':>5}")
        print(f"  {'─'*5}─┼─{'─'*8}─┼─{'─'*4}─┼─{'─'*5}─┼─{'─'*5}")
        for s in result["steps"]:
            print(f"  {s['step_number']:>5} | {s['action']:8s} | {s['alpha']:>4.1f} | {s['base_time_min']:>4.1f}분 | {s['scaled_time_min']:>4.1f}분")

        # 인분별 총 시간 요약
        print(f"\n  인분별 총 조리시간:")
        for srv in test_servings:
            r = scale_recipe(recipe, srv)
            bar = "█" * int(r["scaled_total_min"])
            print(f"    {srv}인분: {r['scaled_total_min']:>5.1f}분 ({r['change_pct']:>+5.1f}%) {bar}")