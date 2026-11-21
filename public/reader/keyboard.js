let focusIndex = 0;
document.addEventListener("keydown", (ev) => {
  const tag = (ev.target.tagName || "").toLowerCase();
  if (tag === "input" || tag === "select" || tag === "textarea") return;
  if (ev.metaKey || ev.ctrlKey || ev.altKey) return;

  const onButton = !!(ev.target.closest && ev.target.closest("button"));
  if (ev.code === "Space" || (ev.code === "Enter" && !onButton)) {
    ev.preventDefault();
    const i = state.index != null ? state.index : focusIndex;
    if (startOf(i) != null) toggleSection(i);
  } else if (ev.key === "ArrowDown" || ev.key === "j") {
    ev.preventDefault();
    selectCard(Math.min(CHAPTER.length - 1, focusIndex + 1), { scroll: true });
    if (state.playing) playSection(focusIndex);
  } else if (ev.key === "ArrowUp" || ev.key === "k") {
    ev.preventDefault();
    selectCard(Math.max(0, focusIndex - 1), { scroll: true });
    if (state.playing) playSection(focusIndex);
  } else if ((ev.key === "e" || ev.key === "E") && document.getElementById("toggleEn")) {
    setAll("en", !state.enOpen);
  } else if (ev.key === "u" || ev.key === "U" || ev.key === "Escape") {
    setAll("ua", !state.uaOpen);
  } else if (ev.key === "c" || ev.key === "C" || ev.key === "ArrowRight") {
    continuousEl.click();
  } else if (ev.key === "t" || ev.key === "T" || ev.key === "ArrowLeft") {
    themeEl.click();
  }
});
