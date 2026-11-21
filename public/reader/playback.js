function clearWord() {
  if (state.wordEl) {
    state.wordEl.classList.remove("is-current");
    state.wordEl = null;
  }
}

function updateWord(i, t) {
  const e = els[i];
  if (!e || !e.words || !e.wordTimes) { clearWord(); return; }
  const times = e.wordTimes;
  let lo = 0, hi = times.length - 1, k = -1;
  while (lo <= hi) {
    const mid = (lo + hi) >> 1;
    if (times[mid][0] <= t) { k = mid; lo = mid + 1; } else { hi = mid - 1; }
  }
  if (k < 0) k = 0;
  const span = e.words[k];
  if (state.wordEl === span) return;
  clearWord();
  span.classList.add("is-current");
  state.wordEl = span;
}

function markPlaying() {
  clearWord();
  els.forEach((e, i) => {
    const on = i === state.index && state.playing;
    e.card.classList.toggle("is-playing", on);
    e.card.classList.toggle("is-selected", i === state.selected);
    e.btn.classList.toggle("is-playing", on);
    e.btn.textContent = on ? "⏸" : "▶";
    e.btn.setAttribute("aria-label", on
      ? "Stop playback of this section"
      : (e.btn.disabled ? "no timestamp" : `Play section ${i + 1}`));
    if (!on) e.card.style.setProperty("--p", "0%");
  });
  // Re-apply the underline at once: without this the next rAF would leave the
  // word unmarked for one frame every time the section changes.
  if (state.playing && state.progress === "word" && state.index != null) {
    updateWord(state.index, audio.currentTime);
  }
}

/** Pick the card that Continuous play should start from. */
function selectCard(i, opts) {
  if (i == null || i < 0 || i >= CHAPTER.length) return;
  state.selected = i;
  focusIndex = i;
  store.set(LS.selected, String(i));
  markPlaying();
  updateContinuousButton();
  if (opts && opts.scroll) scrollToCard(i);
}

function stop(resetButton = true) {
  state.playing = false;
  state.index = null;
  cancelAnimationFrame(state.raf);
  clearWord();
  audio.pause();
  if (resetButton) markPlaying();
  updateContinuousButton();
}

/**
 * Play exactly one section: start[i] … start[i+1] (or end of audio).
 * `continuous` keeps the chain going when the segment ends.
 */
function playSection(i) {
  const start = startOf(i);
  if (start == null) return;

  // Already inside this section and audible: pressing Continuous again (or
  // re-pressing play) must let the audio keep flowing instead of rewinding.
  const resumeInPlace = state.playing && state.index === i;

  state.index = i;
  state.playing = true;
  state.endAt = endOf(i);
  // Remember where the listener is, so Continuous play can resume here later.
  state.selected = i;
  state.lastIndex = i;
  focusIndex = i;
  store.set(LS.last, String(i));
  store.set(LS.selected, String(i));

  audio.playbackRate = state.rate;
  audio.volume = state.volume;

  const begin = () => {
    // Re-assigning currentTime restarts decoding of the segment, which is what
    // made card-to-card playback hiccup. Only seek when we are not already at
    // (or a whisker away from) this section's first word.
    if (!resumeInPlace && Math.abs(audio.currentTime - start) > 0.2) {
      try { audio.currentTime = start; } catch (e) { /* metadata not ready yet */ }
    }
    audio.play().catch(() => {
      state.playing = false;
      markPlaying();
      updateContinuousButton();
      showBanner();
    });
    markPlaying();
    updateContinuousButton();
    tick();
  };

  if (audio.readyState >= 1) begin();
  else audio.addEventListener("loadedmetadata", begin, { once: true });
}

function toggleSection(i) {
  if (state.playing && state.index === i) {
    stop();
    state.continuous = false;
    updateContinuousButton();
    return;
  }
  stop();
  playSection(i);
}

/* rAF ticker: timeupdate only fires ~4×/s, too coarse for segment ends. */
function tick() {
  if (!state.playing || state.index == null) return;
  const i = state.index;
  const t = audio.currentTime;
  const span = Math.max(0.001, state.endAt - startOf(i));
  const pct = Math.min(100, Math.max(0, ((t - startOf(i)) / span) * 100));
  els[i].card.style.setProperty("--p", pct.toFixed(1) + "%");
  if (state.progress === "word") updateWord(i, t);

  if (t >= state.endAt - 0.03) {
    onSegmentEnd();
    return;
  }
  state.raf = requestAnimationFrame(tick);
}

/**
 * Move the "current section" markers to unit i WITHOUT touching the audio.
 * Continuous play calls this at a section boundary: the file never pauses and
 * never re-seeks, so playback is gapless and the highlighted card simply
 * follows whatever the audio is playing.
 */
function advanceSection(i) {
  state.index = i;
  state.playing = true;
  state.endAt = endOf(i);
  // Remember where the listener is, so Continuous play can resume here later.
  state.selected = i;
  state.lastIndex = i;
  focusIndex = i;
  store.set(LS.last, String(i));
  store.set(LS.selected, String(i));
  markPlaying();
  updateContinuousButton();
  scrollToCard(i);
  state.raf = requestAnimationFrame(tick);
}

function onSegmentEnd() {
  // Guard against a late/duplicate call (rAF and timeupdate can both fire).
  if (!state.playing || state.index == null) return;
  if (audio.currentTime < state.endAt - 0.03) return;

  const from = state.index;
  if (state.continuous) {
    // The audio is already running through this boundary: follow it to the
    // next card instead of restarting playback (no pause, no seek, no gap).
    const t = audio.currentTime;
    let nxt = nextPlayable(from);
    // Skip any section whose audio is already behind us (degenerate timestamps).
    while (nxt !== -1 && endOf(nxt) <= t + 0.03) nxt = nextPlayable(nxt);
    if (nxt !== -1 && nxt !== from) {
      advanceSection(nxt);
      return;
    }
  }
  const wasContinuous = state.continuous;
  stop();
  if (wasContinuous) {
    // The chapter finished: forget the resume point so the next start is section 1.
    state.continuous = false;
    state.lastIndex = null;
    state.selected = null;
    store.set(LS.last, "");
    store.set(LS.selected, "");
    markPlaying();
    updateContinuousButton();
  }
}

function scrollToCard(i) {
  const el = els[i] && els[i].card;
  if (el) el.scrollIntoView({ block: "center", behavior: "smooth" });
}

/* ===================================================================== */
