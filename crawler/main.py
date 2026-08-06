# -*- coding: utf-8 -*-
"""크롤 실행 진입점.

네이버 상영작/개봉예정 수집 → 재개봉작만 KOBIS로 원개봉일 보강 → docs/data/movies.json 생성.
KOBIS 키가 없거나 조회에 실패하면 이전 크롤 결과의 보강값을 승계한다.

사용법:
    python -m crawler.main
"""
from __future__ import annotations

import json
import os
import sys
import time
from dataclasses import asdict
from datetime import datetime, timedelta, timezone
from pathlib import Path

from . import kobis, naver

ROOT = Path(__file__).resolve().parent.parent
OUTPUT = ROOT / "docs" / "data" / "movies.json"
KST = timezone(timedelta(hours=9))


def _load_dotenv(path: Path) -> None:
    """python-dotenv 없이 .env 를 읽는다. 이미 설정된 환경변수가 우선."""
    if not path.exists():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip())


def _load_previous_enrichment(path: Path) -> dict[str, dict]:
    """이전 movies.json 에서 title → KOBIS 보강값 맵을 만든다."""
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}
    result: dict[str, dict] = {}
    for section in ("now_playing", "upcoming"):
        for m in data.get(section, []):
            if m.get("original_open_date"):
                result[m["title"]] = {
                    "kobis_code": m.get("kobis_code"),
                    "original_open_date": m["original_open_date"],
                    "prdt_year": m.get("prdt_year"),
                }
    return result


def _enrich(rereleases: list[naver.Movie]) -> None:
    previous = _load_previous_enrichment(OUTPUT)
    has_key = bool(os.getenv("KOBIS_API_KEY"))
    if not has_key:
        print("  KOBIS_API_KEY 미설정 — 신규 조회 없이 이전 결과만 승계합니다.")

    for movie in rereleases:
        if has_key:
            info = kobis.find_original(movie.title, movie.release_date)
            time.sleep(0.3)
            if info:
                movie.kobis_code = info["kobis_code"]
                movie.original_open_date = info["original_open_date"]
                movie.prdt_year = info["prdt_year"]
                print(f"    {movie.title}: 원개봉 {movie.original_open_date}")
                continue
        prev = previous.get(movie.title)
        if prev:
            movie.kobis_code = prev["kobis_code"]
            movie.original_open_date = prev["original_open_date"]
            movie.prdt_year = prev["prdt_year"]
            print(f"    {movie.title}: 이전 결과 승계 (원개봉 {movie.original_open_date})")
        elif has_key:
            print(f"    {movie.title}: KOBIS 매칭 실패")


def main() -> None:
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass
    _load_dotenv(ROOT / ".env")

    print("네이버에서 영화 목록 수집 중...")
    now_playing = naver.get_now_playing()
    print(f"  현재 상영작 {len(now_playing)}편")
    upcoming = naver.get_upcoming()
    print(f"  개봉 예정작 {len(upcoming)}편")

    rereleases = [m for m in now_playing + upcoming if m.is_rerelease]
    print(f"재개봉작 {len(rereleases)}편 감지 — 원개봉일 보강...")
    _enrich(rereleases)

    payload = {
        "generated_at": datetime.now(KST).isoformat(timespec="seconds"),
        "now_playing": [asdict(m) for m in now_playing],
        "upcoming": [asdict(m) for m in upcoming],
    }
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    now_re = sum(1 for m in now_playing if m.is_rerelease)
    up_re = sum(1 for m in upcoming if m.is_rerelease)
    print(f"완료: {OUTPUT.relative_to(ROOT)}")
    print(f"  상영 중 {len(now_playing)}편 (재개봉 {now_re}) / 개봉 예정 {len(upcoming)}편 (재개봉 {up_re})")


if __name__ == "__main__":
    main()
