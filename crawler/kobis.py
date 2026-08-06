# -*- coding: utf-8 -*-
"""KOBIS(영화진흥위원회) 오픈API 보조 조회.

재개봉작의 '원래 개봉일'과 제작연도를 찾는 용도로만 쓴다.
KOBIS_API_KEY 가 없으면 조용히 건너뛴다 — 사이트는 원개봉일 없이도 동작한다.
"""
from __future__ import annotations

import os
import re
from datetime import date, timedelta

import requests

API_URL = "http://kobis.or.kr/kobisopenapi/webservice/rest/movie/searchMovieList.json"

# 재개봉일보다 최소 이만큼 이전에 개봉한 항목만 '원작'으로 인정 (장기상영과 구분)
MIN_GAP = timedelta(days=180)


def find_original(title: str, rerelease_iso: str | None) -> dict | None:
    """제목이 일치하고 재개봉일보다 충분히 이전에 개봉한 KOBIS 항목을 찾는다.

    동명 영화가 여럿이면 재개봉일 직전에 개봉한 것을 고른다.
    """
    key = os.getenv("KOBIS_API_KEY")
    if not key:
        return None
    try:
        res = requests.get(API_URL, params={"key": key, "movieNm": title}, timeout=10)
        res.raise_for_status()
        items = (res.json().get("movieListResult") or {}).get("movieList") or []
    except Exception:
        return None

    target = _norm_title(title)
    rerelease = _to_date(rerelease_iso) or date.today()

    best: tuple[date, dict] | None = None
    for item in items:
        if _norm_title(item.get("movieNm")) != target:
            continue
        open_raw = item.get("openDt") or ""
        if not re.fullmatch(r"\d{8}", open_raw):
            continue
        open_date = date(int(open_raw[:4]), int(open_raw[4:6]), int(open_raw[6:8]))
        if open_date > rerelease - MIN_GAP:
            continue
        if best is None or open_date > best[0]:
            best = (open_date, item)

    if best is None:
        return None
    open_date, item = best
    return {
        "kobis_code": item.get("movieCd"),
        "original_open_date": open_date.isoformat(),
        "prdt_year": item.get("prdtYear") or None,
    }


def _norm_title(name: str | None) -> str:
    return re.sub(r"[\s:·,\-–!?'\"“”‘’]+", "", (name or "")).lower()


def _to_date(iso: str | None) -> date | None:
    if not iso:
        return None
    parts = [int(p) for p in iso.split("-") if p.isdigit()]
    while len(parts) < 3:
        parts.append(1)
    try:
        return date(parts[0], parts[1], parts[2])
    except ValueError:
        return None
