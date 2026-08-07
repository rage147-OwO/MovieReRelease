# -*- coding: utf-8 -*-
"""크롤 실행 진입점.

네이버 상영작/개봉예정 수집 → 재개봉작만 KOBIS로 원개봉일 보강 →
지역 극장 상영작과 교차매칭 → 신규 재개봉작 Discord 알림 →
docs/data/movies.json, theaters.json 생성.
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

from . import kobis, naver, notify, theaters

ROOT = Path(__file__).resolve().parent.parent
MOVIES_OUTPUT = ROOT / "docs" / "data" / "movies.json"
THEATERS_OUTPUT = ROOT / "docs" / "data" / "theaters.json"
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


def _match_theaters(now_playing: list[naver.Movie], theater_list: list[theaters.Theater]) -> int:
    """극장별 당일 상영작(now_showing)을 now_playing 영화 제목과 정규화 매칭해
    각 Movie.theaters 에 극장 id를 채운다. 매칭된 (영화, 극장) 쌍 개수를 반환."""
    by_title = {kobis._norm_title(m.title): m for m in now_playing}
    matches = 0
    for theater in theater_list:
        for shown_title in theater.now_showing:
            movie = by_title.get(kobis._norm_title(shown_title))
            if movie:
                movie.theaters.append(theater.id)
                matches += 1
    return matches


def _enrich_rerelease_theaters(
    rereleases: list[naver.Movie], theater_by_id: dict[str, theaters.Theater]
) -> tuple[int, int]:
    """재개봉작만 영화 중심 스케줄 API(get_schedule_theaters)로 전국 상영관을 보강한다.

    지역 시딩(_match_theaters)은 CGV 위주로만 잡히므로, 재개봉작처럼 상영관이
    적고 정확도가 중요한 영화에 한해 체인·지역 무관하게 정밀 조회한다.
    시딩에 없던 극장은 좌표 없이 이름만 등록(목록엔 나오되 지도 마커는 생략).
    반환값: (추가 매칭 건수, 새로 등록된 극장 수)
    """
    extra_matches = 0
    new_theaters = 0
    for movie in rereleases:
        for pid, name in theaters.get_schedule_theaters(movie.title):
            if pid not in theater_by_id:
                theater_by_id[pid] = theaters.Theater(id=pid, name=name, address=None, lat=None, lon=None)
                new_theaters += 1
            if pid not in movie.theaters:
                movie.theaters.append(pid)
                extra_matches += 1
        theaters._throttle()
    return extra_matches, new_theaters


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


def _load_previous_rerelease_ids(path: Path) -> set[str]:
    """이전 movies.json 에서 재개봉으로 표시됐던 영화의 naver_os 집합.
    새 movies.json 을 쓰기 전에 반드시 먼저 호출해야 한다."""
    if not path.exists():
        return set()
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return set()
    ids: set[str] = set()
    for section in ("now_playing", "upcoming"):
        for m in data.get(section, []):
            if m.get("is_rerelease") and m.get("naver_os"):
                ids.add(m["naver_os"])
    return ids


def _enrich(rereleases: list[naver.Movie]) -> None:
    previous = _load_previous_enrichment(MOVIES_OUTPUT)
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
    previous_rerelease_ids = _load_previous_rerelease_ids(MOVIES_OUTPUT)  # 덮어쓰기 전에 미리 읽어둔다

    print("네이버에서 영화 목록 수집 중...")
    now_playing = naver.get_now_playing()
    print(f"  현재 상영작 {len(now_playing)}편")
    upcoming = naver.get_upcoming()
    print(f"  개봉 예정작 {len(upcoming)}편")

    rereleases = [m for m in now_playing + upcoming if m.is_rerelease]
    print(f"재개봉작 {len(rereleases)}편 감지 — 원개봉일 보강...")
    _enrich(rereleases)

    print("지역 극장 상영정보 수집 중 (시간이 좀 걸립니다)...")
    theater_list = theaters.build_theater_directory()
    theater_by_id = {t.id: t for t in theater_list}
    matches = _match_theaters(now_playing, theater_list)
    with_showtime = sum(1 for t in theater_list if t.now_showing)
    print(f"  극장 {len(theater_list)}곳 (상영정보 확인됨 {with_showtime}곳) / 영화-극장 매칭 {matches}건")

    now_rereleases = [m for m in now_playing if m.is_rerelease]
    print(f"재개봉작 {len(now_rereleases)}편 — 전국 상영관 정밀 조회 중...")
    extra_matches, new_theater_count = _enrich_rerelease_theaters(now_rereleases, theater_by_id)
    print(f"  추가 매칭 {extra_matches}건 / 지역 시딩에 없던 극장 {new_theater_count}곳 신규 등록")
    theater_list = list(theater_by_id.values())

    new_rereleases = [m for m in rereleases if m.naver_os and m.naver_os not in previous_rerelease_ids]
    if new_rereleases:
        print(f"신규 재개봉작 {len(new_rereleases)}편 감지: {', '.join(m.title for m in new_rereleases)}")
        notify.notify_new_rereleases(new_rereleases)
    else:
        print("신규 재개봉작 없음")

    movies_payload = {
        "generated_at": datetime.now(KST).isoformat(timespec="seconds"),
        "now_playing": [asdict(m) for m in now_playing],
        "upcoming": [asdict(m) for m in upcoming],
    }
    MOVIES_OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    MOVIES_OUTPUT.write_text(json.dumps(movies_payload, ensure_ascii=False, indent=2), encoding="utf-8")

    theaters_payload = {
        "generated_at": datetime.now(KST).isoformat(timespec="seconds"),
        # 좌표 없는 극장도 포함한다 — 지도 마커는 못 찍어도 "이 극장에서 상영 중"이라는
        # 사실 자체는 유효한 정보라 목록에는 표시한다 (프론트에서 lat/lon null 처리).
        "theaters": [
            {
                "id": t.id,
                "name": t.name,
                "address": t.address,
                "lat": t.lat,
                "lon": t.lon,
                "phone": t.phone,
            }
            for t in theater_list
        ],
    }
    THEATERS_OUTPUT.write_text(json.dumps(theaters_payload, ensure_ascii=False, indent=2), encoding="utf-8")

    now_re = sum(1 for m in now_playing if m.is_rerelease)
    up_re = sum(1 for m in upcoming if m.is_rerelease)
    print(f"완료: {MOVIES_OUTPUT.relative_to(ROOT)}, {THEATERS_OUTPUT.relative_to(ROOT)}")
    print(f"  상영 중 {len(now_playing)}편 (재개봉 {now_re}) / 개봉 예정 {len(upcoming)}편 (재개봉 {up_re})")


if __name__ == "__main__":
    main()
