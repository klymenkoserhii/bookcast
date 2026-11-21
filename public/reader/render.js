function render() {
  const trilingual = !!document.getElementById("toggleEn");
  const frag = document.createDocumentFragment();
  let lastPara = CHAPTER.length ? CHAPTER[0].para : 0;

  CHAPTER.forEach((unit, i) => {
    // Paragraph break (from `---` in the Markdown) => visual separator.
    if (i > 0 && unit.para !== lastPara) {
      const sep = document.createElement("div");
      sep.className = "para-sep";
      sep.setAttribute("aria-hidden", "true");
      sep.textContent = "⁂";
      frag.appendChild(sep);
      lastPara = unit.para;
    }

    const card = document.createElement("article");
    card.className = "unit";
    card.id = "u-" + (i + 1);   // stable anchor: vocabulary pages link to chapter-NN.html#u-N
    card.dataset.index = String(i);
    card.setAttribute("aria-labelledby", "pl-" + i);

    /* --- PL: always visible, primary study text --- */
    const row = document.createElement("div");
    row.className = "pl-row";

    const btn = document.createElement("button");
    btn.type = "button";
    btn.className = "play";
    btn.textContent = "▶";
    const hasTime = startOf(i) != null;
    btn.disabled = !hasTime;
    btn.title = hasTime
      ? `Play section ${i + 1} (${fmt(startOf(i))}–${fmt(endOf(i))})`
      : "no timestamp";
    btn.setAttribute("aria-label", btn.title);
    btn.addEventListener("click", () => toggleSection(i));

    const pl = document.createElement("p");
    pl.className = "pl";
    pl.id = "pl-" + i;
    pl.lang = "pl";
    setStudyText(pl, unit.pl);

    /* --- word spans for progress mode 2, kept only when they line up --- */
    let wordSpans = null;
    let wordTimes = null;
    const unitWordTimes = WORD_TIMES && WORD_TIMES[i];
    if (unitWordTimes && unitWordTimes.length) {
      const spans = wrapWords(pl);
      if (spans.length === unitWordTimes.length) {
        wordSpans = spans;
        wordTimes = unitWordTimes;
        card.classList.add("has-words");
      } else {
        pl.replaceChildren();          // tokenisation mismatch: plain text, no underline
        setStudyText(pl, unit.pl);
      }
    }

    row.append(btn, pl);

    /* --- number badge --- */
    const num = document.createElement("span");
    num.className = "num";
    num.textContent = String(i + 1);

    /* --- EN / UA toggle chips --- */
    const toggles = document.createElement("div");
    toggles.className = "toggles";

    const enChip = trilingual ? document.createElement("button") : null;
    if (enChip) {
    enChip.type = "button";
    enChip.className = "chip";
    enChip.textContent = "EN ▾";
    enChip.setAttribute("aria-expanded", "false");
    enChip.setAttribute("aria-controls", "en-" + i);
    }

    const uaChip = document.createElement("button");
    uaChip.type = "button";
    uaChip.className = "chip";
    uaChip.textContent = "UA ▾";
    uaChip.setAttribute("aria-expanded", "false");
    uaChip.setAttribute("aria-controls", "ua-" + i);

    if (enChip) toggles.appendChild(enChip);
    toggles.appendChild(uaChip);

    /* --- hidden EN block --- */
    const enBox = trilingual ? document.createElement("div") : null;
    if (enBox) {
    enBox.className = "stack en";
    enBox.id = "en-" + i;
    enBox.hidden = true;
    const enLbl = document.createElement("span");
    enLbl.className = "lbl";
    enLbl.textContent = "English";
    const enP = document.createElement("p");
    enP.lang = "en";
    setStudyText(enP, unit.en);
    enBox.append(enLbl, enP);
    }

    /* --- hidden UA block --- */
    const uaBox = document.createElement("div");
    uaBox.className = "stack ua";
    uaBox.id = "ua-" + i;
    uaBox.hidden = true;
    const uaLbl = document.createElement("span");
    uaLbl.className = "lbl";
    uaLbl.textContent = "Українська";
    const uaP = document.createElement("p");
    uaP.lang = "uk";
    setStudyText(uaP, unit.ua);
    uaBox.append(uaLbl, uaP);

    /* --- progress hairline --- */
    const pbar = document.createElement("div");
    pbar.className = "pbar";
    pbar.appendChild(document.createElement("span"));

    card.append(num, row, toggles);
    if (enBox) card.appendChild(enBox);
    card.append(uaBox, pbar);

    if (enChip) enChip.addEventListener("click", () => setEn(i, enBox.hidden));
    uaChip.addEventListener("click", () => setUa(i, uaBox.hidden));

    // Click anywhere on the card to select it (the Continuous play start point).
    // Double-click starts that section immediately.
    card.addEventListener("click", (ev) => {
      if (ev.target.closest("button, input, select, a, label")) return;
      selectCard(i);
    });
    card.addEventListener("dblclick", (ev) => {
      if (ev.target.closest("button, input, select, a, label")) return;
      toggleSection(i);
    });

    els[i] = { card, btn, enChip, uaChip, enBox, uaBox, pbar: pbar.firstElementChild,
               words: wordSpans, wordTimes: wordTimes };
    frag.appendChild(card);
  });

  cardsEl.appendChild(frag);

  const timed = CHAPTER.filter((u) => u.start != null).length;
  statsEl.textContent =
    `${CHAPTER.length} units · ${timed} timed sections · audio: ${AUDIO_URL}`;
}

