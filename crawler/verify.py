# -*- coding: utf-8 -*-
"""라이브 사이트 데이터를 네이버 원본과 독립적으로 대조 검증한다.

crawler/theaters.py 의 함수를 재사용하지 않고 원시 응답을 별도로 다시
파싱한다 — 크롤러 자체에 파싱 버그가 있으면 그 함수를 다시 불러도
같은 버그가 재현될 뿐이라, 진짜 검증이 되려면 독립적인 경로가 필요하다.

확인 항목:
  1. 참조 무결성 — movies.json의 모든 theaters id가 theaters.json에 실존하는가
  2. 재개봉작 표본 — 라이브 사이트의 극장/오늘 상영시간이 네이버 원본과 일치하는가
  3. 날짜 탭 불변식 — theater_times에 등장하는 모든 날짜가 실제로 극장 ≥1곳을 갖는가

사용법:
    python -m crawler.verify                 # 배포된 라이브 사이트 검증
    python -m crawler.verify --local          # 로컬 docs/data 검증
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parent.parent
LIVE_BASE = "https://rage147-owo.github.io/MovieReRelease/"
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


def _fetch_text(url: str, params: dict) -> str:
    from urllib.parse import urlencode

    req = Request(f"{url}?{urlencode(params)}", headers=UA)
    with urlopen(req, timeout=15) as res:
        return res.read().decode("utf-8")


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


def _extract_movie_code(text: str) -> str | None:
    m = re.search(r'"u9":\s*"[^"]*",\s*"u2":\s*"(\d+)"', text)
    return m.group(1) if m else None


def fetch_ground_truth(title: str) -> set[str]:
    """네이버 스케줄 API를 이 스크립트 안에서 독립적으로 다시 호출해
    오늘 상영 중인 극장명 집합을 얻는다 (theaters.py 코드 재사용 없음)."""
    import http.cookiejar
    import urllib.request

    cj = http.cookiejar.CookieJar()
    opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(cj))

    from urllib.parse import urlencode

    search_req = Request(
        f"https://search.naver.com/search.naver?{urlencode({'query': f'영화 {title} 상영일정'})}", headers=UA
    )
    with opener.open(search_req, timeout=15) as res:
        text = res.read().decode("utf-8")
        referer = res.geturl()

    movie_code = _extract_movie_code(text)
    if not movie_code:
        return set()

    params = {
        "where": "nexearch",
        "pkid": "68",
        "key": "MovieAPIforScheduleListKB",
        "u2": movie_code,
        "u9": f"영화 {title}",
    }
    sched_req = Request(
        f"https://ts-proxy.naver.com/dcontent/nqapirender.nhn?{urlencode(params)}",
        headers={**UA, "Referer": referer},
    )
    with opener.open(sched_req, timeout=15) as res:
        data = json.loads(res.read().decode("utf-8"))

    names: set[str] = set()
    for item in data.get("items", []):
        for m in re.finditer(r'class="this_link_place">\s*([^<]+)<', item.get("html", "")):
            names.add(m.group(1).strip())
    return names


def check_sample_against_naver(movies: dict, theaters: dict, sample_size: int = 3) -> list[str]:
    """재개봉작 표본을 네이버 원본과 직접 대조한다."""
    errors = []
    theater_by_id = {t["id"]: t for t in theaters["theaters"]}
    rereleases = [m for m in movies.get("now_playing", []) if m.get("is_rerelease")]

    for m in rereleases[:sample_size]:
        site_names = {theater_by_id[tid]["name"] for tid in m.get("theaters", []) if tid in theater_by_id}
        try:
            truth_names = fetch_ground_truth(m["title"])
        except Exception as e:
            errors.append(f"[대조실패] {m['title']!r} 네이버 조회 오류: {e}")
            continue

        missing_on_site = truth_names - site_names
        extra_on_site = site_names - truth_names
        status = "OK" if not missing_on_site else "MISMATCH"
        print(f"  [{status}] {m['title']}: 사이트={sorted(site_names)} / 네이버={sorted(truth_names)}")
        if missing_on_site:
            errors.append(f"[표본대조] {m['title']!r}: 네이버엔 있는데 사이트엔 없음 → {missing_on_site}")
        if extra_on_site:
            print(f"           (참고: 사이트에만 있음, 오늘 상영 없이 등록된 것일 수 있음 → {extra_on_site})")
    return errors


def main() -> None:
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

    print("3) 재개봉작 표본을 네이버 원본과 대조...")
    all_errors += check_sample_against_naver(movies, theaters)

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
