const fmt = (s) => {
  if (!isFinite(s) || s < 0) s = 0;
  const m = Math.floor(s / 60);
  const r = Math.floor(s % 60);
  return m + ":" + String(r).padStart(2, "0");
};

const startOf = (i) => (i >= 0 && i < CHAPTER.length ? CHAPTER[i].start : null);

function endOf(i) {
  for (let j = i + 1; j < CHAPTER.length; j++) {
    const t = startOf(j);
    if (t != null) return t;
  }
  return isFinite(audio.duration) ? audio.duration : Infinity;
}

function nextPlayable(i) {
  for (let j = i + 1; j < CHAPTER.length; j++) if (startOf(j) != null) return j;
  return -1;
}
