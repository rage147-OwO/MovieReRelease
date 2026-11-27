# -*- coding: utf-8 -*-
"""네이버에서 극장 위치, 극장별 당일 상영작, 영화별 전국 회차를 수집한다."""
from __future__ import annotations

import json
import random
import re
import time
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta, timezone

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from .naver import HEADERS

SEARCH_URL = "https://search.naver.com/search.naver"
SCHEDULE_API_URL = "https://api-gw.entertain.naver.com/csearch/contents/movie/{movie_id}/screening"
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

# 네이버 place 데이터가 광주광역시를 "전남광주"(+"통합특별시"가 붙기도 함)라는
# 존재하지 않는 행정구역명으로 준다(경기도 광주시와 구분하려는 내부 표기로
# 추정) — 실제 공식 명칭으로 정규화한다. 엔드포인트마다 접미사 유무가 달라
# ("전남광주통합특별시 ..." 도, "전남광주 서구 ..." 도 나온다) 둘 다 잡는다.
_ADDRESS_FIXUPS = [
    (re.compile(r"^전남광주(?:통합특별시)?"), "광주광역시"),
]


def _normalize_address(address: str | None) -> str | None:
    if not address:
        return address
    for pattern, replacement in _ADDRESS_FIXUPS:
        address = pattern.sub(replacement, address)
    return address


@dataclass
class Theater:
    id: str
    name: str
    address: str | None
    lat: str | None
    lon: str | None
    phone: str | None = None
    now_showing: list[str] = field(default_factory=list)
    region: str | None = None


def build_theater_directory(region_queries: list[str] | None = None) -> list[Theater]:
    """지역 검색으로 극장을 모으고, 각 극장의 당일 상영작을 채운다."""
    theaters: dict[str, Theater] = {}
    for query in region_queries or DEFAULT_REGION_QUERIES:
        try:
            for t in search_theaters(query):
                theaters.setdefault(t.id, t)
        except requests.RequestException as exc:
            print(f"  {query}: 극장 검색 실패 ({exc})")
        _throttle()

    for t in theaters.values():
        try:
            t.now_showing = get_now_showing(t.name, t.id)
        except requests.RequestException as exc:
            print(f"  {t.name}: 극장별 상영작 조회 실패 ({exc})")
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
                address=_normalize_address(obj.get("fullAddress") or obj.get("roadAddress")),
                lat=obj.get("y"),
                lon=obj.get("x"),
                phone=obj.get("phone"),
            )
        )
    return results


def search_theater_detail(name: str) -> Theater | None:
    """극장 이름 단독 검색으로 주소·좌표를 얻는다 (지역 시딩·스케줄 API 둘 다에서
    빠진 극장 보강용).

    "{이름} 영화관"으로 검색하면 PlaceListBusinessesItem 목록 위젯이 아니라
    단일 상세 페이지로 바로 넘어가는 경우가 많다(체인 지점명처럼 검색어가
    고유할 때) — search_theaters()는 목록 위젯만 파싱하므로 이런 경우 0건을
    준다. 상세 페이지엔 PlaceDetailBase(+ 중첩된 Coordinate)가 내장돼
    있어 그걸 대신 파싱한다. "영화관" 접미사 없이도 한 번 더 시도한다
    (드물게 접미사가 오히려 다른 업체로 갈라지는 경우가 있다).
    """
    for i, query in enumerate((f"{name} 영화관", name)):
        if i > 0:
            time.sleep(random.uniform(1.0, 2.0))  # 같은 극장에 연속 요청이라 짧게라도 텀을 둔다
        text = _fetch(query)
        m = re.search(r'"__typename":"PlaceDetailBase"', text)
        if not m:
            continue
        obj_start = text.rfind("{", 0, m.start())
        try:
            obj = json.loads(_extract_balanced(text, obj_start))
        except (ValueError, json.JSONDecodeError):
            continue
        if obj.get("category") != "영화관":
            continue
        tid = obj.get("id")
        if not tid:
            continue
        coord = obj.get("coordinate") or {}
        lat, lon = coord.get("y"), coord.get("x")
        if not lat or not lon:
            continue
        return Theater(
            id=tid,
            name=_MARK_TAGS.sub("", obj.get("name") or name),
            address=_normalize_address(obj.get("roadAddress") or obj.get("address")),
            lat=lat,
            lon=lon,
            phone=obj.get("phone"),
        )
    return None


def get_now_showing(theater_name: str, theater_id: str) -> list[str]:
    return _parse_now_showing(_fetch(f"{theater_name} 영화시간표"), theater_id)


def _parse_now_showing(text: str, theater_id: str) -> list[str]:
    # PlaceDetail의 base 참조로 같은 극장의 movieTimes인지 확인한다.
    names = {}
    today = datetime.now(KST).date().isoformat()
    for hit in re.finditer(r'"__typename"\s*:\s*"PlaceDetail"', text):
        start = text.rfind("{", 0, hit.start())
        if start < 0:
            continue
        try:
            detail, _ = json.JSONDecoder().raw_decode(text, start)
        except ValueError:
            continue
        if (detail.get("base") or {}).get("__ref") != f"PlaceDetailBase:{theater_id}":
            continue
        for field_name, items in detail.items():
            if field_name != "movieTimes" and not field_name.startswith("movieTimes("):
                continue
            for item in items or []:
                if item.get("__typename") == "MovieTime" and item.get("date") == today and item.get("name"):
                    names[item["name"]] = None
    return list(names)


class ScheduleError(Exception):
    """영화별 시간표를 확인할 수 없는 응답."""


@dataclass
class ScreeningTheater:
    name: str
    region: str | None
    schedule: dict[str, list[str]] = field(default_factory=dict)


def schedule_session() -> requests.Session:
    session = requests.Session()
    session.headers.update({**HEADERS, "Accept": "application/json"})
    session.mount("https://", HTTPAdapter(max_retries=Retry(
        total=2,
        backoff_factor=1,
        status_forcelist=(429, 500, 502, 503, 504),
        respect_retry_after_header=False,
    )))
    return session


def _fetch_screening(session: requests.Session, movie_id: str, day: str | None = None) -> dict | None:
    try:
        response = session.get(
            SCHEDULE_API_URL.format(movie_id=movie_id),
            params={"date": day} if day else None,
            timeout=15,
        )
        response.raise_for_status()
        data = response.json()
    except (requests.RequestException, ValueError) as exc:
        raise ScheduleError(str(exc)) from exc
    if not isinstance(data, dict) or data.get("success") is not True:
        raise ScheduleError("네이버 API 응답 오류")
    result = data.get("result")
    if result is None:
        return None
    if (
        not isinstance(result, dict)
        or not isinstance(result.get("metadata"), dict)
        or str(result["metadata"].get("dssId")) != movie_id
        or not isinstance(result.get("dateAxis"), list)
        or not isinstance(result.get("theaters"), list)
        or not isinstance(result.get("selectedDate"), str)
    ):
        raise ScheduleError("시간표 응답 형식 또는 영화 ID 불일치")
    if day and result["selectedDate"] != day:
        raise ScheduleError(f"요청 날짜와 응답 날짜 불일치 ({result['selectedDate']})")
    return result


# 네이버는 심야 회차를 24:xx 이상의 시각으로도 제공한다.
_SHOWTIME = re.compile(r"(?:[0-2][0-9]|3[0-5]):[0-5][0-9]")


def _add_screening_day(
    result: dict, day: str, schedule: dict[str, ScreeningTheater]
) -> None:
    for theater in result["theaters"]:
        place_id = str(theater.get("placeId") or "")
        name = theater.get("theaterName")
        if not place_id.isdecimal() or not isinstance(name, str) or not name.strip():
            continue
        times = {
            slot["startTime"]
            for slot in theater.get("runnings") or []
            if isinstance(slot.get("startTime"), str) and _SHOWTIME.fullmatch(slot["startTime"])
        }
        if times:
            entry = schedule.setdefault(place_id, ScreeningTheater(name.strip(), theater.get("regionDepth1")))
            entry.schedule[day] = sorted(times.union(entry.schedule.get(day, [])))


def get_schedule_theaters(
    movie_id: str, session: requests.Session, *, today: date, days: int = SCHEDULE_DAYS
) -> dict[str, ScreeningTheater]:
    """동일 영화의 공개된 날짜만 조회하고 네이버가 회신한 날짜의 회차를 저장한다."""
    initial = _fetch_screening(session, movie_id)
    if initial is None:
        return {}

    window = {(today + timedelta(days=offset)).isoformat() for offset in range(days)}
    published = {
        day.get("date")
        for day in initial["dateAxis"]
        if isinstance(day, dict) and isinstance(day.get("date"), str) and day.get("disabled") is False
    }
    schedule: dict[str, ScreeningTheater] = {}
    failures = []
    for day in sorted(window & published):
        if day == initial["selectedDate"]:
            result = initial
        else:
            time.sleep(random.uniform(1.0, 2.0))
            try:
                result = _fetch_screening(session, movie_id, day)
                if result is None:
                    raise ScheduleError("공개 날짜의 시간표 응답 누락")
            except ScheduleError as exc:
                failures.append(f"{day}: {exc}")
                continue
        _add_screening_day(result, day, schedule)
    if failures:
        message = "; ".join(failures)
        if not schedule:
            raise ScheduleError(message)
        print(f"  영화 {movie_id}: 일부 날짜 조회 실패 ({message})")
    return schedule


def _fetch(query: str, retries: int = 2) -> str:
    for attempt in range(retries + 1):
        try:
            response = requests.get(SEARCH_URL, params={"query": query}, headers=HEADERS, timeout=15)
            response.raise_for_status()
            return response.text
        except requests.RequestException as exc:
            status = exc.response.status_code if exc.response is not None else None
            if attempt == retries or status is not None and status not in (429, 500, 502, 503, 504):
                raise
            time.sleep(random.uniform(3.0, 6.0))


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
