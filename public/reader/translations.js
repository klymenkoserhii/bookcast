const englishToggle = document.getElementById("toggleEn");
const ukrainianToggle = document.getElementById("toggleUa");

function setChip(chip, box, open) {
  box.hidden = !open;
  chip.textContent = (box.classList.contains("en") ? "EN " : "UA ") + (open ? "▴" : "▾");
  chip.setAttribute("aria-expanded", String(open));
}

function setEn(i, open) { setChip(els[i].enChip, els[i].enBox, open); }
function setUa(i, open) { setChip(els[i].uaChip, els[i].uaBox, open); }

function setAll(kind, open) {
  const english = kind === "en";
  state[english ? "enOpen" : "uaOpen"] = open;
  els.forEach((entry, i) => (english ? setEn(i, open) : setUa(i, open)));
  const button = english ? englishToggle : ukrainianToggle;
  button.textContent = (open ? "Hide all " : "Reveal all ") + kind.toUpperCase();
  button.setAttribute("aria-pressed", String(open));
  button.classList.toggle("is-on", open);
}

if (englishToggle) englishToggle.addEventListener("click", () => setAll("en", !state.enOpen));
ukrainianToggle.addEventListener("click", () => setAll("ua", !state.uaOpen));
