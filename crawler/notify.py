# -*- coding: utf-8 -*-
"""신규 재개봉작을 디스코드 웹훅으로 알린다.

DISCORD_WEBHOOK_URL 이 없으면 조용히 건너뛴다 — 필수 기능이 아니다.
"""
from __future__ import annotations

import os
import time

import requests

from . import naver

ACCENT_COLOR = 0xF6B23C  # 사이트 포인트 컬러(#f6b23c)
BATCH_SIZE = 10  # 디스코드 한 메시지당 embed 최대 개수


def notify_new_rereleases(movies: list[naver.Movie]) -> None:
    webhook_url = os.getenv("DISCORD_WEBHOOK_URL")
    if not webhook_url:
        print("  DISCORD_WEBHOOK_URL 미설정 — 알림을 건너뜁니다.")
        return
    if not movies:
        return

    for i in range(0, len(movies), BATCH_SIZE):
        batch = movies[i : i + BATCH_SIZE]
        payload = {
            "content": f"🎬 새로운 재개봉작 {len(movies)}편을 찾았어요!" if i == 0 else None,
            "embeds": [_build_embed(m) for m in batch],
        }
        try:
            res = requests.post(webhook_url, json=payload, timeout=10)
            res.raise_for_status()
            print(f"  Discord 알림 전송: {', '.join(m.title for m in batch)}")
        except requests.RequestException as e:
            print(f"  Discord 알림 실패: {e}")
        time.sleep(1)


def _build_embed(m: naver.Movie) -> dict:
    status = "상영 중" if not m.dday else f"개봉 {m.dday}"
    fields = [{"name": "재개봉일", "value": (m.release_raw or "미정").rstrip("."), "inline": True}]

    if m.original_open_date:
        gap = _year_gap(m.original_open_date, m.release_date)
        value = m.original_open_date + (f" · {gap}년 만" if gap >= 1 else "")
        fields.append({"name": "원개봉", "value": value, "inline": True})

    if m.theaters:
        fields.append({"name": "상영관", "value": f"{len(m.theaters)}곳에서 확인됨", "inline": True})

    embed = {
        "title": m.title,
        "url": m.naver_link,
        "description": " · ".join(filter(None, [m.genre, m.runtime, status])),
        "color": ACCENT_COLOR,
        "fields": fields,
    }
    if m.poster:
        embed["thumbnail"] = {"url": m.poster}
    return embed


def _year_gap(orig_iso: str, re_iso: str | None) -> int:
    if not orig_iso or not re_iso:
        return 0
    try:
        return int(re_iso[:4]) - int(orig_iso[:4])
    except ValueError:
        return 0
