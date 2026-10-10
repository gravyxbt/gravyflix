const { chromium, expect } = require("@playwright/test");
(async () => {
  const browser = await chromium.launch({ headless: true });
  try {
    const page = await browser.newPage({
      viewport: { width: 390, height: 844 },
      isMobile: true,
      hasTouch: true,
    });
    const errors = [];
    page.on("pageerror", (e) => errors.push(e.message));
    const summary = {
      has_full: true,
      languages: ["eng"],
      count: 1,
      state: "ready",
    };
    const ep = (id, n) => ({
      id,
      kind: "episode",
      title: "Episode " + n,
      show_title: "Rick and Morty",
      season_number: 1,
      episode_number: n,
      duration: 1300,
      subtitle_summary: summary,
    });
    const library = [
      {
        id: 1,
        kind: "movie",
        title: "Obsession",
        year: 2026,
        duration: 6600,
        genres: ["Horror"],
        date_added: "2026-10-01",
        subtitle_summary: summary,
      },
      {
        id: "show-rick",
        kind: "show",
        title: "Rick and Morty",
        genres: ["Comedy", "Animation"],
        episode_count: 2,
        season_count: 1,
        date_added: "2026-09-30",
        subtitle_summary: { episodes_available: 2, episode_total: 2 },
        seasons: [
          { number: 1, title: "Season 1", episodes: [ep(2, 1), ep(3, 2)] },
        ],
      },
    ];
    let state = {
      name: "Living Room",
      connected: true,
      state: "IDLE",
      active: false,
      position: 0,
      duration: 6600,
      autoplay_enabled: true,
      subtitle_tracks: [],
      subtitle_active: null,
    };
    const commands = [];
    await page.route("**/api/library/browse", (r) =>
      r.fulfill({ json: library }),
    );
    await page.route("**/api/history", r => r.fulfill({json:[{movie_id:1,position:200,duration:6600,completed:0,updated_at:"2026-10-01"}]}));
    await page.route("**/api/cast/**", async (r) => {
      const req = r.request(),
        url = req.url();
      if (url.endsWith("/history"))
        return r.fulfill({
          json: [
            {
              movie_id: 1,
              position: 200,
              duration: 6600,
              completed: 0,
              updated_at: "2026-10-01",
            },
          ],
        });
      if (req.method() === "POST") {
        const b = req.postDataJSON();
        commands.push(b);
        expect(req.headers()["x-media-control"]).toBe("1");
        if (b.movie_id)
          state = {
            ...state,
            active: true,
            state: "PLAYING",
            movie_id: b.movie_id,
            title: "Obsession",
            subtitle_tracks: [{ id: 1, label: "English" }],
          };
        if (b.action === "pause") state.state = "PAUSED";
        if (b.action === "play") state.state = "PLAYING";
        if (b.action === "seek") state.position = b.position;
        if (b.action === "stop")
          state = { ...state, active: false, state: "IDLE" };
        if (url.endsWith("/captions")) state.subtitle_active = b.track_id;
        if (b.action === "confirm") state.still_watching = false;
        if (b.action === "cancel")
          state = { ...state, autoplay_suspended: true, still_watching: false };
      }
      await r.fulfill({ json: state });
    });
    await page.goto(process.env.WEB_TEST_URL || "http://127.0.0.1:8081");
    await expect(page.locator("#hero-title")).toHaveText("Obsession");
    await expect(
      page.getByRole("heading", { name: "Continue Watching" }),
    ).toBeVisible();
    expect(
      await page.evaluate(
        () => document.documentElement.scrollWidth <= innerWidth,
      ),
    ).toBe(true);
    await page.getByRole("button", { name: "Shows", exact: true }).click();
    await page.locator(".card").first().click();
    await expect(page.locator("#details")).toBeVisible();
    await expect(page.locator(".episode")).toHaveCount(2);
    await page.locator("#playback-mode").selectOption("compatible");
    await expect(page.locator("#detail-subtitles")).toContainText("2 of 2");
    await page.getByRole("button", { name: "Close details" }).click();
    await page.getByRole("button", { name: "Search", exact: true }).click();
    await page.locator("#search").fill("Horror");
    await expect(page.locator(".card")).toHaveCount(1);
    await page.locator("#search").fill("nothing-matches");
    await expect(page.locator("#shelves")).toContainText("No titles match");
    await page.getByRole("button", { name: "Movies", exact: true }).click();
    await page.getByRole("button", { name: "Home", exact: true }).click();
    await page.locator("#hero-play").click();
    await expect(page.locator("#remote")).toBeVisible();
    expect(commands.find((x) => x.movie_id)?.intent).toBe("resume");
    expect(commands.find((x) => x.movie_id)?.mode).toBe("compatible");
    await page.getByRole("button", { name: "Pause", exact: true }).click();
    await expect(page.locator("#state")).toHaveText("Paused");
    await page.getByRole("button", { name: "Resume", exact: true }).click();
    await page.locator("#seek").fill("500");
    await page.locator("#seek").dispatchEvent("change");
    await expect
      .poll(() => commands.some((c) => c.position === 500))
      .toBe(true);
    await page.locator("#captions").selectOption("1");
    await expect.poll(() => commands.some((c) => c.track_id === 1)).toBe(true);
    state = {
      ...state,
      remaining: 20,
      next_item: { id: 3, title: "Episode 2", show_title: "Rick and Morty" },
    };
    await expect(page.locator("#up-next")).toBeVisible({ timeout: 6000 });
    state.remaining = 700;
    state.up_next_visible = true;
    await expect(page.locator("#countdown")).toContainText("700", {
      timeout: 6000,
    });
    await expect(page.locator("#up-next")).toBeVisible();
    state.up_next_visible = false;
    await expect(page.locator("#up-next")).toBeHidden({ timeout: 6000 });
    state.up_next_visible = true;
    await expect(page.locator("#up-next")).toBeVisible({ timeout: 6000 });
    await page.locator("#cancel-next").click();
    await expect(page.locator("#up-next")).toBeHidden();
    state = { ...state, still_watching: true };
    await expect(page.locator("#watching")).toBeVisible({ timeout: 6000 });
    await page.locator("#confirm-next").click();
    await expect(page.locator("#watching")).toBeHidden();
    await page.locator("#stop").click();
    await expect(page.locator("#remote")).toBeHidden();
    await page.screenshot({ path: "dist/web-test-phone.png" });
    await page.setViewportSize({ width: 1440, height: 1000 });
    await page.screenshot({ path: "dist/web-test-desktop.png" });
    await page.route("**/api/cast/play", (r) =>
      r.fulfill({ status: 503, json: { detail: "TV unavailable" } }),
    );
    await page.locator("#hero-play").click();
    await expect(page.locator("#notice")).toHaveText("TV unavailable");
    expect(errors).toEqual([]);
    console.log(
      "Web tests passed: phone/desktop, series, genres, search, resume, cast, pause, seek, captions, countdown, confirmation and errors.",
    );
  } finally {
    await browser.close();
  }
})().catch((e) => {
  console.error(e);
  process.exit(1);
});
