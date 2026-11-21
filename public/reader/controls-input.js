/* Speed label: "1×" at the top of the range, "0.9×" below it. */
function fmtRate(r) {
  return (Math.round(r * 10) / 10) + "×";
}

volumeEl.addEventListener("input", () => {
  state.volume = Number(volumeEl.value) / 100;
  audio.volume = state.volume;
  volumeOut.textContent = volumeEl.value + "%";
  store.set(LS.volume, volumeEl.value);
});

rateEl.addEventListener("input", () => {
  state.rate = Number(rateEl.value);
  audio.playbackRate = state.rate;
  rateOut.textContent = fmtRate(state.rate);
  store.set(LS.rate, rateEl.value);
});

/* --- progress display mode -------------------------------------------- */
function setProgressMode(mode) {
  if (mode !== "word" || HAS_WORD_TIMES) state.progress = mode;
  progressEl.value = state.progress;
  document.documentElement.dataset.progress = state.progress;
  store.set(LS.progress, state.progress);
  if (state.progress !== "word") clearWord();
}

progressEl.addEventListener("change", () => setProgressMode(progressEl.value));

