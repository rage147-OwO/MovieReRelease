# -*- coding: utf-8 -*-
"""네이버 통합검색 영화 목록 파싱.

기존 MovieParser/NaverParsing.py 가 쓰던 qapirender JSONP 엔드포인트를 그대로 사용한다.
카드의 개봉일 라벨(dt)이 '재개봉'으로 표기되는 것이 네이버의 재개봉 표시다.
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from urllib.parse import parse_qs, quote, urlparse

import requests
from bs4 import BeautifulSoup

API_URL = "https://m.search.naver.com/p/csearch/content/qapirender.nhn"
HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"
    )
}


@dataclass
class Movie:
    title: str
    poster: str | None = None
    genre: str | None = None
    runtime: str | None = None
    release_raw: str | None = None    # 네이버 표기 그대로: "2026.07.22." / "2026.08."
    release_date: str | None = None   # ISO 정규화: "2026-07-22" / "2026-08"
    is_rerelease: bool = False        # dt 라벨이 '재개봉'인 카드
    rating: str | None = None
    cast: str | None = None
    dday: str | None = None
    naver_os: str | None = None       # 네이버 영화 entity id
    naver_link: str | None = None
    # KOBIS 보강 (재개봉작만 채워짐)
    kobis_code: str | None = None
    original_open_date: str | None = None
    prdt_year: str | None = None
    # 지역 극장 보강 (theaters.py 크롤 결과와 교차매칭된 상영관 id 목록)
    theaters: list[str] = field(default_factory=list)
    # 극장 id → 오늘 상영시간 목록 (재개봉작 정밀 조회로만 채워짐, get_schedule_theaters)
    theater_times: dict[str, list[str]] = field(default_factory=dict)


def get_now_playing() -> list[Movie]:
    return _fetch_movies("현재상영영화", "s1.dsc")


def get_upcoming() -> list[Movie]:
    return _fetch_movies("개봉예정영화", "s2.dsc")


def _fetch_movies(query: str, sort: str) -> list[Movie]:
    data = _fetch_jsonp(query, sort)
    movies: list[Movie] = []
    seen: set[str] = set()
    for item in data.get("items", []):
        soup = BeautifulSoup(item.get("html", ""), "html.parser")
        for card in soup.select("div.card_item"):
            movie = _parse_card(card)
            if movie is None:
                continue
            key = movie.naver_os or f"{movie.title}|{movie.release_raw}"
            if key in seen:
                continue
            seen.add(key)
            movies.append(movie)
    return movies


def _fetch_jsonp(query: str, sort: str) -> dict:
    params = {
        "_callback": "cb",
        "key": "MovieAPIforPList",
        "pkid": "68",
        "where": "nexearch",
        "start": "0",
        "display": "1000",
        "so": sort,
        "q": query,
    }
    res = requests.get(API_URL, params=params, headers=HEADERS, timeout=15)
    res.raise_for_status()
    text = res.text.strip()
    payload = text[text.find("(") + 1 : text.rfind(")")]
    return json.loads(payload.replace("\\'", "'"))


def _parse_card(card) -> Movie | None:
    title_el = card.select_one("a.this_text")
    if title_el is None:
        return None
    movie = Movie(title=title_el.get_text(strip=True))

    query_params = parse_qs(urlparse(title_el.get("href") or "").query)
    movie.naver_os = (query_params.get("os") or [None])[0]
    naver_query = (query_params.get("query") or [None])[0]
    if movie.naver_os and naver_query:
        movie.naver_link = (
            "https://search.naver.com/search.naver"
            f"?where=nexearch&sm=tab_etc&pkid=68&os={movie.naver_os}&qvt=0"
            f"&query={quote(naver_query)}"
        )
    else:
        movie.naver_link = (
            f"https://search.naver.com/search.naver?query={quote(movie.title + ' 영화')}"
        )

    img = card.select_one("a.img_box img")
    if img is not None:
        movie.poster = img.get("src")

    for dl in card.select("dl.info_group"):
        for dt in dl.select("dt"):
            label = dt.get_text(strip=True)
            dd = dt.find_next_sibling("dd")
            if label == "개요":
                dds = dl.select("dd")
                if dds:
                    movie.genre = dds[0].get_text(strip=True)
                if len(dds) > 1:
                    movie.runtime = dds[1].get_text(strip=True)
            elif label in ("개봉", "재개봉"):
                if label == "재개봉":
                    movie.is_rerelease = True
                if dd is not None:
                    movie.release_raw = dd.get_text(strip=True)
                    movie.release_date = _normalize_date(movie.release_raw)
            elif label == "평점" and dd is not None:
                num = dd.select_one("span.num")
                if num is not None:
                    movie.rating = num.get_text(strip=True)
            elif label == "출연" and dd is not None:
                movie.cast = dd.get_text(" ", strip=True)

    dday = card.select_one("span.icon_dday")
    if dday is not None:
        movie.dday = dday.get_text(strip=True)
    return movie


def _normalize_date(raw: str | None) -> str | None:
    if not raw:
        return None
    numbers = re.findall(r"\d+", raw)
    if not numbers:
        return None
    if len(numbers) >= 3:
        return f"{numbers[0]}-{int(numbers[1]):02d}-{int(numbers[2]):02d}"
    if len(numbers) == 2:
        return f"{numbers[0]}-{int(numbers[1]):02d}"
    return numbers[0]
