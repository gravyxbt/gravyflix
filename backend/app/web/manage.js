const $ = (id) => document.getElementById(id);
let library = { catalog: [], files: [] },
  currentPage = "overview",
  latestJob = null;
const labels = {
  overview: "Overview",
  playback: "Playback diagnostics",
  library: "Media library",
  artwork: "Artwork review",
  subtitles: "Subtitles",
  intros: "Skip intros",
  credits: "Movie credits",
  settings: "Server settings",
  setup: "Setup & devices",
};
const el = (tag, text, className) => {
  const node = document.createElement(tag);
  if (text !== undefined) node.textContent = text;
  if (className) node.className = className;
  return node;
};
const bytes = (n) => `${(n / 1024 ** 3).toFixed(1)} GB`;
function notice(message, error = false) {
  $("notice").textContent = message;
  $("notice").className = error ? "error" : "";
  $("notice").hidden = false;
}
async function api(path, method = "GET", body) {
  const response = await fetch("/api/manage/" + path, {
    method,
    headers: {
      "X-Gravyflix-Manage": "1",
      ...(body ? { "Content-Type": "application/json" } : {}),
    },
    body: body ? JSON.stringify(body) : undefined,
    cache: "no-store",
  });
  if (!response.ok) {
    let message = `Server request failed (${response.status})`;
    try {
      const data = await response.json();
      message =
        typeof data.detail === "string"
          ? data.detail
          : "Please check the form values.";
    } catch {}
    throw new Error(message);
  }
  return response;
}
async function data(path, method, body) {
  return (await api(path, method, body)).json();
}
async function safely(fn) {
  try {
    await fn();
  } catch (error) {
    notice(error.message, true);
  }
}
function empty(container, text) {
  container.append(el("p", text, "empty"));
}
function status(value) {
  return el(
    "span",
    (value || "pending").replaceAll("_", " "),
    "state " + (value || "pending"),
  );
}
function row(title) {
  const node = el("article", undefined, "item");
  node.append(el("h3", title));
  return node;
}
function button(text, action) {
  const node = el("button", text);
  node.type = "button";
  node.addEventListener("click", () => safely(action));
  return node;
}
function details(container, entries) {
  container.replaceChildren();
  for (const [key, value] of entries) {
    container.append(el("dt", key), el("dd", String(value)));
  }
}
async function overview() {
  const o = await data("overview");
  $("server-state").textContent = "● Server online";
  $("updated").textContent =
    "Updated " +
    new Date().toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });
  $("stats").replaceChildren();
  for (const [name, count, note] of [
    ["Movies", o.movies, "Ready to browse"],
    ["Shows", o.shows, "Grouped by series"],
    ["Media files", o.files, "Movies + episodes + extras"],
    [
      "Artwork",
      `${o.artwork_ready}/${o.titles}`,
      "Titles with matched artwork",
    ],
  ]) {
    const card = el("article", undefined, "stat");
    card.append(
      el("span", name),
      el("strong", String(count)),
      el("small", note),
    );
    $("stats").append(card);
  }
  details($("server-details"), [
    ["Media folder", o.media_directory],
    ["Free space", `${bytes(o.disk_free)} of ${bytes(o.disk_total)}`],
    ["Playback cache", `${bytes(o.cache_bytes)} / ${bytes(o.cache_limit)}`],
    ["Automatic scan interval", `${o.scan_seconds} seconds`],
    [
      "Media tools",
      `FFmpeg: ${o.ffmpeg ? "ready" : "missing"} · ffprobe: ${o.ffprobe ? "ready" : "missing"}`,
    ],
    ["Missing files", o.missing_files + " hidden from the library"],
  ]);
  $("service-details").replaceChildren();
  for (const [name, text] of [
    ["Artwork", `${o.artwork_ready} titles matched`],
    ["Subtitles", `${o.subtitles.ready || 0} files with ready tracks`],
    ["Skip intro", `${o.intros.ready || 0} files with intro markers`],
  ]) {
    const entry = el("div", undefined, "service");
    entry.append(el("span", name), el("strong", text));
    $("service-details").append(entry);
  }
  $("setup-media").textContent = o.media_directory;
  $("setup-url").textContent = location.origin;
}
async function loadLibrary() {
  library = await data("library");
  renderLibrary();
  renderSubtitles();
  renderIntros();
  renderCredits();
}
function renderLibrary() {
  const query = $("library-search").value.toLowerCase();
  const container = $("library-list");
  container.replaceChildren();
  const titles = library.catalog.filter((i) =>
    [i.title, ...(i.genres || [])].join(" ").toLowerCase().includes(query),
  );
  for (const item of titles) {
    const card = button("", () => showItem(item));
    card.className = "media-card";
    const art = el("img");
    art.src = item.landscape_url || item.backdrop_url || "/web/assets/card.png";
    art.loading = "lazy";
    art.alt = "";
    art.onerror = () => {
      art.onerror = null;
      art.src = "/web/assets/card.png";
    };
    const copy = el("div", undefined, "card-copy");
    copy.append(
      el("strong", item.title),
      el(
        "small",
        item.kind === "show"
          ? `${item.season_count} seasons · ${item.episode_count} episodes`
          : `Movie${item.year ? " · " + item.year : ""}`,
      ),
      el("small", (item.genres || []).join(" · ") || "Genres pending"),
    );
    card.append(art, copy);
    container.append(card);
  }
  if (!titles.length)
    empty(
      container,
      query
        ? "No matching titles."
        : "Your library is empty. Add files to the media folder and scan.",
    );
}
function showItem(item) {
  $("file-title").textContent = item.title;
  $("file-details").replaceChildren();
  if (item.kind === "show") {
    for (const season of item.seasons) {
      $("file-details").append(el("h3", season.title));
      for (const ep of season.episodes) {
        const file = library.files.find((f) => f.id === ep.id);
        $("file-details").append(
          button(
            `Episode ${ep.episode_number} · ${ep.title || ep.filename}`,
            () => showFile(file),
          ),
        );
        $("file-details").lastChild.className = "episode-button";
      }
    }
  } else
    showFile(
      library.files.find((f) => f.id === item.id),
      false,
    );
  $("file-dialog").showModal();
}
function showFile(file, open = true) {
  if (!file) return;
  $("file-title").textContent = file.title;
  const dl = el("dl");
  const mins = file.duration
    ? Math.round(file.duration / 60) + " minutes"
    : "Not available";
  details(dl, [
    ["Filename", file.filename],
    ["Server path", file.file_path],
    ["Runtime", mins],
    ["Size", bytes(file.file_size)],
    [
      "Video / audio",
      `${file.video_codec || "unknown"} / ${file.audio_codec || "unknown"}`,
    ],
    ["Roku compatibility", file.compatibility_note],
    [
      "Subtitles",
      `${file.subtitles.tracks.length} ready tracks · ${file.subtitles.state}`,
    ],
    [
      "Intro",
      file.intro.intro
        ? `${file.intro.intro.start.toFixed(1)}–${file.intro.intro.end.toFixed(1)} seconds`
        : file.intro.note,
    ],
  ]);
  $("file-details").replaceChildren(dl);
  if (open && !$("file-dialog").open) $("file-dialog").showModal();
}
async function renderArtwork() {
  const reports = await data("artwork");
  $("review-count").textContent = reports.length || "";
  const container = $("artwork-list");
  container.replaceChildren();
  for (const report of reports) {
    const article = row(report.title);
    article.append(status(report.status));
    if (report.error) article.append(el("p", report.error));
    for (const candidate of report.candidates || []) {
      const line = el("div", undefined, "candidate");
      const copy = el("div");
      copy.append(
        el(
          "strong",
          candidate.title + (candidate.year ? " (" + candidate.year + ")" : ""),
        ),
      );
      const link = el("a", "View source ↗");
      try {
        const url = new URL(candidate.url);
        if (
          url.protocol === "https:" &&
          url.hostname === "www.themoviedb.org"
        ) {
          link.href = url.href;
          link.target = "_blank";
          link.rel = "noopener noreferrer";
          copy.append(el("br"), link);
        }
      } catch {}
      line.append(
        copy,
        button("Use this match", async () => {
          await startJob("artwork/choose", {
            id: String(report.id),
            url: candidate.url,
          });
        }),
      );
      article.append(line);
    }
    container.append(article);
  }
  if (!reports.length)
    empty(
      container,
      "No artwork matches need review. New ambiguous titles will appear here automatically.",
    );
}
function filteredFiles(input) {
  const query = $(input).value.toLowerCase();
  return library.files.filter((f) =>
    (f.title + " " + f.filename).toLowerCase().includes(query),
  );
}
function renderSubtitles() {
  const container = $("subtitle-list");
  container.replaceChildren();
  for (const file of filteredFiles("subtitles-search")) {
    const article = row(file.filename);
    article.append(status(file.subtitles.state));
    const tracks = file.subtitles.tracks;
    article.append(
      el(
        "p",
        tracks.length
          ? tracks.map((t) => `${t.description} · ${t.source}`).join(" / ")
          : file.subtitles.note || "Waiting for subtitle discovery.",
      ),
    );
    container.append(article);
  }
  if (!container.children.length) empty(container, "No matching media files.");
}
function renderIntros() {
  const container = $("intro-list");
  container.replaceChildren();
  for (const file of filteredFiles("intros-search").filter(
    (f) => f.series_info || f.grouping_hint,
  )) {
    const article = row(file.filename);
    article.append(status(file.intro.state), el("p", file.intro.note));
    const form = el("form", undefined, "inline-form");
    const fields = {};
    for (const name of ["start", "end"]) {
      const label = el(
        "label",
        (name === "start" ? "Start" : "End") + " (seconds)",
      );
      const input = el("input");
      input.type = "number";
      input.min = "0";
      input.step = "0.1";
      input.required = true;
      input.value = file.intro.intro?.[name]?.toFixed(1) || "";
      label.append(input);
      form.append(label);
      fields[name] = input;
    }
    const save = el("button", "Save timing");
    save.type = "submit";
    form.append(
      save,
      button("Disable for this file", async () => {
        await data("intros/" + file.id, "PUT", { disabled: true });
        await loadLibrary();
        notice("Intro skipping disabled for this episode.");
      }),
    );
    form.addEventListener("submit", (event) => {
      event.preventDefault();
      safely(async () => {
        await data("intros/" + file.id, "PUT", {
          start: Number(fields.start.value),
          end: Number(fields.end.value),
        });
        await loadLibrary();
        notice("Intro timing saved. It will apply on the next playback.");
      });
    });
    article.append(form);
    container.append(article);
  }
  if (!container.children.length)
    empty(
      container,
      "No matching episodes. Add a series to review its intros.",
    );
}
const settingDefinitions = [
  [
    "AUTO_VISUAL_CREDITS",
    "Automatic visual credits recognition",
    "boolean",
    "Analyze small movie-ending samples locally when credit chapters are missing.",
  ],
  [
    "AUTO_CREDITS",
    "Automatic movie credits",
    "boolean",
    "Enable the credits background worker. User-reviewed times take priority.",
  ],
  [
    "MOVIES_DIR",
    "Media folder",
    "text",
    "An existing folder on the server. Relative paths start at the project directory.",
  ],
  [
    "AUTO_LIBRARY_SCAN_SECONDS",
    "Scan interval (seconds)",
    "number",
    "Default: 300. The automatic scan runs with the artwork worker enabled.",
  ],
  [
    "CAST_HOST",
    "Vizio / Cast TV address",
    "text",
    "TV IP or hostname, for example 192.0.2.20. Leave blank if you only use Roku.",
  ],
  ["CAST_NAME", "TV name", "text", "A friendly name for the phone remote."],
  [
    "ROKU_CACHE_MAX_GB",
    "Playback cache limit (GB)",
    "number",
    "Converted playback copies. Your original media remains untouched.",
  ],
  [
    "ROKU_VIDEO_ENCODER",
    "Video encoder",
    "select",
    "Use NVIDIA only after verifying NVENC support on this server.",
  ],
  [
    "SUBTITLE_LANGUAGES",
    "Subtitle languages",
    "text",
    "Comma-separated codes, for example en,es.",
  ],
  [
    "SUBTITLE_DAILY_DOWNLOAD_LIMIT",
    "Daily subtitle download budget",
    "number",
    "Default: 5. Your provider account may enforce a lower limit.",
  ],
  [
    "PUBLIC_BASE_URL",
    "Server URL override (optional)",
    "text",
    "Normally blank: clients use the address they connect to.",
  ],
  [
    "AUTO_ARTWORK",
    "Automatic scanning & artwork",
    "boolean",
    "Find new files and fetch artwork from public sources.",
  ],
  [
    "AUTO_SUBTITLES",
    "Automatic subtitles",
    "boolean",
    "Extract text captions and look for matching downloads.",
  ],
  [
    "AUTO_INTROS",
    "Automatic intro detection",
    "boolean",
    "Find repeated openings across episodes.",
  ],
];
async function loadSettings() {
  const settings = await data("settings");
  const container = $("setting-fields");
  container.replaceChildren();
  for (const [key, title, type, help] of settingDefinitions) {
    const label = el("label", title);
    let input;
    if (type === "select") {
      input = el("select");
      for (const value of ["libx264", "h264_nvenc"]) {
        const option = el(
          "option",
          value === "libx264"
            ? "CPU · libx264 (recommended)"
            : "NVIDIA · h264_nvenc",
        );
        option.value = value;
        input.append(option);
      }
    } else {
      input = el("input");
      input.type = type === "boolean" ? "checkbox" : type;
    }
    input.name = key;
    if (type === "boolean") input.checked = settings.values[key] === "true";
    else input.value = settings.values[key];
    if (type === "number") {
      input.min = key === "AUTO_LIBRARY_SCAN_SECONDS" ? 10 : 1;
      input.max =
        key === "ROKU_CACHE_MAX_GB"
          ? 10000
          : key === "AUTO_LIBRARY_SCAN_SECONDS"
            ? 86400
            : 100;
      input.step = 1;
    }
    label.append(input, el("small", help));
    container.append(label);
  }
  $("key-status").textContent = settings.saved_key_configured
    ? "· A key is saved"
    : "· No key saved";
  if (settings.environment_overrides.length)
    notice(
      "These process environment variables override saved settings: " +
        settings.environment_overrides.join(", "),
      true,
    );
}
$("settings-form").addEventListener("submit", (event) => {
  event.preventDefault();
  safely(async () => {
    const values = {};
    for (const [key, , ,] of settingDefinitions) {
      const input = $("settings-form").elements.namedItem(key);
      values[key] =
        input.type === "checkbox" ? String(input.checked) : input.value.trim();
    }
    const result = await data("settings", "PUT", {
      values,
      opensubtitles_key:
        $("settings-form")
          .elements.namedItem("opensubtitles_key")
          .value.trim() || null,
    });
    $("settings-form").elements.namedItem("opensubtitles_key").value = "";
    await loadSettings();
    notice(result.message);
    $("restart-panel").scrollIntoView({ behavior: "smooth", block: "center" });
  });
});
async function startJob(path, body) {
  const job = await data(path, "POST", body);
  latestJob = job.id;
  await pollJobs();
}
for (const btn of document.querySelectorAll("[data-action]"))
  btn.addEventListener("click", () =>
    safely(() => startJob(btn.dataset.action)),
  );
async function pollJobs() {
  const jobs = await data("jobs");
  $("server-state").textContent = "● Server online";
  const job = jobs[0];
  const busy = job && ["queued", "running"].includes(job.state);
  document
    .querySelectorAll("[data-action]")
    .forEach((btn) => (btn.disabled = !!busy));
  if (job) {
    $("job").hidden = false;
    $("job").textContent = `${job.label} · ${job.state} · ${job.message}`;
    if (latestJob === job.id && !busy) {
      latestJob = null;
      await Promise.all([overview(), loadLibrary(), renderArtwork()]);
      if (job.state === "error") notice(job.message, true);
    }
  }
}
async function changePage(name) {
  if (!labels[name]) name = "overview";
  currentPage = name;
  document
    .querySelectorAll(".page")
    .forEach((section) => (section.hidden = section.id !== name));
  document.querySelectorAll("[data-page]").forEach((btn) => {
    if (btn.dataset.page === name) btn.setAttribute("aria-current", "page");
    else btn.removeAttribute("aria-current");
  });
  $("page-title").textContent = labels[name];
  if (name === "playback") await loadPlayback();
  if (name === "settings") await loadSettings();
  if (["library", "subtitles", "intros", "credits"].includes(name))
    await loadLibrary();
  if (name === "artwork") await renderArtwork();
  if (["overview", "setup"].includes(name)) await overview();
}
for (const btn of document.querySelectorAll("[data-page]"))
  btn.addEventListener("click", () => {
    location.hash = btn.dataset.page;
  });
window.addEventListener("hashchange", () =>
  safely(() => changePage(location.hash.slice(1))),
);
$("library-search").addEventListener("input", renderLibrary);
$("subtitles-search").addEventListener("input", renderSubtitles);
$("intros-search").addEventListener("input", renderIntros);
$("credits-search").addEventListener("input", renderCredits);
$("close-dialog").addEventListener("click", () => $("file-dialog").close());
$("download-roku").addEventListener("click", () =>
  safely(async () => {
    if (
      ["localhost", "127.0.0.1", "::1", "[::1]"].includes(location.hostname)
    ) {
      throw new Error(
        "Open the dashboard using the server’s LAN IP before downloading. A Roku cannot connect to localhost.",
      );
    }
    const response = await api("roku-package");
    const url = URL.createObjectURL(await response.blob());
    const link = el("a");
    link.href = url;
    link.download = "gravyflix-roku.zip";
    document.body.append(link);
    link.click();
    link.remove();
    setTimeout(() => URL.revokeObjectURL(url), 10000);
    notice("Roku package downloaded, configured for " + location.origin + ".");
  }),
);
await safely(async () => {
  await Promise.all([overview(), renderArtwork()]);
  await changePage(location.hash.slice(1) || "overview");
  await pollJobs();
});
setInterval(() => {
  if (document.hidden) return;
  pollJobs().catch(() => {
    $("server-state").textContent = "Server unavailable";
  });
}, 4000);

function creditClock(seconds) {
  const value = Math.floor(seconds);
  return [Math.floor(value / 3600), Math.floor(value / 60) % 60, value % 60]
    .map((n) => String(n).padStart(2, "0"))
    .join(":");
}
function parseCreditTime(value) {
  if (/^\d+(?:\.\d+)?$/.test(value)) return Number(value);
  if (!/^\d+:[0-5]\d:[0-5]\d(?:\.\d+)?$/.test(value))
    throw new Error(
      "Enter HH:MM:SS, such as 01:41:32, or a number of seconds.",
    );
  const parts = value.split(":").map(Number);
  return parts[0] * 3600 + parts[1] * 60 + parts[2];
}
function renderCredits() {
  const container = $("credit-list");
  container.replaceChildren();
  const ids = new Set(
    library.catalog.filter((i) => i.kind === "movie").map((i) => i.id),
  );
  for (const file of filteredFiles("credits-search").filter((f) =>
    ids.has(f.id),
  )) {
    const credit = file.credits || {
      state: "pending",
      start: null,
      note: "Credits have not been checked yet",
    };
    const article = row(file.title);
    article.append(
      status(credit.state),
      el("p", file.filename),
      el("p", credit.note),
    );
    const form = el("form", undefined, "inline-form");
    const label = el("label", "Credits start");
    label.style.width = "160px";
    const input = el("input");
    input.type = "text";
    input.placeholder = "01:41:32";
    input.required = true;
    input.value = credit.start === null ? "" : creditClock(credit.start);
    label.append(input);
    form.append(label);
    const save = el("button", "Save credits time");
    save.type = "submit";
    form.append(
      save,
      button("Use final 30 seconds", async () => {
        await data("credits/" + file.id, "PUT", { disabled: true });
        await loadLibrary();
        notice("This movie will use the final 30-second prompt.");
      }),
    );
    form.addEventListener("submit", (event) => {
      event.preventDefault();
      safely(async () => {
        const start = parseCreditTime(input.value.trim());
        await data("credits/" + file.id, "PUT", { start });
        await loadLibrary();
        notice(
          "Credits timing saved. Up next will appear here on the next playback.",
        );
      });
    });
    if (credit.method)
      article.append(
        el(
          "p",
          "Source: " +
            credit.method +
            (credit.start !== null ? " · " + creditClock(credit.start) : ""),
          "muted",
        ),
      );
    article.append(form);
    container.append(article);
  }
  if (!container.children.length)
    empty(
      container,
      "No matching movies. Series use their existing autoplay timing.",
    );
}

setInterval(() => {
  if (
    !document.hidden &&
    currentPage === "credits" &&
    !document.activeElement?.closest("#credit-list")
  )
    safely(loadLibrary);
}, 15000);

async function loadPlayback() {
  const report = await data("playback");
  const container = $("playback-list");
  container.replaceChildren();
  $("playback-summary").textContent = `${report.cache.active_jobs.length} conversions running or queued · ${bytes(report.cache.reserved_bytes)} reserved · ${report.cache.leases} cache leases. History diagnostics kept for ${report.retention_days} days.`;
  $("playback-limits").textContent = report.observation_limits;
  for (const session of report.sessions) {
    const article = row(session.title || "Unavailable title");
    article.append(status(session.state));
    const details = el("dl");
    for (const [label, value] of [
      ["Device", session.client_type === "roku" ? "Roku" : "Vizio / Cast"],
      ["Delivery", session.delivery || "Not selected yet"],
      ["Reason", (session.reason || "Waiting for playback").replaceAll("_", " ")],
      ["Source", `${session.video_codec || "Unknown video"} / ${session.audio_codec || "No audio"}`],
      ["Position", `${Math.round(session.position)} / ${Math.round(session.duration)} seconds`],
      ["Preparation", session.preparation_seconds == null ? "Not reported" : `${session.preparation_seconds.toFixed(1)}s`],
      ["Time to playing", session.first_play_seconds == null ? "Not confirmed" : `${session.first_play_seconds.toFixed(1)}s`],
      ["Reported buffering", `${session.buffering_seconds.toFixed(1)}s`],
      ["Updated", new Date(session.updated_at * 1000).toLocaleString()],
      ["Session", session.id],
    ]) details.append(el("dt", label), el("dd", value));
    article.append(details);
    const timeline = report.events.filter(e => e.session_id === session.id).slice(0, 12).reverse();
    if (timeline.length) article.append(el("p", timeline.map(e => `${e.event} @ ${Math.round(e.position)}s`).join(" → "), "muted"));
    container.append(article);
  }
  if (!report.sessions.length) empty(container, "Play a title on Roku or cast to your TV to see playback diagnostics here.");
}
$("playback-export").addEventListener("click", () => safely(async () => {
  const response = await api("playback/export");
  const url = URL.createObjectURL(await response.blob());
  const link = el("a"); link.href = url; link.download = "gravyflix-playback-diagnostics.json"; link.click();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}));
setInterval(() => { if (!document.hidden && currentPage === "playback") safely(loadPlayback); }, 5000);
