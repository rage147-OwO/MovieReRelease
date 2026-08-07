"use strict";

const state = { tab: "now", onlyRerelease: true, data: null, theaters: new Map(), movies: [] };
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
const $modalList = document.getElementById("modal-theater-list");
const $modalEmpty = document.getElementById("modal-empty");
const $modalFallbackLink = document.getElementById("modal-fallback-link");

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
  document.addEventListener("keydown", (e) => {
    if (e.key === "Escape" && !$modalBackdrop.hidden) closeModal();
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

function openModal(movie) {
  if (!movie) return;

  $modalTitle.textContent = movie.title;
  $modalSub.innerHTML = movie.naver_link
    ? `<a href="${escapeAttr(movie.naver_link)}" target="_blank" rel="noopener">네이버에서 보기 ↗</a>`
    : "";

  const theaterList = (movie.theaters || [])
    .map((id) => state.theaters.get(id))
    .filter(Boolean);

  $modalFallbackLink.href = movie.naver_link || "#";

  // 지도 컨테이너가 실제로 보이는 상태여야 Leaflet이 크기를 올바르게 계산한다 —
  // hidden 해제를 먼저 하고 나서 지도를 그린다.
  $modalBackdrop.hidden = false;
  document.body.style.overflow = "hidden";
  document.getElementById("modal-close").focus();

  if (theaterList.length === 0) {
    $modalMap.hidden = true;
    $modalList.hidden = true;
    $modalEmpty.hidden = false;
  } else {
    $modalMap.hidden = false;
    $modalList.hidden = false;
    $modalEmpty.hidden = true;
    $modalList.innerHTML = theaterList
      .map(
        (t) => `
      <li>
        <span class="theater-name">${escapeHtml(t.name)}</span>
        <span class="theater-addr">${escapeHtml(t.address || "")}</span>
      </li>`
      )
      .join("");
    renderMap(theaterList);
  }
}

function closeModal() {
  $modalBackdrop.hidden = true;
  document.body.style.overflow = "";
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
