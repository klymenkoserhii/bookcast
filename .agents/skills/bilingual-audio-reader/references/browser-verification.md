# Verifying a built chapter in the browser

Static checks (unit counts, monotonic times) do not prove the audio works. Open the page and drive it. These probes check what a user would notice: the page loads, section playback starts at the right time, it stops at the boundary, and selecting a card then pressing Continuous starts from that card.

Written for the `execute` tool's `tools.browser` API; adapt the calls if your harness differs. The JavaScript inside `evaluate` runs in the page.

## 0. Serve the Bookcast repository over HTTP

```bash
cd <bookcast-repository>
nohup python3 <skill-dir>/scripts/range_server.py "$PWD" 8150 >/tmp/range.log 2>&1 &
# cold Python start can take a couple of seconds: wait until it answers instead of a fixed sleep
for i in $(seq 1 20); do curl -sf -o /dev/null http://127.0.0.1:8150/public/<book-slug>/chapter-03.html && break; sleep 0.5; done
curl -s -o /dev/null -w "range=%{http_code}\n" -H "Range: bytes=0-99" "http://127.0.0.1:8150/public/<book-slug>/audio/chapter-03.webm"   # 206 required only for the direct-media timestamp helper
```

The reader fetches the complete audio with `fetch()` and plays a Blob URL, so reader seeking does not depend on Range support. The helper uses direct media and may require Range support. Use a fresh port or stop the old server first.

## 1. Reader probe

Pick card indexes that exist (`N` = unit count). Do not reuse hard-coded numbers from another chapter.

```js
const tab = await tools.browser.tabs.open({ url: "http://127.0.0.1:8150/public/<book-slug>/chapter-03.html" })
await tools.browser.wait({ tabID: tab.id, condition: "load" })
const consoleErrors = (await tools.browser.console({ tabID: tab.id, level: "error" })).messages.map(m => m.text)
const r = await tools.browser.evaluate({ tabID: tab.id, script: `(async () => {
  const a = document.getElementById('audio');
  const cards = [...document.querySelectorAll('.unit')];
  const wait = ms => new Promise(r => setTimeout(r, ms));
  await new Promise(res => { if (a.readyState >= 1) res(); else a.addEventListener('loadedmetadata', res, {once:true}); });
  const last = cards.length - 1, mid = Math.floor(last / 2), sel = Math.floor(last * 0.75);
  const cn = document.querySelector('.brand .chapter-name');
  const base = { title: document.title, chapterName: cn && cn.textContent, units: cards.length,
    duration: +a.duration.toFixed(1), stats: document.getElementById('stats').textContent,
    requestedAudio: eval('AUDIO_URL'), currentSrc: a.currentSrc,
    disabledIdx: cards.map((c,i) => c.querySelector('.play').disabled ? i : -1).filter(i => i >= 0),
    starts: [CHAPTER[0].start, CHAPTER[last].start] };
  // 1. section playback starts at its timestamp and advances
  cards[mid].querySelector('.play').click(); await wait(1500);
  const play = { start: CHAPTER[mid].start, now: +a.currentTime.toFixed(2), playing: !a.paused };
  // 2. hard stop at the next section boundary
  let next = mid + 1; while (CHAPTER[next].start == null) next++;
  a.currentTime = CHAPTER[next].start - 0.3; await wait(1200);
  const stop = { paused: a.paused, t: +a.currentTime.toFixed(2), boundary: CHAPTER[next].start };
  // 3. select a card while another plays, then Continuous must start from the selection
  cards[3].querySelector('.play').click(); await wait(800);
  cards[sel].querySelector('.pl').click(); await wait(150);
  const label = document.getElementById('continuous').textContent;
  document.getElementById('continuous').click(); await wait(1500);
  const cont = { active: cards.findIndex(c => c.classList.contains('is-playing')), expected: sel,
                 start: CHAPTER[sel].start, now: +a.currentTime.toFixed(2) };
  document.getElementById('continuous').click(); await wait(250); a.pause();
  return { base, play, stop, label, cont };
})()` })
```

What good looks like:

- `units` equals the markdown unit count; `duration` matches the encoded reader asset and is within about one second of the original MP3; `requestedAudio` is the relative WebM URL and `currentSrc` is a `blob:` URL.
- `disabledIdx` lists exactly the merged units (empty if none).
- `play.now` is within about 1.5 s of `play.start` and `playing` is true.
- `stop.paused` is true and `stop.t` is within about 0.25 s after `stop.boundary`.
- `label` reads "Continuous from #<sel+1>" and `cont.active === cont.expected`.

## 2. Helper probe: run it in its own call

```js
const h = await tools.browser.tabs.open({ url: "http://127.0.0.1:8150/src/<book-slug>/chapter-03.timestamp-helper.html" })
await tools.browser.wait({ tabID: h.id, condition: "load" })
const v = await tools.browser.evaluate({ tabID: h.id, script: `(async () => {
  const a = document.getElementById('audio');
  await new Promise(res => { if (a.readyState >= 1) res(); else a.addEventListener('loadedmetadata', res, {once:true}); });
  return { rows: document.querySelectorAll('li.row').length, counter: document.getElementById('counter').textContent,
           duration: +a.duration.toFixed(1), row1: document.querySelector('li.row .val').textContent };
})()` })
```

`rows` equals the unit count and `counter` is the number of stamped (timed) rows, so it is lower than `rows` by the number of merged units.

## Checking many chapters at once (same-origin iframes)

Opening one tab per chapter in a single script was unreliable: for one book it worked, for another every tab after the first threw a `TypeError`. A robust alternative, since the pages are same-origin on the test server, is to open **one** tab and load each chapter into a hidden iframe, driving it through `iframe.contentWindow`. Two things matter:

- `CHAPTER` and `AUDIO_TIMES` are top-level `const`s, so they are **not** properties of `window`. Read them with `w.eval('CHAPTER[30].start')` (indirect eval runs in the page's global scope). `w.CHAPTER` is `undefined`, and using it gives `TypeError: Cannot read properties of undefined`.
- One `evaluate` call is cut off after 60 s. Budget about 6 s per chapter and run at most 5 chapters per call.

Sketch (per chapter, inside the page script of the first tab):

```js
const fr = document.createElement('iframe'); fr.style.cssText = 'position:fixed;left:0;top:0;width:900px;height:700px;opacity:0';
fr.src = '/chapter-' + n + '.html'; document.body.appendChild(fr);
await new Promise(res => fr.onload = res);
const w = fr.contentWindow, d = w.document;
for (let i = 0; i < 40 && !(d.getElementById('audio') && w.eval('typeof CHAPTER') !== 'undefined' && d.querySelectorAll('.unit').length); i++) await wait(250);
// ... same assertions as the reader probe, using d / w.KeyboardEvent / w.eval('CHAPTER[k].start') ...
fr.remove();
```

Assert per chapter: unit count equals the markdown, disabled buttons equal the merged units, no `__PLACEHOLDER__` text, chapter name present, section playback starts at its timestamp, and (if the template has the TV keys) Enter on a focused button does not play while Enter on the page does.

**Do not stop the test server in the same step as the browser test.** Tool calls issued together run in parallel, so killing the server mid-test produces timeouts and console errors that look like page bugs. Stop it in a later step.

## Things that went wrong in testing, and are not file bugs

- **Make the probe wait for the page to boot.** `browser.wait({condition:"load"})` can return before the inline script has built the cards, so a probe that reads `document.getElementById('audio')` immediately fails with a `TypeError`. Start every probe by polling until `#audio`, `CHAPTER` and `.unit` elements exist (about 10 s max). With that poll, several chapters can be checked in one script, one tab each, closing each tab afterwards. Earlier, I mistook this for a helper-page bug and ran helper probes in separate calls.
- **Do not navigate one tab between chapters** with `location.href = ...`: the next `browser.wait` fails with "The document changed before this operation ran". Open a new tab per chapter instead.
- **Allow time for seeks in long files.** Starting a section far into a 1-hour MP3 can take a second or two to buffer; poll until `currentTime` passes the section start (up to ~5 s) instead of a fixed 1.2 s wait.
- **HTTP/1.0 test servers get intermittent 502s** from the automation proxy. `range_server.py` uses HTTP/1.1 keep-alive, which fixed it.
- **`browser.screenshot` needs a visible window.** In a headless or hidden window it fails with "Screenshot needs a visible tab". Say so in the report instead of retrying: the DOM and audio-state assertions above are the substantive check.
- **`setTimeout` is not available in the `execute` sandbox itself** (only inside `evaluate` page scripts). Put waits inside the page script.
- Clean up afterwards: kill the server, close all tabs.
