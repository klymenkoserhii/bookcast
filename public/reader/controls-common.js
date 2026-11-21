/** First section that actually has a timestamp. */
function firstTimed() {
  for (let i = 0; i < CHAPTER.length; i++) if (startOf(i) != null) return i;
  return -1;
}

/**
 * Where should Continuous play begin?
 *   1. the card the user selected (playSection keeps this in sync with the
 *      section playing, so "keep going from here" still works)
 *   2. the section playing right now
 *   3. the last section that was played (remembered across reloads)
 *   4. the first timed section
 */
function resumeIndex() {
  if (state.selected != null && startOf(state.selected) != null) return state.selected;
  if (state.playing && state.index != null) return state.index;
  if (state.lastIndex != null && startOf(state.lastIndex) != null) return state.lastIndex;
  return firstTimed();
}

function updateContinuousButton() {
  const on = state.continuous;
  const from = on ? null : resumeIndex();
  const label = on
    ? "⏹ Stop continuous"
    : (from > 0 ? `▶ Continuous from #${from + 1}` : "▶ Continuous play");
  continuousEl.textContent = label;
  continuousEl.title = on
    ? "Stop continuous playback"
    : (from > 0
        ? `Starts at section ${from + 1} — click another card to change the starting point`
        : "Play the chapter continuously from here");
  continuousEl.setAttribute("aria-pressed", String(on));
  continuousEl.classList.toggle("is-on", on);
}

continuousEl.addEventListener("click", () => {
  if (state.continuous) {
    state.continuous = false;
    stop();
    return;
  }
  const from = resumeIndex();
  if (from < 0) return;
  state.continuous = true;
  updateContinuousButton();
  playSection(from);
  scrollToCard(from);
});

/* --- theme ------------------------------------------------------------ */
function applyTheme(theme) {
  document.documentElement.dataset.theme = theme;
  themeEl.textContent = theme === "dark" ? "☀️" : "🌙";
  themeEl.setAttribute("aria-label", theme === "dark" ? "Switch to light mode" : "Switch to dark mode");
  store.set(LS.theme, theme);
}
themeEl.addEventListener("click", () => {
  applyTheme(document.documentElement.dataset.theme === "dark" ? "light" : "dark");
});

/* --- header collapse -------------------------------------------------- */
const topbarEl = document.querySelector("header.topbar");
const collapseEl = document.getElementById("collapse");

/* The anchor offset (--hdr) follows the header height, so it is re-measured
   whenever the header collapses or expands. */
const setHdr = () => document.documentElement.style.setProperty("--hdr", topbarEl.offsetHeight + "px");

function applyCollapsed(collapsed) {
  topbarEl.classList.toggle("is-collapsed", collapsed);
  collapseEl.setAttribute("aria-expanded", String(!collapsed));
  const label = collapsed ? "Expand header" : "Collapse header";
  collapseEl.setAttribute("aria-label", label);
  collapseEl.title = label;
  collapseEl.textContent = collapsed ? "▼" : "▲";
  store.set(LS.collapsed, collapsed ? "1" : "0");
  setHdr();
}
collapseEl.addEventListener("click", () => {
  applyCollapsed(!topbarEl.classList.contains("is-collapsed"));
});

/* --- audio state ------------------------------------------------------ */
function showBanner() { banner.hidden = false; }
loadReaderAudio(audio, AUDIO_URL, showBanner);

audio.addEventListener("error", showBanner);
audio.addEventListener("stalled", () => { if (audio.readyState < 2) showBanner(); });

audio.addEventListener("timeupdate", () => {
  clockEl.textContent = fmt(audio.currentTime) + " / " + fmt(audio.duration);
  // Safety net for background tabs, where requestAnimationFrame is throttled:
  // timeupdate still fires, so section boundaries keep working.
  if (state.playing && state.index != null && audio.currentTime >= state.endAt - 0.03) {
    onSegmentEnd();
  }
});
audio.addEventListener("loadedmetadata", () => {
  clockEl.textContent = fmt(0) + " / " + fmt(audio.duration);
  banner.hidden = true;
  // Some browsers seek before metadata is available; re-sync an active section.
  if (state.playing && state.index != null) audio.currentTime = startOf(state.index);
});
// External pause (media keys, browser UI, OS) resets the card buttons.
// Guard: switching sections calls pause() and play() back-to-back, and the
// queued "pause" event must not cancel the section that just started.
audio.addEventListener("pause", () => {
  if (!audio.paused) return;
  if (state.playing) {
    cancelAnimationFrame(state.raf);
    state.playing = false;
    state.index = null;
    markPlaying();
    if (state.continuous) { state.continuous = false; updateContinuousButton(); }
  }
});

