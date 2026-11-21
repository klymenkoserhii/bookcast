const audio = document.getElementById("audio");
const cardsEl = document.getElementById("cards");
const banner = document.getElementById("audioBanner");
const clockEl = document.getElementById("clock");
const statsEl = document.getElementById("stats");
const volumeEl = document.getElementById("volume");
const volumeOut = document.getElementById("volumeOut");
const rateEl = document.getElementById("rate");
const rateOut = document.getElementById("rateOut");
const continuousEl = document.getElementById("continuous");
const themeEl = document.getElementById("theme");
const progressEl = document.getElementById("progress");
const progressCtl = document.getElementById("progressCtl");
let footnoteTooltipIndex = 0;


// Theme, volume and speed are shared by every chapter. The reading position is NOT:
// "selected" and "last" are scoped to this page, otherwise a new chapter would open with
// the previous chapter's section number selected.
const PAGE = location.pathname;
const LS = { theme: "reader.theme", volume: "reader.volume", rate: "reader.rate",
             collapsed: "reader.collapsed",
             progress: "reader.progress",
             selected: "reader.selected:" + PAGE, last: "reader.last:" + PAGE };


const state = {
  index: null,        // unit currently playing (or null)
  playing: false,
  continuous: false,
  endAt: 0,           // hard stop time of the current segment
  raf: 0,
  rate: 1,
  volume: 1,
  enOpen: false,
  uaOpen: false,
  progress: "section", // progress display mode: "section" hairline or "word" underline
  wordEl: null,        // <span class="w"> currently underlined
  selected: null,     // card picked as the next starting point
  lastIndex: null,    // last section that was actually played
};

/* Word timings exist only when the chapter was built from an alignment sidecar
   that carries the ASR word stream. */
const HAS_WORD_TIMES = Array.isArray(WORD_TIMES) && WORD_TIMES.some((u) => u && u.length);

// CHAPTER[i].start comes from AUDIO_TIMES; keep one source of truth.
CHAPTER.forEach((u, i) => {
  const t = AUDIO_TIMES[i];
  u.start = (typeof t === "number" && isFinite(t)) ? t : null;
});

const els = []; // per-card DOM references, filled in render()
