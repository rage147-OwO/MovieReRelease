# 🎬 재개봉 레이더 (MovieReRelease)

지금 극장에서 다시 만날 수 있는 **재개봉 영화**를 매일 자동으로 수집해 보여주는 정적 웹사이트.

## 동작 방식

```
GitHub Actions (매일 06:00 KST)
  └─ crawler/ 실행
       ├─ 네이버 통합검색 JSONP → 현재 상영작 / 개봉 예정작 수집
       │    └─ 카드의 개봉일 라벨이 '재개봉'이면 재개봉작으로 판정
       ├─ KOBIS 오픈API → 재개봉작의 원개봉일·제작연도 보강
       └─ docs/data/movies.json 갱신 → 커밋/푸시
GitHub Pages (docs/) → 정적 사이트 서빙
```

## 구조

```
crawler/
  naver.py    네이버 영화 목록 파싱 (JSONP + BeautifulSoup)
  kobis.py    KOBIS 원개봉일 조회 (재개봉작 보강용)
  main.py     실행 진입점 → docs/data/movies.json 생성
docs/         GitHub Pages 루트 (index.html + app.js + data/movies.json)
.github/workflows/crawl.yml   매일 자동 크롤 워크플로
```

## 로컬 실행

```bash
pip install -r requirements.txt
cp .env.example .env   # KOBIS_API_KEY 입력 (선택)
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
3. push 하면 워크플로가 크롤 → 데이터 커밋 → Pages 배포까지 자동 실행된다.
   사이트 주소: `https://<계정>.github.io/MovieReRelease/`

## 로드맵

- [x] **Phase 1** — 재개봉 감지 + 목록 사이트 + 매일 자동 갱신
- [ ] **Phase 2** — 지역 선택: 내 지역 영화관에서 재개봉작 상영 여부 (영화관별 시간표 크롤링)
- [ ] **Phase 3** — 지도 연계: 영화 클릭 → 상영 중인 영화관을 지도에 표시
