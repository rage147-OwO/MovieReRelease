# -*- coding: utf-8 -*-
"""배포 또는 로컬 상영시간표를 네이버 원본과 대조한다.

    python -m crawler.verify
    python -m crawler.verify --local
"""
from __future__ import annotations

import json
import sys
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import urlencode
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parent.parent
LIVE_BASE = "https://rage147-owo.github.io/MovieReRelease/"
KST = timezone(timedelta(hours=9))
UA = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"
    )
}


def _fetch_json(url: str) -> dict:
    req = Request(url, headers=UA)
    with urlopen(req, timeout=15) as res:
        return json.loads(res.read().decode("utf-8"))


def load_site_data(local: bool) -> tuple[dict, dict]:
    if local:
        movies = json.loads((ROOT / "docs" / "data" / "movies.json").read_text(encoding="utf-8"))
        theaters = json.loads((ROOT / "docs" / "data" / "theaters.json").read_text(encoding="utf-8"))
    else:
        movies = _fetch_json(LIVE_BASE + "data/movies.json")
        theaters = _fetch_json(LIVE_BASE + "data/theaters.json")
    return movies, theaters


def check_referential_integrity(movies: dict, theaters: dict) -> list[str]:
    """movies.json이 참조하는 극장 id가 전부 theaters.json에 실존하는지."""
    errors = []
    theater_ids = {t["id"] for t in theaters["theaters"]}
    for section in ("now_playing", "upcoming"):
        for m in movies.get(section, []):
            missing = set(m.get("theaters", [])) - theater_ids
            if missing:
                errors.append(f"[참조무결성] {m['title']!r}이 존재하지 않는 극장 id 참조: {missing}")
    return errors


def check_date_tab_invariant(movies: dict) -> list[str]:
    """theater_times의 모든 날짜가 실제로 그 영화의 어떤 극장이든 매칭되는지
    (프론트가 날짜 탭을 만들 때 전제하는 불변식 — 어긋나면 빈 화면 버그로 이어진다)."""
    errors = []
    for section in ("now_playing", "upcoming"):
        for m in movies.get(section, []):
            tt = m.get("theater_times") or {}
            for tid, schedule in tt.items():
                if tid not in m.get("theaters", []):
                    errors.append(
                        f"[날짜탭불변식] {m['title']!r}: theater_times에 있는 극장 {tid}가 theaters 목록엔 없음"
                    )
                for date, times in schedule.items():
                    if not times:
                        errors.append(f"[날짜탭불변식] {m['title']!r}: {tid}의 {date} 시간 목록이 비어있음")
    return errors


def check_schedule_coverage(movies: dict, today: date) -> list[str]:
    today_iso = today.isoformat()
    count = sum(
        any(day >= today_iso and times for dates in movie.get("theater_times", {}).values()
            for day, times in dates.items())
        for movie in movies.get("now_playing", [])
    )
    print(f"  현재·미래 회차가 확인된 영화 {count}편")
    return [] if count else ["[상영시간] 현재·미래 회차가 전체 상영작에서 0건"]


def fetch_ground_truth(movie_id: str, day: str) -> set[tuple[str, str]]:
    """크롤러를 거치지 않고 네이버의 극장 ID와 회차를 읽는다."""
    url = f"https://api-gw.entertain.naver.com/csearch/contents/movie/{movie_id}/screening"
    data = _fetch_json(f"{url}?{urlencode({'date': day})}")
    if data.get("success") is not True:
        raise ValueError("네이버 시간표 API 응답 오류")
    result = data.get("result")
    if result is None:
        return set()
    if str(result["metadata"]["dssId"]) != movie_id:
        raise ValueError("응답의 영화 ID 불일치")
    if result["selectedDate"] != day:
        if any(info["date"] == day and info["disabled"] is False for info in result["dateAxis"]):
            raise ValueError("공개 상영일의 응답 날짜 불일치")
        return set()
    return {
        (str(theater["placeId"]), slot["startTime"])
        for theater in result["theaters"] if theater.get("placeId")
        for slot in theater.get("runnings", []) if slot.get("startTime")
    }


def check_sample_against_naver(movies: dict, today: date, sample_size: int = 2) -> list[str]:
    """일반작과 재개봉작의 오늘·내일 회차를 극장 ID와 시각으로 비교한다."""
    errors = []
    checked = 0
    now_playing = [movie for movie in movies.get("now_playing", []) if movie.get("naver_os")]
    for rerelease in (True, False):
        samples = [movie for movie in now_playing if bool(movie.get("is_rerelease")) == rerelease][:sample_size]
        for movie in samples:
            for day in (today, today + timedelta(days=1)):
                day_str = day.isoformat()
                site = {
                    (theater_id, slot)
                    for theater_id, dates in movie.get("theater_times", {}).items()
                    for slot in dates.get(day_str, [])
                }
                try:
                    source = fetch_ground_truth(movie["naver_os"], day_str)
                except (OSError, ValueError, KeyError) as exc:
                    errors.append(f"[대조 실패] {movie['title']} {day_str}: {exc}")
                    continue
                checked += bool(source)
                missing, extra = source - site, site - source
                print(f"  {movie['title']} {day_str}: 사이트 {len(site)}건 / 네이버 {len(source)}건")
                if missing or extra:
                    errors.append(
                        f"[회차 차이] {movie['title']} {day_str}: "
                        f"네이버에만 {len(missing)}건, 사이트에만 {len(extra)}건"
                    )
    if not checked:
        errors.append("[표본 대조] 네이버에서 확인된 회차가 0건")
    return errors


def main() -> None:
    sys.stdout.reconfigure(encoding="utf-8")
    local = "--local" in sys.argv
    print(f"검증 대상: {'로컬 docs/data' if local else LIVE_BASE}")

    movies, theaters = load_site_data(local)
    print(f"movies: now_playing {len(movies['now_playing'])}편 / theaters: {len(theaters['theaters'])}곳")
    print()

    all_errors: list[str] = []

    print("1) 참조 무결성 확인...")
    all_errors += check_referential_integrity(movies, theaters)

    print("2) 날짜 탭 불변식 확인...")
    all_errors += check_date_tab_invariant(movies)

    today = datetime.now(KST).date()
    print("3) 전체 상영시간 확인...")
    all_errors += check_schedule_coverage(movies, today)

    print("4) 일반작과 재개봉작 표본을 네이버 원본과 대조...")
    all_errors += check_sample_against_naver(movies, today)

    print()
    if all_errors:
        print(f"❌ {len(all_errors)}건 발견:")
        for e in all_errors:
            print(" -", e)
        sys.exit(1)
    else:
        print("✅ 전부 통과")


if __name__ == "__main__":
    main()
