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
  // Article body only (no nav/ads); falls back to <main>/<body>.
  var root = document.querySelector(".ArticleBody-articleBody, [data-module='ArticleBody'], article")
    || document.querySelector("main") || document.body;
  // Tickers the article links to (CNBC quote links look like /quotes/AAPL).
  var tickers = [];
  root.querySelectorAll('a[href*="/quotes/"]').forEach(function (a) {
    var m = a.href.match(/\/quotes\/([A-Za-z.\-]{1,6})/);
    if (m && tickers.indexOf(m[1].toUpperCase()) < 0) tickers.push(m[1].toUpperCase());
  });
  var ticker = window.prompt("Main ticker (optional). Detected: " + (tickers.join(", ") || "none"), "");
  if (ticker === null) return;
  fetch(INGEST_URL, {
    method: "POST",
    mode: "no-cors",
    headers: { "Content-Type": "text/plain" },
    body: JSON.stringify({
      secret: SECRET, ticker: ticker, tickers: tickers,
      title: document.title, text: root.innerText, url: location.href,
    }),
  });
  alert("Sent to Thrive Alpha: " + (ticker || tickers.join(", ") || "auto-detect"));
})();
```

**Bookmark URL** (paste this whole line as the bookmark's URL, after editing the two `REPLACE_`
placeholders):

```
javascript:(function(){var u="REPLACE_WITH_YOUR_BACKEND_URL/api/ingest/article";var s="REPLACE_WITH_YOUR_SECRET";var r=document.querySelector(".ArticleBody-articleBody, [data-module='ArticleBody'], article")||document.querySelector("main")||document.body;var k=[];r.querySelectorAll('a[href*="/quotes/"]').forEach(function(a){var m=a.href.match(/\/quotes\/([A-Za-z.\-]{1,6})/);if(m&&k.indexOf(m[1].toUpperCase())<0)k.push(m[1].toUpperCase());});var t=window.prompt("Main ticker (optional). Detected: "+(k.join(", ")||"none"),"");if(t===null)return;fetch(u,{method:"POST",mode:"no-cors",headers:{"Content-Type":"text/plain"},body:JSON.stringify({secret:s,ticker:t,tickers:k,title:document.title,text:r.innerText,url:location.href})});alert("Sent to Thrive Alpha: "+(t||k.join(", ")||"auto-detect"));})();
```

## Use

While reading an article (e.g. an Investing Club piece):
1. Click the bookmarklet.
2. Press OK. Type a ticker only if the article is about one stock and none was detected.
3. Check the ticker's Verdict tab (Second opinions) or News a moment later.

## What happens to a clip

- **Tickers:** the one you typed, the article's quote links, and `(NASDAQ:AAPL)`-style mentions
  (`signals/club_extract.detect_tickers`). Each ticker gets its own copy of the clip (max 12).
- **Club view extraction** (when `ANTHROPIC_API_KEY` is set): Claude Haiku pulls, per ticker, the
  Club's 1/2/3 rating, price target, any trade (bought/sold/trimmed, shares, price), stance, up to
  3 thesis points and 2 risks, plus a 2-sentence summary (`signals/club_extract.py`). Only those
  fields and the summary are stored; the article text is dropped. Without the key, v1 behavior
  (text stored, generic card).
- **Where it shows:** a "CNBC Investing Club" row in Second opinions (label Buy / Wait for
  pullback / Don't buy / Trim, with PT and trade) for 120 days, and a Club card in News.
- **Tracking:** the nightly EOD row saves the Club label beside the other second opinions, so the
  Track tab scores Club calls against the same forward returns as ours. It does not feed the
  model; only consider that after months of tracked results.
- **Privacy:** clips stay in your backend's `DATA_ROOT/manual_catalysts.json`; nothing is shown
  publicly or redistributed.

## Known limitations

- **The shared secret lives in the bookmarklet's own source.** Its only protection is not sharing
  that bookmarklet text — an accepted tradeoff for a single-user personal tool.
- Clips are capped at 20 most recent per ticker (`manual_catalysts.MAX_ARTICLES_PER_TICKER`).
- Extraction can miss or misread a value; every Club row links back to the article.
