# -*- coding: utf-8 -*-
"""신규 재개봉작 이력을 RSS 피드로 발행한다.

디스코드 웹훅은 사이트 운영자가 직접 만들어 GitHub Secret에 등록해야 하는
push 방식이라 번거롭다. RSS는 반대로 pull 방식 — 이 피드의 공개 URL 하나만
MonitoRSS 같은 디스코드 봇에 등록하면, 새 항목이 생길 때마다 봇이 알아서
가져가 알려준다. 시크릿도, 웹훅 설정도 필요 없다.

docs/data/rerelease_log.json 에 신규 재개봉 감지 이력을 append-only로 쌓고,
그중 최근 항목만 docs/feed.xml(RSS 2.0)로 렌더링한다.
"""
from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from xml.sax.saxutils import escape

from . import naver

KST = timezone(timedelta(hours=9))
MAX_LOG_ENTRIES = 200
MAX_FEED_ITEMS = 50

SITE_URL = "https://rage147-owo.github.io/MovieReRelease/"
FEED_URL = SITE_URL + "feed.xml"

_WEEKDAYS = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
_MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]


def update_log_and_feed(log_path: Path, feed_path: Path, new_rereleases: list[naver.Movie], now: datetime) -> None:
    """새로 감지된 재개봉작을 로그에 append하고, 로그 기준으로 feed.xml을 다시 만든다.
    new_rereleases 가 비어 있어도 lastBuildDate 갱신을 위해 feed는 매번 다시 쓴다."""
    log = _load_log(log_path)
    existing_ids = {e.get("naver_os") for e in log}

    for movie in new_rereleases:
        if not movie.naver_os or movie.naver_os in existing_ids:
            continue
        log.insert(
            0,
            {
                "naver_os": movie.naver_os,
                "title": movie.title,
                "detected_at": now.isoformat(timespec="seconds"),
                "link": movie.naver_link,
                "genre": movie.genre,
                "runtime": movie.runtime,
                "release_raw": movie.release_raw,
                "original_open_date": movie.original_open_date,
                "poster": movie.poster,
            },
        )
        existing_ids.add(movie.naver_os)

    log = log[:MAX_LOG_ENTRIES]
    log_path.parent.mkdir(parents=True, exist_ok=True)
    log_path.write_text(json.dumps(log, ensure_ascii=False, indent=2), encoding="utf-8")

    feed_path.write_text(_build_rss(log[:MAX_FEED_ITEMS], now), encoding="utf-8")


def _load_log(path: Path) -> list[dict]:
    if not path.exists():
        return []
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return []


def _build_rss(entries: list[dict], now: datetime) -> str:
    items = "\n".join(_build_item(e) for e in entries)
    return f"""<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0" xmlns:atom="http://www.w3.org/2005/Atom">
<channel>
<title>재개봉 알리미 — 새 재개봉작</title>
<link>{_esc(SITE_URL)}</link>
<description>지금 극장에서 다시 만날 수 있는 재개봉 영화를 매일 자동으로 찾아 알려드려요.</description>
<language>ko</language>
<atom:link href="{_esc_attr(FEED_URL)}" rel="self" type="application/rss+xml"/>
<lastBuildDate>{_rfc822(now)}</lastBuildDate>
{items}
</channel>
</rss>
"""


def _build_item(e: dict) -> str:
    desc_parts = [p for p in [e.get("genre"), e.get("runtime")] if p]
    if e.get("release_raw"):
        desc_parts.append(f"재개봉 {e['release_raw'].rstrip('.')}")
    if e.get("original_open_date"):
        desc_parts.append(f"원개봉 {e['original_open_date']}")
    description = " · ".join(desc_parts)

    detected_at = e.get("detected_at")
    pub_date = _rfc822(datetime.fromisoformat(detected_at)) if detected_at else ""
    link = e.get("link") or SITE_URL
    enclosure = f'<enclosure url="{_esc_attr(e["poster"])}" type="image/jpeg"/>' if e.get("poster") else ""

    return f"""<item>
<title>{_esc(e.get("title") or "")}</title>
<link>{_esc(link)}</link>
<guid isPermaLink="false">naver_os:{_esc(e.get("naver_os") or "")}</guid>
<pubDate>{pub_date}</pubDate>
<description>{_esc(description)}</description>
{enclosure}
</item>"""


def _rfc822(dt: datetime) -> str:
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=KST)
    return (
        f"{_WEEKDAYS[dt.weekday()]}, {dt.day:02d} {_MONTHS[dt.month - 1]} {dt.year} "
        f"{dt.hour:02d}:{dt.minute:02d}:{dt.second:02d} {dt.strftime('%z')}"
    )


def _esc(s: str) -> str:
    return escape(s)


def _esc_attr(s: str) -> str:
    return escape(s, {'"': "&quot;"})
