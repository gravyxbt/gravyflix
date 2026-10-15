const $ = (id) => document.getElementById(id);
let catalog = [],
  history = [],
  selected = null,
  detail = null,
  view = "home",
  busy = false,
  polling = false,
  seeking = false,
  tv = {},
  artworkToken = 0;
const fallback = "/web/assets/card.png";
const clock = (n) => {
  n = Math.max(0, Math.floor(n || 0));
  return (
    (n >= 3600 ? Math.floor(n / 3600) + ":" : "") +
    String(Math.floor(n / 60) % 60).padStart(n >= 3600 ? 2 : 1, "0") +
    ":" +
    String(n % 60).padStart(2, "0")
  );
};
const runtime = (n) =>
  n
    ? `${Math.floor(n / 3600) ? Math.floor(n / 3600) + "h " : ""}${Math.round((n % 3600) / 60)}m`
    : "";
const episodes = (item) =>
  item.kind === "show" ? item.seasons.flatMap((s) => s.episodes) : [];
const first = (item) =>
  item.kind === "show"
    ? episodes(item).find((e) => e.season_number > 0) || episodes(item)[0]
    : item;
const record = (item) =>
  history.find(
    (h) =>
      h.movie_id === item?.id &&
      !h.completed &&
      h.resume_valid !== false &&
      h.position > 15 &&
      h.position < h.duration - 30,
  );
const resume = (item) =>
  item.kind === "show"
    ? item.resume_episode || null
    : record(item)
      ? item
      : null;
const artwork = (item) => item?.landscape_url || item?.backdrop_url || fallback;
const metadata = (item) =>
  [
    item.year,
    item.kind === "show"
      ? `${item.season_count} season${item.season_count === 1 ? "" : "s"} · ${item.episode_count} episodes`
      : runtime(item.duration),
    ...(item.genres || []).slice(0, 3),
  ]
    .filter(Boolean)
    .join(" · ");
function captionLabel(item) {
  const s = item?.subtitle_summary;
  if (!s) return "Subtitle availability not checked";
  if (item.kind === "show")
    return s.episodes_available
      ? `CC · Subtitles on ${s.episodes_available} of ${s.episode_total} episodes`
      : s.episodes_converting
        ? "Embedded subtitles converting automatically"
        : s.episodes_with_embedded_images
          ? "Embedded image subtitles · Conversion required"
        : "No subtitles available yet";
  if (s.has_full)
    return `CC · Subtitles available${s.languages?.length ? " · " + s.languages.map((x) => ({ eng: "English", spa: "Spanish", fre: "French", ger: "German" })[x] || x.toUpperCase()).join(", ") : ""}`;
  if (s.has_forced) return "CC · Forced subtitles only";
  if (s.conversion_pending) return "Converting embedded subtitles…";
  if (s.embedded_image_count) return "Embedded image subtitles · Conversion required";
  return ["pending", "queued", "checking", "processing"].includes(s.state)
    ? "Subtitles being checked"
    : "No subtitles available yet";
}
async function api(path, body) {
  const response = await fetch(path, {
    cache: "no-store",
    signal: AbortSignal.timeout(30000),
    ...(body !== undefined
      ? {
          method: "POST",
          headers: {
            "Content-Type": "application/json",
            "X-Media-Control": "1",
          },
          body: JSON.stringify(body),
        }
      : {}),
  });
  const data = await response.json();
  if (!response.ok)
    throw Error(
      typeof data.detail === "string"
        ? data.detail
        : "Request failed. Please try again.",
    );
  return data;
}
function image(img, url) {
  img.onerror = () => {
    img.onerror = null;
    img.src = fallback;
  };
  img.src = url || fallback;
}
function hero(item) {
  if (!item) return;
  selected = item;
  $("hero-title").textContent = item.title;
  $("hero-kind").textContent = item.kind === "show" ? "SERIES" : "MOVIE";
  $("hero-meta").textContent = metadata(item);
  $("hero-description").textContent =
    item.description ||
    item.overview ||
    (item.kind === "show"
      ? "Choose an episode and settle in."
      : "From your personal movie collection. Ready for the big screen.");
  $("hero-subtitles").textContent = captionLabel(item);
  $("hero-play").disabled = false;
  $("hero-info").disabled = false;
  $("hero-play").textContent = item.kind === "show" && resume(item) && !record(resume(item)) ? "Next Episode" : resume(item)
    ? "▶ Resume on TV"
    : item.kind === "show"
      ? "▶ Play series on TV"
      : "▶ Play on TV";
  const token = ++artworkToken;
  const url = item.backdrop_url || item.landscape_url || "/web/assets/hero.png";
  if ($("hero-art").dataset.url === url) return;
  const preload = new Image();
  preload.onload = () => {
    if (token === artworkToken) {
      $("hero-art").src = url;
      $("hero-art").dataset.url = url;
    }
  };
  preload.onerror = () => {
    if (token === artworkToken) $("hero-art").src = "/web/assets/hero.png";
  };
  preload.src = url;
}
function card(item) {
  const button = document.createElement("button");
  button.className = "card";
  button.setAttribute(
    "aria-label",
    `${item.title}, ${item.kind === "show" ? "series" : "movie"}`,
  );
  const art = document.createElement("div");
  art.className = "card-art";
  const img = document.createElement("img");
  img.alt = "";
  img.loading = "lazy";
  img.decoding = "async";
  image(img, artwork(item));
  art.append(img);
  const r = resume(item),
    h = record(r);
  if (h) {
    const progress = document.createElement("div");
    progress.className = "progress";
    progress.style.width = `${Math.min(100, (h.position / h.duration) * 100)}%`;
    art.append(progress);
  }
  const name = document.createElement("span");
  name.className = "card-name";
  name.textContent = item.title;
  const sub = document.createElement("span");
  sub.className = "card-sub";
  sub.textContent =
    item.kind === "show"
      ? `${item.episode_count} episodes`
      : [
          item.year,
          runtime(item.duration),
          item.subtitle_summary?.has_full ? "CC" : "",
        ]
          .filter(Boolean)
          .join(" · ");
  button.append(art, name, sub);
  button.addEventListener("focus", () => hero(item));
  button.addEventListener("pointerenter", (event) => {
    if (event.pointerType === "mouse") hero(item);
  });
  button.onclick = () => openDetails(item);
  return button;
}
function shelf(title, items) {
  if (!items.length) return;
  const section = document.createElement("section");
  section.className = "shelf";
  const heading = document.createElement("h2");
  heading.textContent = title;
  const row = document.createElement("div");
  row.className = "row";
  row.setAttribute("aria-label", title);
  items.forEach((item) => row.append(card(item)));
  row.onkeydown = (e) => {
    if (
      !["ArrowLeft", "ArrowRight"].includes(e.key) ||
      !e.target.classList.contains("card")
    )
      return;
    const next =
      e.key === "ArrowRight"
        ? e.target.nextElementSibling
        : e.target.previousElementSibling;
    if (next) {
      e.preventDefault();
      next.focus();
      next.scrollIntoView({
        block: "nearest",
        inline: "nearest",
        behavior: "smooth",
      });
    }
  };
  section.append(heading, row);
  $("shelves").append(section);
}
function render() {
  $("shelves").replaceChildren();
  $("search-panel").hidden = view !== "search";
  $("hero").hidden = view === "search";
  $("empty").hidden = catalog.length > 0;
  const movies = catalog.filter((i) => i.kind === "movie"),
    shows = catalog.filter((i) => i.kind === "show");
  if (view === "search") {
    const query = $("search").value.trim().toLocaleLowerCase();
    const matches = catalog.filter((i) =>
      [i.title, ...(i.genres || []), ...episodes(i).map((e) => e.title)]
        .join(" ")
        .toLocaleLowerCase()
        .includes(query),
    );
    shelf(
      query
        ? `Results for “${$("search").value.trim()}”`
        : "Browse your library",
      matches,
    );
    if (!matches.length) {
      const p = document.createElement("p");
      p.textContent = "No titles match your search.";
      $("shelves").append(p);
    }
    return;
  }
  const items = view === "movies" ? movies : view === "shows" ? shows : catalog;
  const continuing = items
    .filter((i) => resume(i))
    .sort((a, b) =>
      (b.history_updated_at || record(resume(b))?.updated_at || "").localeCompare(
        a.history_updated_at || record(resume(a))?.updated_at || "",
      ),
    );
  shelf("Continue Watching", continuing);
  shelf(
    "Recently Added",
    [...items]
      .sort((a, b) => (b.date_added || "").localeCompare(a.date_added || ""))
      .slice(0, 20),
  );
  if (view !== "movies") shelf("TV Shows", shows);
  if (view !== "shows") shelf("All Movies", movies);
  const genres = [...new Set(items.flatMap((i) => i.genres || []))].sort();
  genres.forEach((g) =>
    shelf(
      g,
      items.filter((i) => i.genres?.includes(g)),
    ),
  );
  if (!selected || !items.some((i) => i.id === selected.id))
    hero(continuing[0] || items[0]);
}
function openDetails(item) {
  detail = item;
  hero(item);
  $("detail-title").textContent = item.title;
  $("detail-kind").textContent = item.kind === "show" ? "SERIES" : "MOVIE";
  $("detail-meta").textContent = metadata(item);
  $("detail-description").textContent = item.description || item.overview || "";
  $("detail-cast").textContent = Array.isArray(item.cast) && item.cast.length
    ? "Starring: " + item.cast.slice(0, 5).join(", ") : "";
  $("detail-subtitles").textContent = captionLabel(item);
  image($("detail-art"), artwork(item));
  $("detail-play").textContent = item.kind === "show" && resume(item) && !record(resume(item)) ? "Next Episode" : resume(item)
    ? "▶ Resume on TV"
    : item.kind === "show"
      ? "▶ Play first episode"
      : "▶ Play on TV";
  $("restart").hidden = !resume(item);
  $("episodes").hidden = item.kind !== "show";
  if (item.kind === "show") {
    $("season").replaceChildren(
      ...item.seasons.map((s) => new Option(s.title, s.number)),
    );
    const r = resume(item);
    if (r) $("season").value = String(r.season_number);
    renderEpisodes();
  }
  if (!$("details").open) $("details").showModal();
}
function renderEpisodes() {
  const season = detail.seasons.find(
    (s) => String(s.number) === $("season").value,
  );
  $("episode-list").replaceChildren();
  for (const ep of season?.episodes || []) {
    const row = document.createElement("div");
    row.className = "episode";
    const img = document.createElement("img");
    img.alt = "";
    img.loading = "lazy";
    image(img, artwork(ep));
    const text = document.createElement("div");
    text.className = "episode-text";
    const title = document.createElement("p");
    title.className = "episode-title";
    title.textContent = ep.title;
    const info = document.createElement("p");
    info.className = "episode-meta";
    info.textContent = [runtime(ep.duration), captionLabel(ep)]
      .filter(Boolean)
      .join(" · ");
    text.append(title, info);
    if (ep.description && ep.description_scope === "episode") {
      const synopsis = document.createElement("p");
      synopsis.className = "episode-meta";
      synopsis.textContent = ep.description;
      text.append(synopsis);
    }
    const play = document.createElement("button");
    play.textContent = record(ep) ? "Resume" : "Play";
    play.setAttribute("aria-label", `${play.textContent} ${ep.title}`);
    play.onclick = () => playItem(ep);
    row.append(img, text, play);
    $("episode-list").append(row);
  }
}
async function action(path, body) {
  while (busy) await new Promise((resolve) => setTimeout(resolve, 40));
  busy = true;
  document.body.setAttribute("aria-busy", "true");
  const buttons = [...document.querySelectorAll("button")].filter(
    (b) => !b.disabled,
  );
  buttons.forEach((b) => (b.disabled = true));
  $("notice").textContent = "";
  try {
    const result = await api(path, body);
    renderStatus(result);
    return result;
  } catch (error) {
    $("notice").textContent = error.message;
  } finally {
    buttons.forEach((b) => (b.disabled = false));
    busy = false;
    document.body.removeAttribute("aria-busy");
  }
}
async function playItem(item, restart = false) {
  const target = restart ? first(item) : resume(item) || first(item);
  if (!target) return;
  $("details").close();
  const result = await action("/api/cast/play", {
    movie_id: target.id,
    intent: restart ? "restart" : "resume",
    mode: $("playback-mode").value,
  });
  if (result?.active)
    $("remote").scrollIntoView({ behavior: "smooth", block: "start" });
}
function renderStatus(status) {
  tv = status;
  $("connection").textContent =
    `${status.name || "TV"} · ${status.active ? "Playing from your server" : "Ready to cast"}`;
  $("dot").classList.add("online");
  $("remote").hidden = !status.active && !status.still_watching && status.state !== "PREPARING";
  $("remote-link").hidden = $("remote").hidden;
  $("tv-name").textContent = status.name || "YOUR TV";
  $("now-title").textContent = status.title || "Your TV";
  $("state").textContent =
    status.state === "PREPARING"
      ? `${status.preparation_message || "Preparing playback"} (${status.preparation_progress || 0}%)`
      : status.state === "PAUSED"
      ? "Paused"
      : status.state === "BUFFERING"
        ? "Buffering…"
        : status.active
          ? "Playing on TV"
          : "Playback finished";
  $("pause").hidden = !status.active || status.state === "PAUSED";
  $("resume").hidden = status.state !== "PAUSED";
  if (!seeking) {
    $("seek").max = status.duration || 1;
    $("seek").value = status.position || 0;
    $("elapsed").textContent = clock(status.position);
  }
  $("duration").textContent = clock(status.duration);
  $("seek").disabled = !status.duration || !status.active;
  $("autoplay").checked = status.autoplay_enabled !== false;
  const tracks = status.subtitle_tracks || [];
  const signature = JSON.stringify(tracks);
  if ($("captions").dataset.signature !== signature) {
    $("captions").replaceChildren(
      new Option(tracks.length ? "Off" : "No subtitles available", ""),
      ...tracks.map((t) => new Option(t.label, String(t.id))),
    );
    $("captions").dataset.signature = signature;
  }
  $("captions").value = status.subtitle_active
    ? String(status.subtitle_active)
    : "";
  $("captions").disabled = !tracks.length || !status.active;
  const showNext =
    status.active &&
    status.autoplay_enabled !== false &&
    !status.autoplay_suspended &&
    status.next_item &&
    (status.up_next_visible ?? status.remaining <= 30) &&
    !status.still_watching;
  const nextAppeared = showNext && $("up-next").hidden;
  $("up-next").hidden = !showNext;
  if (showNext) {
    $("next-title").textContent = [
      status.next_item.show_title,
      status.next_item.title,
    ]
      .filter(Boolean)
      .join(" · ");
    $("countdown").textContent = `in ${status.remaining}s`;
    if (nextAppeared && !$("details").open)
      $("play-next").focus({ preventScroll: true });
  }
  if (status.still_watching && !$("watching").open) $("watching").showModal();
  else if (!status.still_watching) $("watching").close();
  if (status.preparation_error) $("notice").textContent = status.preparation_error;
  if (status.autoplay_error) $("notice").textContent = status.autoplay_error;
  if (status.idle_reason === "ERROR")
    $("notice").textContent =
      "The TV could not decode this file. Try another title or check the server logs.";
}
async function status() {
  if (polling || busy) return;
  polling = true;
  try {
    renderStatus(await api("/api/cast/status"));
  } catch (error) {
    $("connection").textContent =
      "TV unavailable · Check power and LAN connection";
    $("dot").classList.remove("online");
  } finally {
    polling = false;
  }
}
async function library() {
  try {
    const [items, watched] = await Promise.all([
      api("/api/library/browse"),
      api("/api/history"),
    ]);
    catalog = items;
    history = watched;
    render();
  } catch (error) {
    $("notice").textContent = error.message;
  }
}
for (const button of document.querySelectorAll("[data-view]"))
  button.onclick = () => {
    view = button.dataset.view;
    document.querySelectorAll("[data-view]").forEach((b) => {
      b.classList.toggle("selected", b === button);
      if (b === button) b.setAttribute("aria-current", "page");
      else b.removeAttribute("aria-current");
    });
    render();
    if (view === "search") $("search").focus();
  };
$("search").oninput = render;
$("hero-play").onclick = () => playItem(selected);
$("hero-info").onclick = () => openDetails(selected);
$("close-details").onclick = () => $("details").close();
$("detail-play").onclick = () => playItem(detail);
$("restart").onclick = () => playItem(detail, true);
$("season").onchange = renderEpisodes;
$("refresh").onclick = async () => {
  await library();
  await status();
};
$("remote-link").onclick = () =>
  $("remote").scrollIntoView({ behavior: "smooth" });
for (const name of ["pause", "resume", "stop"])
  $(name).onclick = async () => {
    await action("/api/cast/control", {
      action: name === "resume" ? "play" : name,
    });
    if (name === "stop") await library();
  };
$("seek").oninput = () => {
  seeking = true;
  $("elapsed").textContent = clock(+$("seek").value);
};
$("seek").onchange = async () => {
  await action("/api/cast/control", {
    action: "seek",
    position: +$("seek").value,
  });
  seeking = false;
};
for (const [id, delta] of [
  ["rewind", -10],
  ["forward", 10],
])
  $(id).onclick = () =>
    action("/api/cast/control", {
      action: "seek",
      position: Math.max(
        0,
        Math.min(tv.duration || 0, (tv.position || 0) + delta),
      ),
    });
$("captions").onchange = () =>
  action("/api/cast/captions", {
    track_id: $("captions").value ? +$("captions").value : null,
  });
$("autoplay").onchange = () =>
  action("/api/cast/queue", {
    action: $("autoplay").checked ? "enable" : "disable",
  });
$("play-next").onclick = () => action("/api/cast/queue", { action: "next" });
$("cancel-next").onclick = () =>
  action("/api/cast/queue", { action: "cancel" });
$("confirm-next").onclick = () =>
  action("/api/cast/queue", { action: "confirm" });
$("finish-watching").onclick = () =>
  action("/api/cast/queue", { action: "cancel" });
$("watching").addEventListener("cancel", (e) => {
  e.preventDefault();
  action("/api/cast/queue", { action: "cancel" });
});
setInterval(() => {
  if (document.visibilityState === "visible") status();
}, 2500);
document.addEventListener("visibilitychange", () => {
  if (document.visibilityState === "visible") {
    status();
    library();
  }
});
library();
status();

// Refresh cross-device progress while browsing, without interrupting player controls.
setInterval(() => {
  if (!document.hidden && !busy && !$("details").open && view === "home") library();
}, 30000);
