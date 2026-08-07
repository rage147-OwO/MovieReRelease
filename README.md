# 🎬 재개봉 알리미 (MovieReRelease)

지금 극장에서 다시 만날 수 있는 **재개봉 영화**를 매일 자동으로 수집해 보여주는 정적 웹사이트.

## 동작 방식

```
GitHub Actions (매일 06:00 KST)
  └─ crawler/ 실행
       ├─ 네이버 통합검색 JSONP → 현재 상영작 / 개봉 예정작 수집
       │    └─ 카드의 개봉일 라벨이 '재개봉'이면 재개봉작으로 판정
       ├─ KOBIS 오픈API → 재개봉작의 원개봉일·제작연도 보강
       ├─ 네이버 Place 위젯 → 지역별 극장 위치 + 극장별 당일 상영작 수집
       │    └─ now_playing 제목과 정규화 매칭해 영화별 상영관 id 연결
       ├─ 재개봉작만 네이버 스케줄 API로 전국 상영관 정밀 재조회
       │    └─ 지역 시딩이 못 잡는 롯데시네마·메가박스·지방 극장까지 보강
       ├─ 어제 없던 재개봉작이면 Discord 웹훅으로 알림
       └─ docs/data/movies.json, theaters.json 갱신 → 커밋/푸시
GitHub Pages (docs/) → 정적 사이트 서빙
       └─ 영화 카드 클릭 → 상영관 목록 + Leaflet(OSM) 지도 모달
```

## 구조

```
crawler/
  naver.py     네이버 영화 목록 파싱 (JSONP + BeautifulSoup)
  kobis.py     KOBIS 원개봉일 조회 (재개봉작 보강용)
  theaters.py  네이버 Place 위젯·스케줄 API에서 극장 위치·상영작 파싱
  notify.py    신규 재개봉작 Discord 웹훅 알림
  main.py      실행 진입점 → docs/data/movies.json, theaters.json 생성
docs/          GitHub Pages 루트 (index.html + app.js + data/*.json)
.github/workflows/crawl.yml   매일 자동 크롤 워크플로
```

극장 시딩 지역은 `crawler/theaters.py`의 `DEFAULT_REGION_QUERIES`에 있다 (현재 서울 주요 상권 + 예술영화관 중심).
`"{지역명} 영화관"` 형태로 문자열만 추가하면 커버리지가 늘어난다. 재개봉작은 이 시딩과 별개로
`get_schedule_theaters()`가 전국 단위로 정밀 재조회하므로 지역 시딩 밖이어도 대부분 잡힌다.

## 로컬 실행

```bash
pip install -r requirements.txt
cp .env.example .env   # KOBIS_API_KEY, DISCORD_WEBHOOK_URL 입력 (둘 다 선택)
python -m crawler.main
python -m http.server 8123 --directory docs
# → http://localhost:8123
```

## 배포 설정 (최초 1회)

Pages 활성화는 워크플로가 자동으로 처리한다(`configure-pages` + `enablement: true`). 필요한 것:

1. **저장소를 public으로 전환** (무료 플랜의 GitHub Pages 조건).
   과거 커밋에 API 키가 포함되어 있으므로 전환 전 키 재발급 권장 — KOBIS는 [kobis.or.kr](https://www.kobis.or.kr/kobisopenapi)에서 무료 재발급.
2. (선택) **Settings → Secrets and variables → Actions** → `KOBIS_API_KEY` 시크릿 추가.
   없어도 동작한다 — 크롤러가 이전 movies.json 의 원개봉일을 승계하고, 새 재개봉작만 보강이 빠진다.
3. (선택) **Discord 알림 설정**:
   - 디스코드 서버 → 채널 설정(⚙️) → 연동 → 웹후크 → 새 웹후크 → 채널 선택 → **웹후크 URL 복사**
   - 저장소 **Settings → Secrets and variables → Actions** → `DISCORD_WEBHOOK_URL` 시크릿 추가
   - 없어도 동작한다 — 알림 전송만 조용히 건너뛴다
4. push 하면 워크플로가 크롤 → 데이터 커밋 → Pages 배포까지 자동 실행된다.
   사이트 주소: `https://<계정>.github.io/MovieReRelease/`

### Discord 알림 동작 방식
매 크롤마다 오늘 감지된 재개봉작을 이전 `movies.json`과 비교해, **naver_os(영화 고유 id) 기준으로
어제 없던 것만** 새 재개봉작으로 판단해 알림을 보낸다. 이미 알려진 재개봉작은 매일 재알림하지 않는다.
상영 예정(개봉 전)도 재개봉 라벨이 붙는 순간 알림 대상이라, 실제 상영보다 먼저 알 수 있다.

## 로드맵

- [x] **Phase 1** — 재개봉 감지 + 목록 사이트 + 매일 자동 갱신
- [x] **Phase 2** — 지역 극장 상영 여부 + 지도 연계: 영화 클릭 → 상영 중인 극장 목록·지도 표시
- [x] **Phase 2.5** — 재개봉작 전국 상영관 정밀 조회 + 신규 재개봉작 Discord 알림
- [ ] **Phase 3** — 지역 시딩 커버리지 확장(현재 now_playing 전체는 서울 위주 그대로), 극장 체인별 커버리지 불균형 개선

### 알려진 한계
- 극장별 상영작 데이터는 네이버 Place 위젯에 의존 — 일부 극장(특히 롯데시네마·메가박스 일부 지점)은
  위젯이 연동되어 있지 않아 상영작이 비어 있을 수 있다. 공식 API가 아니므로 페이지 구조가 바뀌면 깨질 수 있다.
- 짧은 시간에 요청이 몰리면 네이버가 일시적으로 빈 응답을 줄 수 있다 — `theaters.py`가 요청 간 2~4초 딜레이를 둔다.
