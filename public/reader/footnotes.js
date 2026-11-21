function positionFootnoteTooltip(reference, tooltip) {
  const refRect = reference.getBoundingClientRect();
  const tipRect = tooltip.getBoundingClientRect();
  const left = Math.max(12, Math.min(
    refRect.left + refRect.width / 2 - tipRect.width / 2,
    window.innerWidth - tipRect.width - 12
  ));
  let top = refRect.bottom + 8;
  if (top + tipRect.height > window.innerHeight - 12) {
    top = refRect.top - tipRect.height - 8;
  }
  top = Math.max(12, Math.min(top, window.innerHeight - tipRect.height - 12));
  tooltip.style.left = `${left}px`;
  tooltip.style.top = `${top}px`;
}

function appendTooltipText(parent, text) {
  const inline = /\\\*|\*([^*]+)\*/g;
  let cursor = 0;
  let match;
  while ((match = inline.exec(text)) !== null) {
    parent.appendChild(document.createTextNode(text.slice(cursor, match.index)));
    if (match[0] === "\\*") {
      parent.appendChild(document.createTextNode("*"));
    } else {
      const italic = document.createElement("em");
      italic.textContent = match[1];
      parent.appendChild(italic);
    }
    cursor = inline.lastIndex;
  }
  parent.appendChild(document.createTextNode(text.slice(cursor)));
}

// Keep superscript markers inside the surrounding spoken word.
function wrapWords(root) {
  const spans = [];
  let activeWord = null;
  for (const node of Array.from(root.childNodes)) {
    if (node.nodeType === 1 && node.tagName === "SUP") {
      if (activeWord) activeWord.appendChild(node);
      continue;
    }
    if (node.nodeType !== 3) continue;
    const parts = node.nodeValue.split(/(\s+)/);
    const frag = document.createDocumentFragment();
    for (const part of parts) {
      if (!part) continue;
      if (/^\s+$/.test(part)) {
        frag.appendChild(document.createTextNode(part));
        activeWord = null;
        continue;
      }
      if (!activeWord) {
        activeWord = document.createElement("span");
        activeWord.className = "w";
        spans.push(activeWord);
        frag.appendChild(activeWord);
      }
      activeWord.appendChild(document.createTextNode(part));
    }
    node.parentNode.replaceChild(frag, node);
  }
  return spans;
}

function setStudyText(element, text) {
  const trilingual = !!document.getElementById("toggleEn");
  const footnote = trilingual ? /<sup>(\d+)<\/sup>|([⁰¹²³⁴⁵⁶⁷⁸⁹]+)/g : /<sup>(\d+)<\/sup>/g;
  const digits = { "⁰": "0", "¹": "1", "²": "2", "³": "3", "⁴": "4",
                   "⁵": "5", "⁶": "6", "⁷": "7", "⁸": "8", "⁹": "9" };
  let cursor = 0;
  let match;
  while ((match = footnote.exec(text)) !== null) {
    element.appendChild(document.createTextNode(text.slice(cursor, match.index)));
    const sup = document.createElement("sup");
    const number = match[1] || Array.from(match[2], digit => digits[digit]).join("");
    const display = match[1] || match[2];
    const note = ANNOTATIONS[number];
    if (note) {
      sup.className = "footnote-ref";
      sup.tabIndex = 0;
      sup.setAttribute("aria-label", `Przypis ${number}: ${note.term}`);
      const visible = document.createElement("span");
      visible.textContent = display;
      sup.appendChild(visible);

      const tooltip = document.createElement("span");
      tooltip.className = "footnote-tooltip";
      tooltip.setAttribute("role", "tooltip");
      tooltip.id = `footnote-tooltip-${++footnoteTooltipIndex}`;
      sup.setAttribute("aria-describedby", tooltip.id);
      const term = document.createElement("strong");
      term.textContent = note.term;
      tooltip.appendChild(term);
      const plLabel = document.createElement("span");
      plLabel.className = "note-label";
      plLabel.textContent = "Definicja (PL)";
      tooltip.appendChild(plLabel);
      const definition = document.createElement("span");
      definition.className = "note-pl";
      appendTooltipText(definition, note.definition);
      tooltip.appendChild(definition);
      const translation = document.createElement("span");
      translation.className = "note-ua";
      const uaLabel = document.createElement("span");
      uaLabel.className = "note-label";
      uaLabel.textContent = "Переклад (UA)";
      translation.appendChild(uaLabel);
      appendTooltipText(translation, note.translation);
      tooltip.appendChild(translation);
      sup.appendChild(tooltip);
      sup.addEventListener("mouseenter", () => positionFootnoteTooltip(sup, tooltip));
      sup.addEventListener("focus", () => positionFootnoteTooltip(sup, tooltip));
    } else {
      sup.textContent = display;
    }
    element.appendChild(sup);
    cursor = footnote.lastIndex;
  }
  element.appendChild(document.createTextNode(text.slice(cursor)));
}
