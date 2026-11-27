function plusDays(date, days) {
  const day = new Date(date + "T00:00:00Z");
  day.setUTCDate(day.getUTCDate() + days);
  return day.toISOString().slice(0, 10);
}

function findReleases(movies, start, end) {
  const found = new Map();
  for (const movie of movies) {
    const date = movie.release_date;
    if (!movie.is_rerelease || !/^\d{4}-\d{2}-\d{2}$/.test(date) || date < start || date > end) continue;
    const key = (movie.naver_os || movie.title) + "/" + date;
    if (!found.has(key)) found.set(key, movie);
  }
  return [...found.values()].sort((a, b) => a.release_date.localeCompare(b.release_date) || a.title.localeCompare(b.title));
}

function movieDetails(movie, theaterNames, start, end) {
  const description = [movie.genre, movie.runtime, movie.original_open_date && "원개봉 " + movie.original_open_date]
    .filter(Boolean).join(" · ");
  const listed = new Set(movie.theaters || []);
  const showtimes = [];
  for (const [id, days] of Object.entries(movie.theater_times || {})) {
    const name = theaterNames.get(id);
    if (!name) continue;
    for (const [date, times] of Object.entries(days)) {
      if (date >= start && date <= end && times.length) {
        showtimes.push({ date, name, times });
      }
    }
  }
  const theaterList = [...listed].map(id => theaterNames.get(String(id))).filter(Boolean);
  const theaters = theaterList.slice(0, 6).join(", ");
  const timeLines = showtimes.sort((a, b) => a.date.localeCompare(b.date) || a.name.localeCompare(b.name))
    .slice(0, 6).map(({ date, name, times }) => "  " + date.slice(5) + " " + name + " " + times.join(", "));
  return [
    movie.release_date + " · " + movie.title,
    description && "  " + description,
    theaters && "  상영관 " + theaters + (theaterList.length > 6 ? " 외 " + (theaterList.length - 6) + "곳" : ""),
    ...(timeLines.length ? timeLines : ["  확인된 상영시간 없음"]),
    movie.naver_link && "  상세 일정 " + movie.naver_link,
  ].filter(Boolean).join("\n");
}

export function buildDigest(scheduledTime, siteUrl, moviesData, theatersData) {
  const today = new Date(scheduledTime + 9 * 60 * 60 * 1000);
  const daysSinceMonday = (today.getUTCDay() + 6) % 7;
  const week = plusDays(today.toISOString().slice(0, 10), -daysSinceMonday);
  const end = plusDays(week, 6);
  const movies = [...moviesData.now_playing, ...moviesData.upcoming];
  const theaterNames = new Map(theatersData.theaters.map(theater => [String(theater.id), theater.name]));
  const current = findReleases(movies, week, end);
  const upcoming = findReleases(movies, plusDays(week, 7), plusDays(week, 13));
  const body = [
    "이번 주 신규 재개봉 (" + week + " ~ " + end + ")",
    current.length
      ? current.map(movie => movieDetails(movie, theaterNames, week, end)).join("\n\n")
      : "현재 사이트 데이터에서 확인된 신규 재개봉작이 없어요.",
    upcoming.length && "다음 주 재개봉 예정\n" +
      upcoming.map(movie => movie.release_date + " · " + movie.title).join("\n"),
    (moviesData.generated_at ? "영화 정보 갱신 " + moviesData.generated_at.slice(0, 16).replace("T", " ") + "\n" : "") +
      "전체 목록과 최신 상영 일정\n" + siteUrl,
  ].filter(Boolean);
  return { week, subject: "[재개봉 알리미] " + week + " ~ " + end, text: body.join("\n\n") };
}
