(function boot() {
  // Theme: stored preference, else system.
  const stored = store.get(LS.theme);
  applyTheme(stored || (matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "light"));

  // Volume / rate preferences.
  const v = store.get(LS.volume);
  if (v != null) { volumeEl.value = v; volumeOut.textContent = v + "%"; state.volume = Number(v) / 100; }
  // The slider owns the allowed values now: clamp an old stored preference
  // (0.75/1.25 from the previous dropdown) onto the 0.5–1.0, 0.1 grid.
  const rawRate = store.get(LS.rate);
  const r = rawRate == null ? NaN : Number(rawRate);
  if (Number.isFinite(r)) {
    rateEl.value = String(Math.min(1, Math.max(0.5, Math.round(r * 10) / 10)));
    if (rateEl.value !== rawRate) store.set(LS.rate, rateEl.value);
  }
  state.rate = Number(rateEl.value);
  rateOut.textContent = fmtRate(state.rate);
  audio.volume = state.volume;

  render();

  // Progress display mode: shared across chapters, word mode needs timings.
  // Word underline is the default; an explicit stored choice always wins.
  progressCtl.hidden = !HAS_WORD_TIMES;
  document.getElementById("progressHelp").hidden = !HAS_WORD_TIMES;
  const storedProgress = store.get(LS.progress);
  setProgressMode(HAS_WORD_TIMES && storedProgress !== "section" ? "word" : "section");

  // Resume point: last played section, else last selected card (survives reload).
  const asIndex = (raw) => {
    if (raw == null || raw === "") return null;
    const n = Number(raw);
    return Number.isInteger(n) && n >= 0 && n < CHAPTER.length ? n : null;
  };
  const sel = asIndex(store.get(LS.selected));
  const last = asIndex(store.get(LS.last));
  if (sel != null) { state.selected = sel; focusIndex = sel; }
  if (last != null) state.lastIndex = last;

  markPlaying();
  updateContinuousButton();

  // Restore the collapsed/expanded header choice, then measure the sticky
  // header (it wraps taller on narrow screens) for the anchor offset.
  applyCollapsed(store.get(LS.collapsed) === "1");
  setHdr(); addEventListener("resize", setHdr);

  // Deep link (#u-N from a vocabulary page or the index): select and show that card.
  const hit = /^#u-(\d+)$/.exec(location.hash);
  if (hit) selectCard(Number(hit[1]) - 1, { scroll: true });
})();
