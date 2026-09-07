# -*- coding: utf-8 -*-
"""
맛집 원픽 (One-Pick) — 캡스톤디자인 예제 코드
================================================
문제 정의: 1인 가구 직장인이 점심 메뉴 결정에 매일 평균 10분이 걸리는
문제를 해결하기 위해, 기분·날씨·예산을 고려해 최적의 맛집 1곳만
추천하는 결정장애 해결 프로그램.

실행 방법:
    python main.py                          # 대화형 모드
    python main.py --mood 스트레스 --weather 비 --budget 12000
    python main.py --test                   # 자체 테스트 실행

표준 라이브러리만 사용 (별도 설치 불필요)
"""

from __future__ import annotations

import argparse
import json
import random
import sys
from dataclasses import dataclass, field, asdict
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Iterable

HISTORY_FILE = Path("history.json")   # 추천 이력 저장 파일 (.gitignore 대상 아님, 데모용)
RECENT_PENALTY_DAYS = 3               # 최근 N일 안에 추천한 곳은 감점


# ---------------------------------------------------------------------------
# 1. 도메인 모델
# ---------------------------------------------------------------------------

class Mood(Enum):
    """오늘의 기분 — 각 기분이 선호하는 음식 태그를 가진다."""
    스트레스 = ("매운", "자극적인")
    피곤함 = ("따뜻한", "든든한")
    상쾌함 = ("가벼운", "건강한")
    우울함 = ("달달한", "따뜻한")
    보통 = ()

    @property
    def preferred_tags(self) -> tuple[str, ...]:
        return self.value


class Weather(Enum):
    """오늘의 날씨 — 날씨별 선호 태그."""
    맑음 = ("가벼운", "면")
    비 = ("따뜻한", "국물")
    추움 = ("국물", "든든한")
    더움 = ("차가운", "면")

    @property
    def preferred_tags(self) -> tuple[str, ...]:
        return self.value


@dataclass(frozen=True)
class Restaurant:
    name: str
    menu: str
    price: int                      # 대표 메뉴 가격 (원)
    walk_minutes: int               # 도보 소요 시간 (분)
    tags: tuple[str, ...]           # 음식 성격 태그
    rating: float                   # 5점 만점 평점

    def __str__(self) -> str:
        return f"{self.name} — {self.menu} ({self.price:,}원, 도보 {self.walk_minutes}분, ★{self.rating})"


@dataclass
class Recommendation:
    restaurant: Restaurant
    score: float
    reasons: list[str] = field(default_factory=list)


# ---------------------------------------------------------------------------
# 2. 데이터 (실제 프로젝트에서는 DB 또는 API로 대체될 부분)
# ---------------------------------------------------------------------------

RESTAURANTS: list[Restaurant] = [
    Restaurant("불향각", "마라탕", 11000, 7, ("매운", "국물", "자극적인"), 4.3),
    Restaurant("혼밥식당", "제육덮밥", 9000, 3, ("든든한", "매운"), 4.1),
    Restaurant("초록샐러드", "닭가슴살 샐러드", 10500, 5, ("가벼운", "건강한", "차가운"), 4.0),
    Restaurant("면사무소", "냉모밀", 8500, 6, ("면", "차가운", "가벼운"), 4.2),
    Restaurant("국밥청", "돼지국밥", 9500, 8, ("국물", "따뜻한", "든든한"), 4.5),
    Restaurant("스윗브런치", "프렌치토스트", 12000, 10, ("달달한", "가벼운"), 4.4),
    Restaurant("교문앞분식", "라볶이", 7000, 2, ("매운", "자극적인", "면"), 3.9),
    Restaurant("온기우동", "튀김우동", 8000, 4, ("면", "국물", "따뜻한"), 4.2),
]


# ---------------------------------------------------------------------------
# 3. 추천 엔진 — 규칙 기반 점수화
# ---------------------------------------------------------------------------

def score_restaurant(
    r: Restaurant,
    mood: Mood,
    weather: Weather,
    budget: int,
    recent_names: Iterable[str] = (),
) -> Recommendation:
    """식당 하나에 대해 상황 적합도 점수를 계산한다.

    점수 구성 (가중치는 팀 회의로 조정하는 값):
      +2.0 * 기분 태그 일치 수
      +1.5 * 날씨 태그 일치 수
      +1.0 * 평점
      예산 초과 시 초과율에 비례해 감점, 예산의 70% 이하면 가성비 가점
      도보 10분 초과분은 분당 -0.3
      최근 추천된 곳은 -3.0 (같은 곳 반복 방지)
    """
    reasons: list[str] = []
    score = 0.0

    mood_hits = set(r.tags) & set(mood.preferred_tags)
    if mood_hits:
        score += 2.0 * len(mood_hits)
        reasons.append(f"기분({mood.name})에 맞는 {'/'.join(sorted(mood_hits))} 메뉴")

    weather_hits = set(r.tags) & set(weather.preferred_tags)
    if weather_hits:
        score += 1.5 * len(weather_hits)
        reasons.append(f"날씨({weather.name})에 어울리는 {'/'.join(sorted(weather_hits))} 메뉴")

    score += r.rating * 1.0

    if r.price > budget:
        over = (r.price - budget) / budget
        score -= 5.0 * over
        reasons.append(f"예산 {budget:,}원 초과(-)")
    elif r.price <= budget * 0.7:
        score += 0.8
        reasons.append("예산 대비 가성비(+)")

    if r.walk_minutes > 10:
        score -= 0.3 * (r.walk_minutes - 10)

    if r.name in set(recent_names):
        score -= 3.0
        reasons.append(f"최근 {RECENT_PENALTY_DAYS}일 내 방문(-)")

    return Recommendation(restaurant=r, score=round(score, 2), reasons=reasons)


def recommend(
    mood: Mood,
    weather: Weather,
    budget: int,
    restaurants: list[Restaurant] | None = None,
    recent_names: Iterable[str] = (),
) -> Recommendation:
    """모든 후보를 점수화해 1곳만 반환한다. 동점이면 무작위로 하나."""
    pool = restaurants if restaurants is not None else RESTAURANTS
    if not pool:
        raise ValueError("후보 식당 목록이 비어 있습니다.")

    scored = [score_restaurant(r, mood, weather, budget, recent_names) for r in pool]
    best = max(rec.score for rec in scored)
    top = [rec for rec in scored if rec.score == best]
    return random.choice(top)


# ---------------------------------------------------------------------------
# 4. 추천 이력 저장/조회 (JSON)
# ---------------------------------------------------------------------------

def load_recent_names(path: Path = HISTORY_FILE, days: int = RECENT_PENALTY_DAYS) -> list[str]:
    if not path.exists():
        return []
    try:
        records = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return []
    today = datetime.now()
    names = []
    for rec in records:
        try:
            when = datetime.fromisoformat(rec["date"])
        except (KeyError, ValueError):
            continue
        if (today - when).days < days:
            names.append(rec["name"])
    return names


def append_history(rec: Recommendation, path: Path = HISTORY_FILE) -> None:
    records = []
    if path.exists():
        try:
            records = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            records = []
    records.append(
        {
            "date": datetime.now().isoformat(timespec="seconds"),
            "name": rec.restaurant.name,
            "score": rec.score,
            "restaurant": asdict(rec.restaurant),
        }
    )
    path.write_text(json.dumps(records, ensure_ascii=False, indent=2), encoding="utf-8")


# ---------------------------------------------------------------------------
# 5. 입출력
# ---------------------------------------------------------------------------

def choose_from_enum(prompt: str, enum_cls: type[Enum]) -> Enum:
    """대화형 모드에서 Enum 항목을 번호로 고르게 한다."""
    members = list(enum_cls)
    print(prompt)
    for i, m in enumerate(members, start=1):
        print(f"  {i}. {m.name}")
    while True:
        raw = input("번호 선택 > ").strip()
        if raw.isdigit() and 1 <= int(raw) <= len(members):
            return members[int(raw) - 1]
        print(f"1~{len(members)} 사이의 번호를 입력하세요.")


def print_result(rec: Recommendation) -> None:
    print("\n" + "=" * 46)
    print("오늘의 원픽!")
    print("=" * 46)
    print(f"  {rec.restaurant}")
    print(f"  적합도 점수: {rec.score}")
    if rec.reasons:
        print("  추천 이유:")
        for reason in rec.reasons:
            print(f"   - {reason}")
    print("=" * 46)


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="맛집 원픽 — 기분·날씨·예산 기반 점심 추천")
    parser.add_argument("--mood", choices=[m.name for m in Mood], help="오늘의 기분")
    parser.add_argument("--weather", choices=[w.name for w in Weather], help="오늘의 날씨")
    parser.add_argument("--budget", type=int, help="예산(원)")
    parser.add_argument("--test", action="store_true", help="자체 테스트 실행")
    return parser.parse_args(argv)


# ---------------------------------------------------------------------------
# 6. 자체 테스트 (실제 프로젝트에서는 tests/ 폴더의 pytest로 확장)
# ---------------------------------------------------------------------------

def run_self_test() -> None:
    print("자체 테스트 실행 중...")

    # 1) 비 오는 날 + 피곤함 → 국물/따뜻한 계열이 상위여야 한다
    rec = recommend(Mood.피곤함, Weather.비, budget=10000, recent_names=[])
    assert set(rec.restaurant.tags) & {"국물", "따뜻한"}, "날씨/기분 태그 반영 실패"

    # 2) 예산이 매우 낮으면 비싼 집이 뽑히지 않아야 한다
    rec = recommend(Mood.보통, Weather.맑음, budget=7500)
    assert rec.restaurant.price <= 9000, f"예산 감점 미반영: {rec.restaurant}"

    # 3) 최근 방문 감점: 1위 후보를 최근 방문 처리하면 다른 곳이 나와야 한다
    first = recommend(Mood.스트레스, Weather.더움, budget=12000)
    second = recommend(Mood.스트레스, Weather.더움, budget=12000,
                       recent_names=[first.restaurant.name])
    assert first.restaurant.name != second.restaurant.name, "최근 방문 감점 미반영"

    # 4) 빈 목록은 명확한 오류를 내야 한다
    try:
        recommend(Mood.보통, Weather.맑음, budget=10000, restaurants=[])
    except ValueError:
        pass
    else:
        raise AssertionError("빈 목록 예외 처리 실패")

    print("테스트 4건 모두 통과 ✔")


# ---------------------------------------------------------------------------
# 7. 진입점
# ---------------------------------------------------------------------------

def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv if argv is not None else sys.argv[1:])

    if args.test:
        run_self_test()
        return 0

    print("맛집 원픽 — 점심 고민 10분을 10초로")

    mood = Mood[args.mood] if args.mood else choose_from_enum("오늘 기분은?", Mood)
    weather = Weather[args.weather] if args.weather else choose_from_enum("오늘 날씨는?", Weather)

    if args.budget:
        budget = args.budget
    else:
        raw = input("점심 예산(원, 기본 10000) > ").strip()
        budget = int(raw) if raw.isdigit() else 10000

    recent = load_recent_names()
    rec = recommend(mood, weather, budget, recent_names=recent)
    print_result(rec)
    append_history(rec)
    print(f"(추천 이력이 {HISTORY_FILE} 에 저장되었습니다)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
