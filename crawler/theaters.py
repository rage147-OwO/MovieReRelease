# -*- coding: utf-8 -*-
"""네이버 검색의 Place/영화 위젯에서 극장 위치와 상영작을 파싱.

세 가지 소스를 쓴다:
  - "{지역} 영화관" 검색 → PlaceListBusinessesItem 목록 (이름·주소·좌표)
    → 시딩 지역은 DEFAULT_REGION_QUERIES 참고, 서울 위주 + 광역시 주요 상권 일부
  - "{극장명} 영화시간표" 검색 → movieTimes(...) 배열 (당일 상영작 이름)
    → CGV는 잘 잡히지만 롯데시네마·메가박스 상당수 지점은 이 위젯 자체가 없다.
  - "영화 {제목} 상영일정" 검색 → movieCode 추출 → MovieAPIforScheduleListKB API
    → 영화 하나가 전국 어느 극장에서 상영 중인지 정확히 알려준다(체인 무관).
    지역 시딩 없이도 동작해 재개봉작처럼 소수 상영관에서만 트는 영화에 특히 유용.
    단, 극장 좌표는 안 준다 — 지역 시딩 극장(위 첫 번째 소스)과 이름이 겹치면
    좌표를 재사용하고, 안 겹치면 좌표 없이 이름만 등록한다.

전부 페이지에 <script>로 내장된 JSON을 정규식+괄호매칭으로 뽑아낸다.
공식 문서화된 API가 아니라 페이지 구조가 바뀌면 깨질 수 있다 — 항목이 0개면 조용히 건너뛴다.
"""
from __future__ import annotations

import json
import random
import re
import time
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone

import requests
from bs4 import BeautifulSoup

from .naver import HEADERS

SEARCH_URL = "https://search.naver.com/search.naver"
SCHEDULE_API_URL = "https://ts-proxy.naver.com/dcontent/nqapirender.nhn"
KST = timezone(timedelta(hours=9))
SCHEDULE_DAYS = 7  # 오늘 포함 며칠치 상영시간을 가져올지 — 네이버 UI도 보통 이만큼 보여준다

# 검색 시딩 지역 — 서울 주요 상권 + 예술영화관 밀집 지역 + 광역시 주요 상권.
# 새 지역을 늘리려면 "{지역명} 영화관" 형태로 추가하면 된다.
DEFAULT_REGION_QUERIES = [
    # 서울
    "강남역 영화관",
    "홍대 영화관",
    "종로 영화관",
    "잠실 영화관",
    "여의도 영화관",
    "왕십리 영화관",
    "신촌 영화관",
    "합정 영화관",
    "이수 영화관",
    "서울아트시네마 영화관",  # 예술영화관 밀집 검색 (서울아트시네마·필름포럼 등)
    # 그 외 광역시·수도권
    "수원역 영화관",
    "부천 영화관",
    "부산 서면 영화관",
    "대구 동성로 영화관",
    "인천 부평 영화관",
    "광주 충장로 영화관",
    "대전 둔산 영화관",
    "울산 삼산 영화관",
]

_MARK_TAGS = re.compile(r"</?mark>")


@dataclass
class Theater:
    id: str
    name: str
    address: str | None
    lat: str | None
    lon: str | None
    phone: str | None = None
    now_showing: list[str] = field(default_factory=list)


def build_theater_directory(region_queries: list[str] | None = None) -> list[Theater]:
    """지역 검색으로 극장을 모으고, 각 극장의 당일 상영작을 채운다."""
    theaters: dict[str, Theater] = {}
    for query in region_queries or DEFAULT_REGION_QUERIES:
        for t in search_theaters(query):
            theaters.setdefault(t.id, t)
        _throttle()

    for t in theaters.values():
        t.now_showing = get_now_showing(t.name)
        _throttle()

    return list(theaters.values())


def _throttle() -> None:
    time.sleep(random.uniform(2.0, 4.0))


def search_theaters(query: str) -> list[Theater]:
    text = _fetch(query)
    results: list[Theater] = []
    seen: set[str] = set()
    for m in re.finditer(r'"__typename":"PlaceListBusinessesItem"', text):
        obj_start = text.rfind("{", 0, m.start())
        try:
            obj = json.loads(_extract_balanced(text, obj_start))
        except (ValueError, json.JSONDecodeError):
            continue
        if obj.get("category") != "영화관":
            continue
        tid = obj.get("id")
        lat, lon = obj.get("y"), obj.get("x")
        if not tid or tid in seen or not lat or not lon:
            continue
        seen.add(tid)
        results.append(
            Theater(
                id=tid,
                name=_MARK_TAGS.sub("", obj.get("name") or ""),
                # fullAddress를 우선한다 — roadAddress는 시/도가 생략된 축약형이라
                # ("강남대로 438" 처럼) 프론트에서 지역(서울/경기 등) 판별이 안 된다.
                address=obj.get("fullAddress") or obj.get("roadAddress"),
                lat=obj.get("y"),
                lon=obj.get("x"),
                phone=obj.get("phone"),
            )
        )
    return results


def get_now_showing(theater_name: str) -> list[str]:
    text = _fetch(f"{theater_name} 영화시간표")
    key_match = re.search(r'"movieTimes\(\{[^}]*\}\)":\[', text)
    if not key_match:
        return []
    try:
        arr = json.loads(_extract_balanced(text, key_match.end() - 1))
    except (ValueError, json.JSONDecodeError):
        return []

    names: list[str] = []
    seen: set[str] = set()
    for item in arr:
        if item.get("__typename") != "MovieTime":
            continue
        name = item.get("name")
        if name and name not in seen:
            seen.add(name)
            names.append(name)
    return names


def get_schedule_theaters(title: str, days: int = SCHEDULE_DAYS) -> dict[str, dict]:
    """영화 제목으로 전국 상영관별 여러 날짜의 상영시간을 얻는다.

    "영화 {title} 상영일정" 검색 페이지에 내장된 movieCode(u2)를 먼저 뽑고,
    그 코드로 네이버 자체 스케줄 API(MovieAPIforScheduleListKB)를 날짜별로
    호출한다. 지역/체인에 상관없이 그 영화가 실제로 걸린 극장만 정확히 나온다.

    날짜(u3) 파라미터는 검색 페이지 방문으로 얻은 세션 쿠키 + Referer가
    같이 있어야 응답이 채워진다 — 없이 보내면(또는 district만 따로 보내면)
    조용히 빈 결과를 준다. 극장들이 "언제까지 상영"인지는 미리 공개하지
    않으므로(주간 성적에 따라 매주 재배정) SCHEDULE_DAYS 너머는 아예
    조회 대상이 아니다 — 네이버 UI도 동일하게 근시일 며칠만 보여준다.

    반환: {place_id: {"name": str, "schedule": {"YYYY-MM-DD": ["10:00", ...]}}}
    """
    session = requests.Session()
    session.headers.update(HEADERS)

    try:
        res = session.get(SEARCH_URL, params={"query": f"영화 {title} 상영일정"}, timeout=15)
        res.raise_for_status()
    except requests.RequestException:
        return {}

    code_match = re.search(r'"u9":\s*"[^"]*",\s*"u2":\s*"(\d+)"', res.text)
    if not code_match:
        return {}
    movie_code = code_match.group(1)
    referer = res.url

    theaters_out: dict[str, dict] = {}
    today = datetime.now(KST).date()
    for offset in range(days):
        date_str = (today + timedelta(days=offset)).isoformat()
        try:
            res = session.get(
                SCHEDULE_API_URL,
                params={
                    "where": "nexearch",
                    "pkid": "68",
                    "key": "MovieAPIforScheduleListKB",
                    "u2": movie_code,
                    "u9": f"영화 {title}",
                    "u3": date_str,
                },
                headers={"Referer": referer},
                timeout=15,
            )
            res.raise_for_status()
            data = res.json()
        except (requests.RequestException, ValueError):
            time.sleep(random.uniform(1.0, 2.0))
            continue

        for item in data.get("items", []):
            soup = BeautifulSoup(item.get("html", ""), "html.parser")
            for wrapper in soup.select("li._scrolling_wrapper"):
                a = wrapper.select_one("a.this_link_place")
                if not a:
                    continue
                place_match = re.search(r"place/(\d+)", a.get("href") or "")
                if not place_match:
                    continue
                pid = place_match.group(1)
                times = [t.get_text(strip=True) for t in wrapper.select("span.this_point_big")]
                if not times:
                    continue
                entry = theaters_out.setdefault(pid, {"name": a.get_text(strip=True), "schedule": {}})
                entry["schedule"][date_str] = times
        time.sleep(random.uniform(1.0, 2.0))

    return theaters_out


def _fetch(query: str, retries: int = 2) -> str:
    for attempt in range(retries + 1):
        res = requests.get(SEARCH_URL, params={"query": query}, headers=HEADERS, timeout=15)
        if res.status_code == 200:
            return res.text
        if attempt < retries:
            time.sleep(random.uniform(3.0, 6.0))
    res.raise_for_status()
    return res.text  # pragma: no cover


def _extract_balanced(text: str, start: int) -> str:
    """text[start]는 '{' 또는 '['. 문자열 이스케이프를 고려해 짝이 맞는 지점까지 잘라낸다."""
    open_ch = text[start]
    close_ch = "}" if open_ch == "{" else "]"
    depth = 0
    in_str = False
    esc = False
    for i in range(start, len(text)):
        c = text[i]
        if in_str:
            if esc:
                esc = False
            elif c == "\\":
                esc = True
            elif c == '"':
                in_str = False
            continue
        if c == '"':
            in_str = True
        elif c == open_ch:
            depth += 1
        elif c == close_ch:
            depth -= 1
            if depth == 0:
                return text[start : i + 1]
    raise ValueError("no matching bracket found")
