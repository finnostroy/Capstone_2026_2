# -*- coding: utf-8 -*-
"""
맛집 원픽 — 백엔드 API 서버 (backend/app.py)
================================================
역할: 프론트엔드(웹 화면)의 요청을 받아 추천 엔진을 실행하고
      결과를 JSON으로 돌려주는 HTTP 서버.

- 추천 엔진은 프로젝트 루트의 main.py 를 그대로 재사용한다 (공용 모듈).
- 표준 라이브러리만 사용 → 별도 설치 없이 실행 가능.
- 같은 서버가 frontend/index.html 도 서빙하므로 CORS 설정이 필요 없다.

실행:
    프로젝트 루트에서   python backend/app.py
    브라우저에서        http://localhost:8000

API 명세 (백엔드 담당이 프론트 담당에게 공유하는 문서에 해당):
    GET /api/restaurants
        → 200: {"restaurants": [ {name, menu, price, ...}, ... ]}
    GET /api/recommend?mood=스트레스&weather=비&budget=12000
        → 200: {"name", "menu", "price", "walk_minutes", "rating",
                 "score", "reasons": [...]}
        → 400: {"error": "..."}  (잘못된 파라미터)
"""

from __future__ import annotations

import json
import sys
from dataclasses import asdict
from http.server import HTTPServer, SimpleHTTPRequestHandler
from pathlib import Path
from urllib.parse import urlparse, parse_qs

# --- 프로젝트 루트를 import 경로에 추가해 main.py 의 엔진을 재사용 ---
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from main import Mood, Weather, RESTAURANTS, recommend  # noqa: E402

FRONTEND_DIR = ROOT / "frontend"
PORT = 8000


def json_bytes(payload: dict, status: int = 200) -> tuple[int, bytes]:
    return status, json.dumps(payload, ensure_ascii=False).encode("utf-8")


def handle_api(path: str, query: dict[str, list[str]]) -> tuple[int, bytes]:
    """API 라우팅 — 경로별로 어떤 응답을 줄지 결정한다."""
    if path == "/api/restaurants":
        return json_bytes({"restaurants": [asdict(r) for r in RESTAURANTS]})

    if path == "/api/recommend":
        # 1) 파라미터 검증 — 잘못된 입력은 400과 함께 이유를 알려준다
        try:
            mood = Mood[query.get("mood", ["보통"])[0]]
        except KeyError:
            return json_bytes({"error": f"mood는 {[m.name for m in Mood]} 중 하나여야 합니다."}, 400)
        try:
            weather = Weather[query.get("weather", ["맑음"])[0]]
        except KeyError:
            return json_bytes({"error": f"weather는 {[w.name for w in Weather]} 중 하나여야 합니다."}, 400)
        raw_budget = query.get("budget", ["10000"])[0]
        if not raw_budget.isdigit() or int(raw_budget) <= 0:
            return json_bytes({"error": "budget은 양의 정수(원)여야 합니다."}, 400)

        # 2) 엔진 실행 (CLI와 완전히 같은 함수를 호출한다)
        rec = recommend(mood, weather, budget=int(raw_budget))

        # 3) 프론트가 쓰기 좋은 평평한 JSON으로 변환
        body = asdict(rec.restaurant)
        body.update({"score": rec.score, "reasons": rec.reasons})
        return json_bytes(body)

    return json_bytes({"error": "존재하지 않는 API 경로입니다."}, 404)


class Handler(SimpleHTTPRequestHandler):
    """/api/* 는 직접 처리하고, 나머지는 frontend/ 폴더의 정적 파일로 서빙."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(FRONTEND_DIR), **kwargs)

    def do_GET(self):  # noqa: N802 (http.server 규약)
        parsed = urlparse(self.path)
        if parsed.path.startswith("/api/"):
            status, body = handle_api(parsed.path, parse_qs(parsed.query))
            self.send_response(status)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return
        if parsed.path == "/":
            self.path = "/index.html"
        super().do_GET()

    def log_message(self, fmt, *args):
        print(f"[요청] {self.address_string()} - {fmt % args}")


def main() -> None:
    if not (FRONTEND_DIR / "index.html").exists():
        print(f"경고: {FRONTEND_DIR/'index.html'} 이 없습니다. 프론트 화면 없이 API만 동작합니다.")
    server = HTTPServer(("0.0.0.0", PORT), Handler)
    print(f"맛집 원픽 서버 실행 중 → http://localhost:{PORT}  (종료: Ctrl+C)")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n서버를 종료합니다.")
        server.server_close()


if __name__ == "__main__":
    main()
