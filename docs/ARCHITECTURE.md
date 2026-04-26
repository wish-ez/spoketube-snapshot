# Architecture

This document is a concise walkthrough of how Spoketube is structured. It is aimed at a reader who wants to understand the shape of the system in a few minutes without reading every file.

For the product-level summary, see the top-level `README.md`.

---

## 1. Application structure

The repository is organised into three Python packages plus the usual Django wiring:

- **`spoketube/`** — the Django project package.
  - `settings.py` — reads configuration either from an INI file (`dev/secrets`, for local development) or from environment variables (for the Elastic Beanstalk deployment). Wires up MySQL, Sphinx, AWS S3/CloudFront static storage, SES email, reCAPTCHA, and the YouTube API client.
  - `urls.py` — routes the root URL to `mainapp.urls`, mounts a custom admin site at `/icecrown/`, and serves `robots.txt` / `sitemap.xml`.
  - `storage.py` — two custom storage backends (`StaticToS3Storage`, `CachedS3Boto3Storage`) used by `django-storages` and `django-compressor` to push static assets to S3 while keeping a local cache for compression.
  - `wsgi.py` — standard Django WSGI entrypoint for Apache/mod_wsgi.

- **`mainapp/`** — the main Django app. Contains models, views, forms, admin, templates, static assets, and the search-related modules. This is where the web layer and the search layer live.

- **`data_parser/`** — a standalone Python package used both by the web app and by scheduled cron jobs. It contains the YouTube Data API client, the caption scraper, proxy handling helpers, and two cron entry points.

- **`.ebextensions/`** — Elastic Beanstalk configuration (Apache, SSL, HTTP→HTTPS redirect, cron, log directory, `collectstatic`/`compress` container commands).

- **`static/`, `templates/`** — project-level static assets and template roots, augmented by app-level ones under `mainapp/`.

---

## 2. Main domain entities

All models live in [`mainapp/models.py`](../mainapp/models.py).

- **`Channels`** — a YouTube channel. Stores identifiers, titles, subscriber counts, upload/privacy status, thumbnails, and a large set of YouTube-side metadata. Keyed by YouTube's `channelId`.

- **`Videos`** — a YouTube video. Stores identifiers, title, description, tags, caption availability and language, duration, publication date, view/like/dislike counts, thumbnails, and a `lxml_subtitle` text field for the captured caption document. Foreign-keyed to `Channels`. This model is the one that is also mirrored into a Sphinx real-time index (`sphinx = True`).

- **`DataApiQuotas`** — a ledger of YouTube Data API quota consumption. Each row is a charge, stamped with a timestamp. `DataApiQuotas.get_quotas_left()` and `get_quotas_used()` compute the current day's usage relative to YouTube's Pacific-time quota reset window, so ingestion jobs can refuse to start when they would blow through the daily budget.

- **`DataParserTasks`** — the queue of ingestion tasks. A task has a type drawn from a fixed set (`add_channel`, `update_channel`, `refresh_channel`, `add_video`, `update_video`, `get_missed_videos`), a payload (`task_item`), a human-readable title, timestamps, and a fatal-error flag.

- **`DataParserStatuses`** — the per-task status trail. One `DataParserTasks` task has many `DataParserStatuses` rows describing current state (`idle`, `work`, `error`, …), progress counters (items total / done / unavailable / without captions / errored), estimated quota cost, and free-form error details.

- **`Proxies`** — the caption-scraping proxy pool. Each row is one proxy endpoint with type/host/port and optional credentials, plus availability and captcha flags.

---

## 3. Search and data flow, at a high level

Two independent flows run in parallel: **write-side ingestion** and **read-side search**.

**Write-side (ingestion):**

1. An administrator uses the custom Django admin (mounted at `/icecrown/`) to queue a `DataParserTasks` row, e.g. "add this channel".
2. A cron job runs [`data_parser/parser_tasks_handler.py`](../data_parser/parser_tasks_handler.py) every minute. If there is no task in flight, it picks up the next `DataParserTasks` row and creates a matching `DataParserStatuses` row in the `work` state.
3. The handler calls the YouTube Data API via the `YouTubeAPI` client in [`data_parser/data_parser.py`](../data_parser/data_parser.py), estimates quota cost, charges `DataApiQuotas`, and rejects the task early if the remaining daily quota is insufficient.
4. For each video the handler fetches captions via the `CaptionParser`, rotating through `Proxies` rows to avoid YouTube rate limiting and captcha pages. Successful captions are stored in `Videos.lxml_subtitle` and mirrored into the Sphinx real-time index.
5. A second cron job ([`data_parser/cron_channels_updater.py`](../data_parser/cron_channels_updater.py)) runs daily to refresh channel-level statistics.

**Read-side (search):**

1. A user submits the search form (`mainapp/forms.py`) on the main page. Parameters include one or more of: speech phrase, title, description, tags, channel(s), date range, duration range, exact-match flag, ordering.
2. [`mainapp/views.py:search`](../mainapp/views.py) validates the form and builds a `SphinxSearchValues` object ([`mainapp/search_module.py`](../mainapp/search_module.py)). If channels were given by title, they are resolved to `channelId` values against the MySQL `Channels` table so that Sphinx can filter on them.
3. `SphinxSearchModule.get_videos_ids` composes a Sphinx QL query against the `videos` index and returns a page of matching video IDs.
4. `SphinxSearchModule.get_videos` hydrates those IDs with the ORM `Videos` rows and, for each hit, runs [`mainapp/speech_parser.py`](../mainapp/speech_parser.py) against the stored subtitle. The speech parser finds each occurrence of the stemmed user phrase, extracts a configurable window of words around it, and pairs every match with a timestamp so the UI can link directly to that moment in the video.
5. The view paginates the result, feeds it into `mainapp/templates/mainapp/search.html`, and renders.

There are also two AJAX endpoints that extend the same flow: `get_rest_matches` (load more speech matches for a video), `get_rest_channels` (load more channels on the landing page), and `autocomplete_channels` (typeahead for the channel filter).

---

## 4. External integrations

- **YouTube Data API v3** — used for channel and video metadata. The `YouTubeAPI` class wraps `googleapiclient` and also tracks per-call quota cost via `DataApiQuotas`.
- **YouTube caption endpoints** — captions are fetched by scraping the public caption URLs with `requests` + `lxml`, through the `Proxies` pool. This is what the `CaptionParser` in `data_parser/` does.
- **Sphinx** — accessed via the MySQL wire protocol through a thin `Connector` class. Used as the full-text search engine over subtitles and metadata.
- **AWS RDS (MySQL)** — primary application database, configured in `spoketube/settings.py`.
- **AWS S3 + CloudFront** — static asset hosting. Django-compressor produces compressed CSS/JS offline, which is then pushed to S3 via `StaticToS3Storage` (see `spoketube/storage.py`) and served through CloudFront.
- **AWS SES** — transactional email (admin notifications, the contact form).
- **Google reCAPTCHA** — protects the contact form.
- **Clicky** — lightweight web analytics, wired in via `django-analytical`.
