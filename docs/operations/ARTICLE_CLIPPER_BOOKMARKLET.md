# Article clipper bookmarklet

Feeds a paid-subscription analysis piece you're personally reading (e.g. CNBC Investing Club)
into the same catalyst pipeline FMP news headlines already use — without ever logging into or
scraping the source site programmatically. You click the bookmarklet yourself, once, while
viewing the page in your own browser; it reads the text already rendered on your screen and
sends it to your own backend. No credentials are stored anywhere, and nothing runs unattended.

**Code:** `backend/signals/manual_catalysts.py` (storage + fallback card), `backend/api/routers/article_ingest.py` (endpoint), wired into `backend/api/ticker_detail.py::_build_news_sentiment_layer_for_ui()` so clips appear in the same News rail and Why-panel gate-linked catalysts as FMP headlines — no frontend changes.

## Why it's built this way

- **Manually triggered, not automated.** The bookmarklet only runs when you click it, on a page
  you're already viewing. That's categorically different from a script that logs in and crawls
  pages unattended — same idea as a personal "save to Pocket" clipper.
- **Cross-origin without touching CORS.** The bookmarklet posts from whatever site you're on
  (e.g. cnbc.com) to your Railway backend. Browsers block a page's JS from *reading* a
  cross-origin response unless the server's CORS policy allows it — but they always allow
  *sending* a "simple" request (`mode: "no-cors"`, a CORS-safelisted `Content-Type` like
  `text/plain`, no custom headers) regardless of the target's CORS policy. The bookmarklet uses
  exactly that, so `api/main.py`'s CORS policy needed no changes — the tradeoff is the
  bookmarklet can't read the server's response, so it just shows an optimistic confirmation.
- **Secret lives in the body, not a header.** A custom header (like the `X-Push-Admin-Secret`
  pattern used for `/api/push/test`) would force a CORS preflight, which a third-party origin
  can't satisfy against this app's restrictive policy — breaking the no-cors trick above. So the
  shared secret travels as a field in the JSON body instead.
- **Always produces a visible card.** The underlying classifier (`build_catalyst_note_cards`)
  only recognizes ~20 hard-news patterns (earnings, M&A, FDA, etc.) and silently drops anything
  that matches none of them — exactly the risk for a long-form "is this stock a buy" opinion
  piece. `manual_catalysts.py` tries that classifier first (so a clip that *does* mention a real
  event still gets categorized properly), and falls back to a generic "Analyst Note" card
  otherwise, so a clip never silently vanishes.

## Setup

1. Set `ARTICLE_INGEST_SECRET` on your backend (Railway env vars or local `.env`) to a random
   string only you know. Leaving it unset disables the check entirely — fine for local dev, not
   recommended once the backend is publicly reachable.
2. Create a new bookmark in your browser (any bookmarks bar works) and paste the snippet below
   as its URL, after replacing `INGEST_URL` and `SECRET` with your own values.
3. Name the bookmark something like "Clip to Thrive Alpha."

**Readable source** (for reference/editing — the bookmark itself needs the minified one-liner below):

```js
(function () {
  var INGEST_URL = "https://YOUR-BACKEND-HOST/api/ingest/article";
  var SECRET = "REPLACE_WITH_YOUR_SECRET";
  var ticker = window.prompt("Ticker for this article?", "");
  if (!ticker) return;
  var payload = {
    secret: SECRET,
    ticker: ticker,
    title: document.title,
    text: document.body.innerText,
    url: location.href,
  };
  fetch(INGEST_URL, {
    method: "POST",
    mode: "no-cors",
    headers: { "Content-Type": "text/plain" },
    body: JSON.stringify(payload),
  });
  alert("Sent to Thrive Alpha - check " + ticker.toUpperCase() + "'s catalyst notes shortly.");
})();
```

**Bookmark URL** (paste this whole line as the bookmark's URL, after editing the two `REPLACE_`
placeholders):

```
javascript:(function(){var u="REPLACE_WITH_YOUR_BACKEND_URL/api/ingest/article";var s="REPLACE_WITH_YOUR_SECRET";var t=window.prompt("Ticker for this article?","");if(!t)return;var p={secret:s,ticker:t,title:document.title,text:document.body.innerText,url:location.href};fetch(u,{method:"POST",mode:"no-cors",headers:{"Content-Type":"text/plain"},body:JSON.stringify(p)});alert("Sent to Thrive Alpha - check "+t.toUpperCase()+"'s catalyst notes shortly.");})();
```

## Use

While reading an article (e.g. an Investing Club piece):
1. Click the bookmarklet.
2. Type the ticker it's about when prompted (e.g. `AMZN`) and confirm.
3. You'll see a confirmation alert immediately (it can't confirm the server actually accepted
   it — see the CORS note above — so check the ticker's News rail / Why panel a moment later to
   verify the clip actually landed).

## Known limitations (v1)

- **No ticker auto-detection.** Nothing in the backend today scans text for ticker/company
  mentions, so you type it yourself. Simplest reliable option given no such utility exists yet.
- **Body extraction is `document.body.innerText`** — whatever text is visibly rendered on the
  page, including nav/boilerplate. The event classifier and LLM wrap both tolerate noise fine,
  but a smarter `<article>`-tag-aware extraction would produce cleaner input if this gets used
  heavily.
- **The shared secret lives in the bookmarklet's own source.** Since it's a static snippet you
  install locally, its only protection is not sharing that bookmarklet text with anyone else —
  an accepted tradeoff for a single-user personal tool (this app has no per-user auth system).
- Clips are capped at 20 most recent per ticker and ~20,000 characters each
  (`manual_catalysts.MAX_ARTICLES_PER_TICKER` / `MAX_TEXT_CHARS`) — bounds file growth, not
  meant as a long-term archive.
