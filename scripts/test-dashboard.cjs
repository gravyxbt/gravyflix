const { chromium, expect } = require("@playwright/test");
(async () => {
  require("node:fs").mkdirSync(
    require("node:path").join(__dirname, "../dist"),
    { recursive: true },
  );
  const browser = await chromium.launch({ headless: true });
  try {
    const page = await browser.newPage({
      viewport: { width: 1440, height: 1000 },
    });
    const errors = [];
    page.on("pageerror", (e) => errors.push(e.message));
    const root = process.env.WEB_TEST_URL || "http://127.0.0.1:8081";
    let saved = null;
    let choice = null;
    const file = {
      id: 1,
      title: "The Office S01E01",
      filename: "The Office S01E01.mkv",
      file_path: "/media/Shows/The Office/Season 01/The Office S01E01.mkv",
      file_size: 1024 ** 3,
      duration: 1300,
      video_codec: "h264",
      audio_codec: "ac3",
      compatibility_note: "Prepared as AAC stereo for Roku.",
      series_info: { season_number: 1 },
      intro: {
        state: "ready",
        intro: { start: 15, end: 46 },
        note: "Repeated opening confirmed",
      },
      subtitles: {
        state: "ready",
        tracks: [{ description: "English", source: "embedded" }],
      },
    };
    const show = {
      id: "show-office",
      title: "The Office",
      kind: "show",
      season_count: 1,
      episode_count: 1,
      genres: ["Comedy"],
      seasons: [
        {
          title: "Season 1",
          number: 1,
          episodes: [{ id: 1, title: "Pilot", episode_number: 1 }],
        },
      ],
    };
    const movie = {
      ...file,
      id: 2,
      title: "Arrival",
      kind: "movie",
      filename: "Arrival (2016).mp4",
      year: 2016,
      genres: ["Science Fiction"],
      series_info: null,
    };
    const values = {
      MOVIES_DIR: "media/Movies",
      CAST_HOST: "192.0.2.20",
      CAST_NAME: "Living Room",
      AUTO_LIBRARY_SCAN_SECONDS: "300",
      AUTO_ARTWORK: "true",
      AUTO_SUBTITLES: "true",
      AUTO_INTROS: "true",
      SUBTITLE_LANGUAGES: "en",
      SUBTITLE_DAILY_DOWNLOAD_LIMIT: "5",
      ROKU_CACHE_MAX_GB: "50",
      ROKU_VIDEO_ENCODER: "libx264",
      PUBLIC_BASE_URL: "",
    };
    const overview = {
      status: "ok",
      files: 312,
      movies: 82,
      shows: 14,
      missing_files: 0,
      artwork_ready: 94,
      titles: 96,
      subtitles: { ready: 285 },
      intros: { ready: 68 },
      ffmpeg: true,
      ffprobe: true,
      media_directory: "/media/Movies",
      disk_free: 220 * 1024 ** 3,
      disk_total: 1000 * 1024 ** 3,
      cache_bytes: 12 * 1024 ** 3,
      cache_limit: 50 * 1024 ** 3,
      scan_seconds: 300,
    };
    await page.route("**/api/manage/**", async (route) => {
      const req = route.request();
      expect(req.headers()["x-gravyflix-manage"]).toBe("1");
      const endpoint = new URL(req.url()).pathname.replace("/api/manage/", "");
      let body = {};
      if (endpoint === "playback" || endpoint === "playback/export") body = {
        retention_days:7,observation_limits:"Reported states only",cache:{active_jobs:[],reserved_bytes:0,leases:1},
        sessions:[{id:"a".repeat(32),title:"Arrival",state:"playing",client_type:"roku",delivery:"direct",reason:"source_matches_receiver_profile",video_codec:"h264",audio_codec:"aac",position:123,duration:6000,preparation_seconds:0,first_play_seconds:1.2,buffering_seconds:0,updated_at:Date.now()/1000}],events:[]
      };
      else if (endpoint === "overview") body = overview;
      else if (endpoint === "library")
        body = { catalog: [movie, show], files: [file, movie] };
      else if (endpoint === "jobs") body = [];
      else if (endpoint === "artwork")
        body = [
          {
            id: 2,
            title: "Arrival",
            status: "needs_review",
            candidates: [
              {
                title: "Arrival",
                year: 2016,
                url: "https://www.themoviedb.org/movie/329865-arrival",
              },
            ],
          },
        ];
      else if (endpoint === "settings") {
        if (req.method() === "PUT") {
          saved = req.postDataJSON();
          body = {
            saved: true,
            message: "Settings saved. Restart the server to apply them.",
          };
        } else
          body = {
            values,
            saved_key_configured: true,
            environment_overrides: [],
          };
      } else if (endpoint === "artwork/choose") {
        choice = req.postDataJSON();
        body = { id: "x", state: "queued" };
      } else if (endpoint.startsWith("intros/")) body = { state: "ready" };
      else body = { id: "x", state: "queued" };
      await route.fulfill({ json: body });
    });
    await page.goto(root + "/manage");
    await expect(page.locator("#server-state")).toContainText("online");
    await expect(page.locator("#stats")).toContainText("312");
    await page.screenshot({
      path: require("node:path").join(
        __dirname,
        "../dist/dashboard-test-desktop.png",
      ),
      fullPage: true,
    });
    await page
      .getByRole("button", { name: "Media library", exact: true })
      .click();
    await expect(page.locator(".media-card")).toHaveCount(2);
    await page.locator("#library-search").fill("comedy");
    await expect(page.locator(".media-card")).toHaveCount(1);
    await page.locator(".media-card").click();
    await expect(page.getByRole("dialog")).toBeVisible();
    await page
      .getByRole("button", { name: "Episode 1 · Pilot", exact: true })
      .click();
    await expect(page.locator("#file-details")).toContainText("ac3");
    await page.keyboard.press("Escape");
    await expect(page.getByRole("dialog")).not.toBeVisible();
    await page.getByRole("button", { name: /Artwork review/ }).click();
    await page.getByRole("button", { name: "Use this match" }).click();
    expect(choice).toEqual({
      id: "2",
      url: "https://www.themoviedb.org/movie/329865-arrival",
    });
    await page.getByRole("button", { name: "Subtitles", exact: true }).click();
    await expect(page.locator("#subtitle-list")).toContainText("English");
    await page
      .getByRole("button", { name: "Skip intros", exact: true })
      .click();
    await expect(page.locator("#intro-list input")).toHaveCount(2);
    await page.locator("#intro-list input").first().fill("18");
    await page.getByRole("button", { name: "Save timing" }).click();
    await expect(page.locator("#notice")).toContainText("Intro timing saved");
    await page
      .getByRole("button", { name: "Server settings", exact: true })
      .click();
    await page.locator("[name=CAST_NAME]").fill("Bedroom TV");
    await page.locator("[name=opensubtitles_key]").fill("new-secret");
    await page.getByRole("button", { name: "Save settings" }).click();
    await expect(page.locator("#notice")).toContainText("Restart");
    expect(saved.values.CAST_NAME).toBe("Bedroom TV");
    expect(saved.opensubtitles_key).toBe("new-secret");
    await expect(page.locator("[name=opensubtitles_key]")).toHaveValue("");
    await page
      .getByRole("button", { name: "Setup & devices", exact: true })
      .click();
    await page.getByRole("button", { name: "Download Roku app ZIP" }).click();
    await expect(page.locator("#notice")).toContainText("LAN IP");
    await page
      .getByRole("button", { name: "Movie credits", exact: true })
      .click();
    await expect(page.locator("#credit-list .item")).toHaveCount(1);
    await page.locator("#credit-list input").fill("00:20:00");
    await page
      .getByRole("button", { name: "Save credits time", exact: true })
      .click();
    await expect(page.locator("#notice")).toContainText("Credits timing saved");
    await page.getByRole("button", {name:"Playback diagnostics",exact:true}).click();
    await expect(page.locator("#playback-list")).toContainText("Arrival");
    await expect(page.locator("#playback-list")).toContainText("direct");
    const downloadPromise = page.waitForEvent("download");
    await page.getByRole("button", {name:"Download diagnostics",exact:true}).click();
    expect((await downloadPromise).suggestedFilename()).toBe("gravyflix-playback-diagnostics.json");
    await page.setViewportSize({ width: 390, height: 844 });
    await page.getByRole("button", { name: "Overview", exact: true }).click();
    await expect(page.locator("#overview")).toBeVisible();
    await page.screenshot({
      path: require("node:path").join(
        __dirname,
        "../dist/dashboard-test-phone.png",
      ),
      fullPage: true,
    });
    expect(
      await page.evaluate(
        () => document.documentElement.scrollWidth <= innerWidth,
      ),
    ).toBe(true);
    await page
      .getByRole("button", { name: "Server settings", exact: true })
      .click();
    expect(
      await page.evaluate(
        () => document.documentElement.scrollWidth <= innerWidth,
      ),
    ).toBe(true);
    expect(errors).toEqual([]);
    console.log(
      "Dashboard browser tests passed: desktop, phone, library details, artwork approval, settings, intro editing, and setup.",
    );
  } finally {
    await browser.close();
  }
})().catch((error) => {
  console.error(error);
  process.exit(1);
});
