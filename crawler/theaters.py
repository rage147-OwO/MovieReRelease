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

import requests
from bs4 import BeautifulSoup

from .naver import HEADERS

SEARCH_URL = "https://search.naver.com/search.naver"
SCHEDULE_API_URL = "https://ts-proxy.naver.com/dcontent/nqapirender.nhn"

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


def get_schedule_theaters(title: str) -> list[tuple[str, str, list[str]]]:
    """영화 제목으로 전국 상영관 (place_id, 극장명, 오늘 상영시간 목록)을 얻는다.

    "영화 {title} 상영일정" 검색 페이지에 내장된 movieCode(u2)를 먼저 뽑고,
    그 코드로 네이버 자체 스케줄 API(MovieAPIforScheduleListKB)를 호출한다.
    지역/체인에 상관없이 그 영화가 실제로 걸린 극장만 정확히 나온다.

    시간은 오늘 것만 준다 — 날짜 파라미터(u3) 없이 호출하면 오늘 데이터만
    오고, 극장들도 "언제까지 상영"인지는 미리 공개하지 않아(주간 성적에
    따라 매주 다시 정해짐) 애초에 얻을 수 있는 정보가 아니다.
    """
    text = _fetch(f"영화 {title} 상영일정")
    code_match = re.search(r'"u9":\s*"[^"]*",\s*"u2":\s*"(\d+)"', text)
    if not code_match:
        return []
    movie_code = code_match.group(1)

    try:
        res = requests.get(
            SCHEDULE_API_URL,
            params={
                "where": "nexearch",
                "pkid": "68",
                "key": "MovieAPIforScheduleListKB",
                "u2": movie_code,
                "u9": f"영화 {title}",
            },
            headers=HEADERS,
            timeout=15,
        )
        res.raise_for_status()
        data = res.json()
    except (requests.RequestException, ValueError):
        return []

    results: list[tuple[str, str, list[str]]] = []
    seen: set[str] = set()
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
            if pid in seen:
                continue
            seen.add(pid)
            times = [t.get_text(strip=True) for t in wrapper.select("span.this_point_big")]
            results.append((pid, a.get_text(strip=True), times))
    return results


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
