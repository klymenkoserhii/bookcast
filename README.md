# Bookcast

Bookcast is a collection of books to read, listen to, and study. Each book has a published reader and contents page, with chapter audio and vocabulary materials where available.

## Books

- **The Hound of the Baskervilles** — trilingual study edition (EN → PL → UA)
- **Lalka** — bilingual study edition (PL → UA)
- **Tajny agent** — trilingual study edition (EN → PL → UA)

Open the library at [`public/index.html`](public/index.html).

## Repository layout

- `src/<book-slug>/` — chapter Markdown, book metadata, vocabulary sources, audio-alignment data, and book-specific build tools.
- `public/<book-slug>/` — published chapter readers, vocabulary pages, book contents page, and browser-ready audio.
- `public/index.html` — main library catalog.

The source and published directories use the same book slug.

## Preview locally

From the repository root, serve the published files over HTTP:

```bash
python3 -m http.server 8000 --directory public
```

Then open <http://localhost:8000>.

Serving the site over HTTP lets readers load chapter audio as a Blob. Readers also support direct relative audio loading when opened from `file://`.

## Updating a book

Use the scripts and instructions in that book’s `src/<book-slug>/` directory. After changing chapter content or adding materials:

1. Rebuild the affected chapter reader(s) and any vocabulary pages.
2. Rebuild the book’s contents page so its links and chapter details are current.
3. Check the chapter links and audio paths, then preview the updated pages locally.

Published readers and audio belong under `public/`; keep working files and build inputs under `src/`.

## Audio

Published readers use WebM audio assets stored in each book’s `public/<book-slug>/audio/` directory. Where original MP3s are present as local build inputs, note that MP3 files are ignored by Git; the published WebM assets are the files used by the site.

## Deployment

The site is deployed automatically on push to GitHub:

- [Cloudflare](https://bookcast.klimenkoserg.workers.dev/)
- [GitHub Pages](https://klymenkoserhii.github.io/bookcast/public)
