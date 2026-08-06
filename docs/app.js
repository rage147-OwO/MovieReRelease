"use strict";

const state = { tab: "now", onlyRerelease: true, data: null };

const $grid = document.getElementById("grid");
const $stats = document.getElementById("stats");
const $empty = document.getElementById("empty");
const $error = document.getElementById("error");
const $updated = document.getElementById("updated");

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

  try {
    const res = await fetch("data/movies.json", { cache: "no-cache" });
    if (!res.ok) throw new Error(res.status);
    state.data = await res.json();
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

  $grid.innerHTML = movies.map(cardHtml).join("");
  $empty.hidden = movies.length > 0;
}

function cardHtml(m) {
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

  return `
<a class="card" href="${escapeAttr(m.naver_link || "#")}" target="_blank" rel="noopener">
  <div class="poster">
    ${poster}
    ${m.is_rerelease ? `<span class="badge-re">재개봉</span>` : ""}
    ${m.dday ? `<span class="badge-dday">${escapeHtml(m.dday)}</span>` : ""}
  </div>
  <div class="card-body">
    <h3 class="title">${escapeHtml(m.title)}</h3>
    <p class="meta">${meta}</p>
    <p class="dates">${dateLine}${origLine}</p>
  </div>
</a>`;
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
