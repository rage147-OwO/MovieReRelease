"use strict";

// 극장 절반가량은 주소 없이 이름만 있다(스케줄 API로만 발견돼 좌표를 못 얻은
// 경우) — 그래도 체인 지점명엔 대개 시/군 지명이 박혀 있어서("메가박스
// 홍성내포", "CGV 논산") 이름 매칭만으로도 지역 그룹핑은 꽤 정확해진다.
// 완전한 행정구역 목록은 아니고, 실제 등장하는 체인 지점명 위주로 채웠다.
const REGION_KEYWORDS = {
  seoul: ["서울", "강남", "홍대", "종로", "잠실", "여의도", "왕십리", "신촌", "합정",
    "건대입구", "구로", "등촌", "불광", "성신여대", "수유", "중계", "천호", "청담",
    "고덕강일", "상봉", "군자", "신도림", "마곡", "가산", "압구정"],
  gyeonggi: ["경기", "인천", "경기광주", "수원", "부천", "고양", "성남", "용인",
    "안산", "안양", "남양주", "화성", "평택", "의정부", "시흥", "파주", "김포",
    "광명", "군포", "이천", "양주", "오산", "구리", "안성", "포천", "의왕", "하남",
    "여주", "동두천", "과천", "가평", "연천", "광교", "동탄", "별내", "다산", "위례",
    "미사", "병점", "범계", "산본", "일산", "행신", "장현", "계양", "부평", "논현",
    "영종", "검단", "송도", "주안", "강화", "동백", "킨텍스", "설성"],
  gangwon: ["강원", "춘천", "원주", "강릉", "동해", "태백", "속초", "삼척", "홍천",
    "횡성", "영월", "평창", "정선", "철원", "화천", "양구", "인제", "고성", "양양",
    "기린"],
  chungcheong: ["대전", "충남", "충북", "충청", "세종", "청주", "충주", "제천",
    "보은", "옥천", "영동", "진천", "괴산", "음성", "단양", "증평", "오창", "혁신",
    "사창", "천안", "공주", "보령", "아산", "서산", "논산", "계룡", "당진", "홍성",
    "예산", "태안", "금산", "부여", "서천", "청양", "유성", "대전가오"],
  jeolla: ["광주", "전남", "전북", "전라", "제주", "전주", "군산", "익산", "정읍",
    "남원", "김제", "완주", "진안", "무주", "장수", "임실", "순창", "고창", "부안",
    "서전주", "목포", "여수", "순천", "나주", "광양", "담양", "곡성", "구례", "고흥",
    "보성", "화순", "장흥", "강진", "해남", "영암", "무안", "함평", "영광", "장성",
    "완도", "진도", "신안", "서귀포", "연동"],
  gyeongsang: ["부산", "대구", "울산", "경남", "경북", "경상", "포항", "경주",
    "김천", "안동", "구미", "영주", "영천", "상주", "문경", "경산", "군위", "의성",
    "청송", "영양", "영덕", "청도", "고령", "성주", "칠곡", "예천", "봉화", "울진",
    "울릉", "창원", "진주", "통영", "사천", "김해", "밀양", "거제", "양산", "의령",
    "함안", "창녕", "남해", "하동", "산청", "함양", "거창", "합천", "마산", "진해",
    "해운대", "화명", "덕천", "금정", "명지", "죽전", "성서", "상인", "동래", "센텀시티"],
};
const REGION_GROUPS = [
  { id: "seoul", label: "서울", keywords: REGION_KEYWORDS.seoul },
  { id: "gyeonggi", label: "경기·인천", keywords: REGION_KEYWORDS.gyeonggi },
  { id: "gangwon", label: "강원", keywords: REGION_KEYWORDS.gangwon },
  { id: "chungcheong", label: "대전·충청·세종", keywords: REGION_KEYWORDS.chungcheong },
  { id: "jeolla", label: "광주·전라·제주", keywords: REGION_KEYWORDS.jeolla },
  { id: "gyeongsang", label: "부산·대구·울산·경상", keywords: REGION_KEYWORDS.gyeongsang },
];
// 이름 자체에 지명이 아예 없어 키워드 매칭이 원천적으로 불가능한 극장들
// (예: "1939시네마"는 가평에 있지만 이름 어디에도 "가평"이 없다) — 직접 찾아서
// 하드코딩. 검색으로 확인한 실제 소재지(2026-08 기준):
//   애관극장 — 인천 중구 개항로 63-2 (한국에서 제일 오래된 극장)
//   달홀영화관 — 강원 고성군 간성읍 (달홀 = 고성의 옛 지명)
//   1939시네마 — 경기 가평군 가평읍
//   토마토시네마 — 강원 화천군 사내면
const MANUAL_REGION_OVERRIDES = {
  "애관극장": "gyeonggi",
  "달홀영화관": "gangwon",
  "1939시네마": "gyeonggi",
  "토마토시네마": "gangwon",
};
// 극장이 이보다 많으면 지역별로 묶고, 각 극장은 접어서(클릭 시 펼침) 보여준다 —
// 재개봉작처럼 몇 곳 안 되면 굳이 묶을 필요 없이 다 펼쳐 보여주는 게 낫다.
const COLLAPSE_THRESHOLD = 5;

const state = {
  tab: "now",
  onlyRerelease: true,
  data: null,
  theaters: new Map(),
  movies: [],
  myRegion: localStorage.getItem("myRegion") || "",
};
let leafletMap = null;
let markerLayer = null;

const $grid = document.getElementById("grid");
const $stats = document.getElementById("stats");
const $empty = document.getElementById("empty");
const $error = document.getElementById("error");
const $updated = document.getElementById("updated");

const $modalBackdrop = document.getElementById("theater-modal");
const $modalTitle = document.getElementById("modal-title");
const $modalSub = document.getElementById("modal-sub");
const $modalMap = document.getElementById("modal-map");
const $modalDateTabs = document.getElementById("modal-date-tabs");
const $modalList = document.getElementById("modal-theater-list");
const $modalEmpty = document.getElementById("modal-empty");
const $modalFallbackLink = document.getElementById("modal-fallback-link");

const WEEKDAY_KO = ["일", "월", "화", "수", "목", "금", "토"];

const $notifyBackdrop = document.getElementById("notify-modal");

init();

async function init() {
  document.querySelectorAll(".tab").forEach((btn) => {
    btn.addEventListener("click", () => {
      state.tab = btn.dataset.tab;
      document.querySelectorAll(".tab").forEach((b) => {
        const active = b === btn;
        b.classList.toggle("active", active);
        b.setAttribute("aria-selected", String(active));
      });
      render();
    });
  });

  document.getElementById("only-rerelease").addEventListener("change", (e) => {
    state.onlyRerelease = e.target.checked;
    render();
  });

  const $regionSelect = document.getElementById("region-select");
  $regionSelect.value = state.myRegion;
  $regionSelect.addEventListener("change", (e) => {
    state.myRegion = e.target.value;
    if (state.myRegion) {
      localStorage.setItem("myRegion", state.myRegion);
    } else {
      localStorage.removeItem("myRegion");
    }
  });

  $grid.addEventListener("click", (e) => {
    const card = e.target.closest(".card");
    if (card) openModal(state.movies[Number(card.dataset.idx)]);
  });
  $grid.addEventListener("keydown", (e) => {
    if (e.key !== "Enter" && e.key !== " ") return;
    const card = e.target.closest(".card");
    if (!card) return;
    e.preventDefault();
    openModal(state.movies[Number(card.dataset.idx)]);
  });

  document.getElementById("modal-close").addEventListener("click", closeModal);
  $modalBackdrop.addEventListener("click", (e) => {
    if (e.target === $modalBackdrop) closeModal();
  });

  $modalDateTabs.addEventListener("click", (e) => {
    const btn = e.target.closest(".date-tab");
    if (!btn || !modalState) return;
    modalState.selectedDate = btn.dataset.date;
    $modalDateTabs.querySelectorAll(".date-tab").forEach((b) => b.classList.toggle("active", b === btn));
    renderTheaterList();
  });

  document.getElementById("notify-info-btn").addEventListener("click", () => {
    $notifyBackdrop.hidden = false;
    document.body.style.overflow = "hidden";
    document.getElementById("notify-modal-close").focus();
  });
  document.getElementById("notify-modal-close").addEventListener("click", closeNotifyModal);
  $notifyBackdrop.addEventListener("click", (e) => {
    if (e.target === $notifyBackdrop) closeNotifyModal();
  });

  document.getElementById("copy-feed-url").addEventListener("click", async (e) => {
    const text = document.getElementById("feed-url-text").textContent;
    const btn = e.currentTarget;
    try {
      await navigator.clipboard.writeText(text);
      btn.textContent = "복사됨!";
    } catch {
      btn.textContent = "복사 실패";
    }
    setTimeout(() => (btn.textContent = "복사"), 1500);
  });

  document.addEventListener("keydown", (e) => {
    if (e.key !== "Escape") return;
    if (!$modalBackdrop.hidden) closeModal();
    if (!$notifyBackdrop.hidden) closeNotifyModal();
  });

  try {
    const [moviesRes, theatersRes] = await Promise.all([
      fetch("data/movies.json", { cache: "no-cache" }),
      fetch("data/theaters.json", { cache: "no-cache" }),
    ]);
    if (!moviesRes.ok) throw new Error(moviesRes.status);
    state.data = await moviesRes.json();
    if (theatersRes.ok) {
      const theatersData = await theatersRes.json();
      state.theaters = new Map((theatersData.theaters || []).map((t) => [t.id, t]));
    }
  } catch (err) {
    $error.hidden = false;
    return;
  }

  if (state.data.generated_at) {
    $updated.textContent = formatUpdated(state.data.generated_at) + " 갱신";
  }
  render();
}

function render() {
  if (!state.data) return;
  const isNow = state.tab === "now";
  const list = (isNow ? state.data.now_playing : state.data.upcoming) || [];
  const rereleaseCount = list.filter((m) => m.is_rerelease).length;
  const movies = state.onlyRerelease ? list.filter((m) => m.is_rerelease) : list.slice();

  // 상영 중은 최근 (재)개봉 순, 개봉 예정은 가까운 날짜 순
  movies.sort((a, b) => {
    const ka = a.release_date || "";
    const kb = b.release_date || "";
    if (!ka && !kb) return 0;
    if (!ka) return 1;
    if (!kb) return -1;
    return isNow ? kb.localeCompare(ka) : ka.localeCompare(kb);
  });

  const label = isNow ? "상영 중" : "개봉 예정";
  $stats.innerHTML = `${label} <strong>${list.length}</strong>편 중 재개봉 <strong>${rereleaseCount}</strong>편`;

  state.movies = movies;
  $grid.innerHTML = movies.map((m, idx) => cardHtml(m, idx)).join("");
  $empty.hidden = movies.length > 0;
}

function cardHtml(m, idx) {
  const poster = m.poster
    ? `<img src="${escapeAttr(m.poster)}" alt="${escapeAttr(m.title)} 포스터" loading="lazy"
         onerror="this.replaceWith(Object.assign(document.createElement('div'),{className:'no-img',textContent:'🎞️'}))">`
    : `<div class="no-img">🎞️</div>`;

  const meta = [m.genre, m.runtime, m.rating ? `<span class="star">★ ${escapeHtml(m.rating)}</span>` : null]
    .filter(Boolean)
    .map((v) => (v.startsWith("<span") ? v : escapeHtml(v)))
    .join(" · ");

  const dateLabel = m.is_rerelease ? "재개봉" : "개봉";
  const dateLine = m.release_raw
    ? `<span class="re-date${m.is_rerelease ? " is-re" : ""}">${dateLabel} ${escapeHtml(trimDot(m.release_raw))}</span>`
    : "";

  let origLine = "";
  if (m.original_open_date) {
    const gap = yearGap(m.original_open_date, m.release_date);
    origLine = `<span class="orig">원개봉 ${escapeHtml(m.original_open_date.replaceAll("-", "."))}${
      gap >= 1 ? ` · ${gap}년 만` : ""
    }</span>`;
  } else if (m.is_rerelease && m.prdt_year) {
    origLine = `<span class="orig">${escapeHtml(m.prdt_year)}년 작품</span>`;
  }

  const theaterCount = (m.theaters || []).length;
  const theaterBadge = theaterCount > 0 ? `<span class="badge-theater">🎦 ${theaterCount}개관</span>` : "";

  return `
<div class="card" data-idx="${idx}" tabindex="0" role="button" aria-haspopup="dialog"
     aria-label="${escapeAttr(m.title)} — 상영관 보기">
  <div class="poster">
    ${poster}
    ${m.is_rerelease ? `<span class="badge-re">재개봉</span>` : ""}
    ${m.dday ? `<span class="badge-dday">${escapeHtml(m.dday)}</span>` : ""}
  </div>
  <div class="card-body">
    <h3 class="title">${escapeHtml(m.title)}</h3>
    <p class="meta">${meta}</p>
    <p class="dates">${dateLine}${origLine}</p>
    ${theaterBadge}
  </div>
</div>`;
}

let modalState = null; // { theaterList, times, dates, selectedDate }

function openModal(movie) {
  if (!movie) return;

  $modalTitle.textContent = movie.title;
  $modalSub.innerHTML = movie.naver_link
    ? `<a href="${escapeAttr(movie.naver_link)}" target="_blank" rel="noopener">네이버에서 보기 ↗</a>`
    : "";

  const theaterList = (movie.theaters || [])
    .map((id) => state.theaters.get(id))
    .filter(Boolean);

  // 내 지역으로 설정한 게 있으면 그 지역 극장을 목록 위로 올린다 (필터링은 아님 —
  // 다른 지역 상영관도 여전히 보여준다, 다만 순서만 우선).
  if (state.myRegion) {
    theaterList.sort((a, b) => (regionIdOf(b) === state.myRegion) - (regionIdOf(a) === state.myRegion));
  }

  $modalFallbackLink.href = movie.naver_link || "#";

  // 지도 컨테이너가 실제로 보이는 상태여야 Leaflet이 크기를 올바르게 계산한다 —
  // hidden 해제를 먼저 하고 나서 지도를 그린다.
  $modalBackdrop.hidden = false;
  document.body.style.overflow = "hidden";
  document.getElementById("modal-close").focus();

  if (theaterList.length === 0) {
    modalState = null;
    $modalMap.hidden = true;
    $modalDateTabs.hidden = true;
    $modalList.hidden = true;
    $modalEmpty.hidden = false;
    return;
  }

  $modalList.hidden = false;
  $modalEmpty.hidden = true;

  const times = movie.theater_times || {};
  const dateSet = new Set();
  theaterList.forEach((t) => Object.keys(times[t.id] || {}).forEach((d) => dateSet.add(d)));
  const dates = [...dateSet].sort();

  modalState = { theaterList, times, dates, selectedDate: dates[0] || null };

  if (dates.length > 0) {
    $modalDateTabs.hidden = false;
    $modalDateTabs.innerHTML = dates
      .map((d, i) => {
        const dt = new Date(d + "T00:00:00+09:00");
        const label = i === 0 ? "오늘" : WEEKDAY_KO[dt.getDay()];
        return `<button class="date-tab${i === 0 ? " active" : ""}" data-date="${d}">
          <span class="date-tab-num">${dt.getDate()}</span><span class="date-tab-day">${label}</span>
        </button>`;
      })
      .join("");
  } else {
    $modalDateTabs.hidden = true;
  }

  renderTheaterList();
}

function renderTheaterList() {
  if (!modalState) return;
  const { theaterList, times, selectedDate } = modalState;

  // 날짜 탭이 있는 영화는 선택한 날짜에 실제 상영 정보가 있는 극장만 보여준다
  // (없는 걸 "상영 정보 없음"으로 나열하기보다 아예 안 보이는 게 더 명확하다).
  // 날짜 정보 자체가 없는 영화(지역 매칭만 된 경우)는 항상 전체를 보여준다.
  const visibleTheaters = selectedDate
    ? theaterList.filter((t) => (times[t.id]?.[selectedDate]?.length ?? 0) > 0)
    : theaterList;

  // 선택한 날짜에 해당하는 극장이 하나도 없으면(이론상 dates는 극장별
  // 스케줄의 합집합이라 발생하지 않아야 하지만, 데이터 이상치에 대비해
  // 방어적으로) 빈 리스트 대신 안내 문구를 보여준다 — 지도·리스트·안내
  // 전부 없는 완전히 빈 화면이 되는 걸 막는다.
  if (!visibleTheaters.length) {
    $modalList.innerHTML = `<li class="theater-list-empty">이 날짜엔 상영 정보가 있는 극장이 없어요</li>`;
    $modalMap.hidden = true;
    return;
  }

  const grouped = visibleTheaters.length >= COLLAPSE_THRESHOLD;

  const rowHtml = (t) => {
    const dayTimes = selectedDate ? times[t.id]?.[selectedDate] : null;
    const timesHtml = dayTimes && dayTimes.length
      ? `<span class="theater-times">${dayTimes
          .map((time) => `<span class="time-chip">${escapeHtml(time)}</span>`)
          .join("")}</span>`
      : `<span class="theater-times no-show">상영시간 정보 없음</span>`;
    // 묶어서 보여줄 땐 그룹 헤더가 지역을 이미 알려주니 배지는 생략한다.
    const nearBadge = !grouped && state.myRegion && regionIdOf(t) === state.myRegion
      ? `<span class="badge-near">내 지역</span>`
      : "";
    const nameAddr = `<span class="theater-name">${escapeHtml(t.name)}${nearBadge}</span>
        <span class="theater-addr">${escapeHtml(t.address || (t.lat ? "" : "주소·좌표 미확인"))}</span>`;

    // 극장이 많을 땐 <details>로 접어둔다 — 클릭(탭)하면 시간이 펼쳐진다.
    // 네이티브 요소라 별도 JS 토글 코드 없이 접근성도 챙겨진다.
    return grouped
      ? `<li class="theater-row-collapsible"><details><summary>${nameAddr}</summary>${timesHtml}</details></li>`
      : `<li>${nameAddr}${timesHtml}</li>`;
  };

  if (grouped) {
    const groups = REGION_GROUPS.map((g) => ({ ...g, theaters: [] }));
    const etc = { id: "etc", label: "기타", theaters: [] };
    for (const t of visibleTheaters) {
      const rid = regionIdOf(t);
      const g = rid ? groups.find((gr) => gr.id === rid) : undefined;
      (g || etc).theaters.push(t);
    }
    const nonEmpty = [...groups, etc].filter((g) => g.theaters.length > 0);
    // 내 지역만 맨 앞으로 빼고 나머지는 원래(지리적) 순서를 그대로 유지한다.
    // (예전엔 sort+reverse를 같이 써서 전체 순서가 통째로 뒤집히는 버그가 있었다.)
    if (state.myRegion) {
      const myIdx = nonEmpty.findIndex((g) => g.id === state.myRegion);
      if (myIdx > 0) nonEmpty.unshift(...nonEmpty.splice(myIdx, 1));
    }
    $modalList.innerHTML = nonEmpty
      .map(
        (g) => `
      <li class="region-group-header">${escapeHtml(g.label)} <span class="region-group-count">${g.theaters.length}</span></li>
      ${g.theaters.map(rowHtml).join("")}`
      )
      .join("");
  } else {
    $modalList.innerHTML = visibleTheaters.map(rowHtml).join("");
  }

  // 매칭된 극장 전부 좌표가 없으면(지역 시딩 밖 극장) 빈 지도 박스 대신 리스트만 보여준다.
  const hasCoords = visibleTheaters.some((t) => t.lat && t.lon);
  $modalMap.hidden = !hasCoords;
  if (hasCoords) renderMap(visibleTheaters);
}

function closeModal() {
  $modalBackdrop.hidden = true;
  document.body.style.overflow = "";
}

function closeNotifyModal() {
  $notifyBackdrop.hidden = true;
  document.body.style.overflow = "";
}

function matchesRegion(theater, keywords) {
  // address(시/도 포함 전체 주소)를 우선 보고, 없으면(좌표 미확인 극장) 이름에서라도 찾는다
  // — "안동 중앙시네마"처럼 지명이 이름에 박혀 있는 경우를 잡기 위함.
  const text = `${theater.address || ""} ${theater.name || ""}`;
  return keywords.some((k) => text.includes(k)) ? 1 : 0;
}

// 이 극장이 속한 지역 id를 하나 고른다 (없으면 null → "기타").
// MANUAL_REGION_OVERRIDES를 먼저 보고, 없으면 키워드 매칭으로 판단한다.
function regionIdOf(theater) {
  const override = MANUAL_REGION_OVERRIDES[theater.name];
  if (override) return override;
  const group = REGION_GROUPS.find((g) => matchesRegion(theater, g.keywords));
  return group ? group.id : null;
}

function renderMap(theaterList) {
  if (typeof L === "undefined") return; // Leaflet CDN 로드 실패 시 지도만 조용히 생략

  if (!leafletMap) {
    // center/zoom 없이 만들면 setView 전까지 맵이 "로드"되지 않아 레이어가 그려지지 않는다 —
    // 서울 중심으로 초기 뷰를 잡아 즉시 로드시킨다 (아래에서 실제 좌표로 다시 맞춘다).
    leafletMap = L.map($modalMap, { scrollWheelZoom: false, center: [37.5665, 126.978], zoom: 11 });
    L.tileLayer("https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png", {
      attribution: "© OpenStreetMap",
      maxZoom: 19,
    }).addTo(leafletMap);
    markerLayer = L.layerGroup().addTo(leafletMap);
  }

  markerLayer.clearLayers();
  const points = [];
  for (const t of theaterList) {
    const lat = parseFloat(t.lat);
    const lon = parseFloat(t.lon);
    if (isNaN(lat) || isNaN(lon)) continue;
    L.marker([lat, lon]).addTo(markerLayer).bindPopup(escapeHtml(t.name));
    points.push([lat, lon]);
  }

  // 모달이 이미 보이는 상태에서 호출되므로(openModal 참고) 컨테이너 크기는 이미 확정돼 있다.
  // requestAnimationFrame으로 미루면 background 탭에서 무기한 지연될 수 있어 바로 실행한다.
  leafletMap.invalidateSize({ animate: false, pan: false });
  if (points.length === 1) {
    leafletMap.setView(points[0], 15, { animate: false });
  } else if (points.length > 1) {
    leafletMap.fitBounds(points, { padding: [24, 24], animate: false });
  }
}

function yearGap(origIso, reIso) {
  const o = parseInt(origIso, 10);
  const r = parseInt(reIso, 10);
  if (!o || !r) return 0;
  return r - o;
}

function trimDot(s) {
  return s.replace(/\.$/, "");
}

function formatUpdated(iso) {
  const d = new Date(iso);
  if (isNaN(d)) return iso;
  const pad = (n) => String(n).padStart(2, "0");
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())} ${pad(d.getHours())}:${pad(d.getMinutes())}`;
}

function escapeHtml(s) {
  return String(s ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;");
}

function escapeAttr(s) {
  return escapeHtml(s).replaceAll('"', "&quot;");
}
