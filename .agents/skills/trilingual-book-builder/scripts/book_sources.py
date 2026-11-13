# -*- coding: utf-8 -*-
"""Source adapters for trilingual-book-builder (standard library only, pypdf/pdftotext optional).

A *source spec* (one per language, in book.config.json) tells these helpers where a
chapter lives and how to turn it into a list of paragraphs:

  kind "epub": {"path": "x.epub", "file": "EPUB/part{n}\\.xhtml$", "offset": 1,
                "container": "id=\\"book-text\\"", "cut": "THE FULL PROJECT GUTENBERG",
                "title_re": "^[IVXLCDM]+\\.\\s*"}
        chapter n is the single zip entry matching  file.format(n=chapter+offset).
  kind "pdf" | "txt": {"path": "x.pdf", "heading": "^\\s*Rozdział\\s+[IVXLCDM]+\\s*$",
                "start_after": null, "strip_lines": ["^\\s*\\d+\\s*$"],
                "para_mode": "blank", "title_re": null}
        chapter n is the n-th heading match in the text (after start_after, if given).

Every adapter returns {"title": str, "paras": [str], "file": str}.
"""
from __future__ import annotations

import html
import re
import shutil
import subprocess
import zipfile
from pathlib import Path


# ---------------------------------------------------------------- helpers

def norm(t: str) -> str:
    t = t.replace("\r\n", "\n").replace("\r", "\n")
    t = re.sub(r"[ \t\n\f\v]+", " ", t)
    return t.strip(" \t\n")


def strip_tags(fragment: str) -> str:
    fragment = re.sub(
        r"<sup[^>]*>(\d+)</sup>", lambda m: f"\x00SUP{m.group(1)}\x00", fragment
    )
    fragment = re.sub(r"<br\s*/?>", " ", fragment)
    fragment = re.sub(r"<[^>]+>", "", fragment)
    fragment = html.unescape(fragment)
    return re.sub(r"\x00SUP(\d+)\x00", r"<sup>\1</sup>", fragment)


def read_epub(path: Path) -> dict[str, str]:
    with zipfile.ZipFile(path) as z:
        out = {}
        for name in z.namelist():
            if name.lower().endswith((".xhtml", ".html", ".htm")):
                out[name] = z.read(name).decode("utf-8", "replace")
        return out


def find_name(names, pattern: str) -> str:
    rx = re.compile(pattern)
    hits = [n for n in names if rx.search(n)]
    if not hits:
        raise FileNotFoundError(f"no EPUB entry matching {pattern!r}")
    if len(hits) > 1:
        raise RuntimeError(f"ambiguous EPUB entries for {pattern!r}: {hits[:5]}")
    return hits[0]


def paras_from_html(text: str, container: str, cut: str | None = None) -> list[str]:
    if not container:
        marker = "<body"
    elif container.startswith("<"):
        marker = container                      # full opening tag prefix, e.g. '<section id="chapter-'
    else:
        marker = f"<div {container}"            # attribute(s) of a <div>
        if marker not in text:
            marker = f"<div class='{container}'"
    if marker not in text:
        raise ValueError(f"container not found: {container!r}")
    body = text.split(marker, 1)[1]
    if cut and cut in body:
        body = body.split(cut, 1)[0]
    body = re.sub(r"<h[12].*?</h[12]>", "", body, flags=re.S)
    paras = [norm(strip_tags(p)) for p in re.findall(r"<p[^>]*>(.*?)</p>", body, re.S)]
    return [p for p in paras if p and p != "*"]


def html_title(text: str, title_re: str | None) -> str:
    m = re.search(r"<h[12][^>]*>(.*?)</h[12]>", text, re.S)
    if not m:
        return ""
    title = norm(strip_tags(m.group(1)))
    if title_re:
        title = re.sub(title_re, "", title, count=1)
    return title.strip()


# ---------------------------------------------------------------- epub

_epub_cache: dict[str, dict[str, str]] = {}


def epub_files(path: Path) -> dict[str, str]:
    key = str(path)
    if key not in _epub_cache:
        _epub_cache[key] = read_epub(path)
    return _epub_cache[key]


def epub_chapter(root: Path, spec: dict, chapter: int) -> dict:
    files = epub_files(root / spec["path"])
    pattern = spec["file"].replace("{n}", str(chapter + int(spec.get("offset", 0))))
    name = find_name(files, pattern)
    text = files[name]
    paras = paras_from_html(text, spec["container"], spec.get("cut"))
    return {"title": html_title(text, spec.get("title_re")), "paras": paras, "file": name}


# ---------------------------------------------------------------- pdf / txt

_text_cache: dict[str, str] = {}


def pdf_text(path: Path) -> str:
    if shutil.which("pdftotext"):
        out = subprocess.run(
            ["pdftotext", "-enc", "UTF-8", str(path), "-"],
            capture_output=True, check=True,
        )
        return out.stdout.decode("utf-8", "replace")
    try:
        import pypdf  # type: ignore
    except ImportError as e:  # pragma: no cover
        raise SystemExit(
            f"PDF extraction needs `pdftotext` (poppler) or `pip install pypdf` ({e}); "
            "scanned PDFs need OCR first (see the pdf skill)."
        ) from e
    reader = pypdf.PdfReader(str(path))
    return "\n\n".join((p.extract_text() or "") for p in reader.pages)


def source_text(root: Path, spec: dict) -> str:
    path = root / spec["path"]
    key = str(path)
    if key not in _text_cache:
        if spec["kind"] == "pdf":
            text = pdf_text(path)
        else:
            text = path.read_text(encoding=spec.get("encoding", "utf-8"))
        text = text.replace("\r\n", "\n").replace("\r", "\n").replace("\f", "\n\n")
        for bad, good in spec.get("char_map", {}).items():
            text = text.replace(bad, good)
        warn_if_garbled(text, spec["path"])
        _text_cache[key] = text
    return _text_cache[key]


def warn_if_garbled(text: str, name: str) -> None:
    """PDFs with broken font encodings yield stray glyphs (private-use, Telugu...)."""
    import sys
    from collections import Counter
    odd = Counter(
        ch for ch in text
        if ord(ch) > 0x24F and not (0x2000 <= ord(ch) <= 0x206F) and not (0x0400 <= ord(ch) <= 0x04FF)
        and ch not in "\u201e\u201d\u201c\u2019\u2026\u00ab\u00bb"
    )
    n = sum(odd.values())
    if n > 20:
        print(
            f"WARNING: {name}: {n} unexpected glyphs, e.g. {odd.most_common(6)}. The PDF font "
            "encoding is probably broken; add a 'char_map' to the source spec "
            "(for example {\"\u0c17\": \"j\"}) or use an EPUB/TXT of the same text.",
            file=sys.stderr,
        )


def split_text_chapters(text: str, spec: dict) -> list[tuple[str, str]]:
    """Return [(heading_line, body)] for every chapter heading match."""
    if spec.get("start_after"):
        m = re.search(spec["start_after"], text, re.M)
        if m:
            text = text[m.end():]
    rx = re.compile(spec["heading"], re.M)
    matches = list(rx.finditer(text))
    out = []
    for i, m in enumerate(matches):
        end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
        out.append((m.group(0).strip(), text[m.end():end]))
    return out


def text_paragraphs(body: str, spec: dict) -> list[str]:
    strip = [re.compile(p) for p in spec.get("strip_lines", [])]
    lines = [ln.rstrip() for ln in body.split("\n")]
    lines = [ln for ln in lines if not any(r.search(ln) for r in strip) or not ln.strip()]
    mode = spec.get("para_mode", "blank")
    if mode == "line":
        paras = [ln.strip() for ln in lines if ln.strip()]
    else:
        paras, cur = [], []
        for ln in lines:
            if ln.strip():
                cur.append(ln.strip())
            elif cur:
                paras.append(" ".join(cur))
                cur = []
        if cur:
            paras.append(" ".join(cur))
    out = []
    for p in paras:
        p = re.sub(r"(\w)-\s+(?=[a-ząćęłńóśźż])", r"\1", p) if spec.get("dehyphenate", True) else p
        p = norm(p)
        if p and p != "*":
            out.append(p)
    return out


def text_chapter(root: Path, spec: dict, chapter: int) -> dict:
    chapters = split_text_chapters(source_text(root, spec), spec)
    if not 1 <= chapter <= len(chapters):
        raise ValueError(
            f"{spec['path']}: heading regex found {len(chapters)} chapters, wanted {chapter}"
        )
    heading, body = chapters[chapter - 1]
    title = re.sub(spec["title_re"], "", heading, count=1).strip() if spec.get("title_re") else ""
    return {"title": title, "paras": text_paragraphs(body, spec), "file": f"{spec['path']}#{chapter}"}


# ---------------------------------------------------------------- UA reference (optional)

def ua_reference(root: Path, spec: dict | None, chapter: int) -> list[str]:
    """Paragraphs of an existing Ukrainian edition; reference only, never copied."""
    if not spec or not (root / spec["path"]).exists():
        return []
    if spec.get("kind", "epub") != "epub":
        got = text_chapter(root, spec, chapter)
        return got["paras"]
    files = epub_files(root / spec["path"])
    names = sorted(n for n in files if re.search(spec["files"], n))
    ps: list[str] = []
    for name in names:
        ps.extend(norm(strip_tags(p)) for p in re.findall(r"<p[^>]*>(.*?)</p>", files[name], re.S))
    ps = [p for p in ps if p]
    marks = [i for i, p in enumerate(ps) if re.fullmatch(spec["marker"], p)]
    if chapter > len(marks):
        return []
    start = marks[chapter - 1] + int(spec.get("skip", 1))
    end = marks[chapter] if chapter < len(marks) else len(ps)
    return [p for p in ps[start:end] if p]


# ---------------------------------------------------------------- dispatch

def chapter_from(root: Path, spec: dict, chapter: int) -> dict:
    kind = spec.get("kind", "epub")
    if kind == "epub":
        return epub_chapter(root, spec, chapter)
    if kind in ("pdf", "txt"):
        return text_chapter(root, {**spec, "kind": kind}, chapter)
    raise ValueError(f"unknown source kind {kind!r}")
