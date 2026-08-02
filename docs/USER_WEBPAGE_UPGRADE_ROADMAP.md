# User Webpage Upgrade Roadmap

Date: 2026-08-02

## Why this roadmap exists

The tenant-facing public website currently supports basic themed presentation plus fixed pages, but page content is structurally limited to title + plain body text. This roadmap adds only the highest-impact upgrades needed to make tenant websites feel credible, searchable, and conversion-ready without building a full CMS.

## Current-state summary

- Tenant page content model is flat (`title`, `navigation_label`, `body`, publish fields, meta fields).
- Tenant public page template renders a heading and `body|linebreaks`.
- Public event listing shows an empty-state string when there are no scheduled items.
- No implemented `robots.txt` or `sitemap.xml` URL handlers were found in runtime routes.
- Existing image processing and photo metadata support are strong and should be reused.

## Product decision first (required)

Choose one primary strategy before implementation:

1. **Dogfood-first:** use tenant pages as the marketing/demo experience and improve the page system directly.
2. **Split-stack:** keep `gatherhqs.com` as dedicated product marketing and use tenant pages only as customer-site demo.

Recommendation: Dogfood-first for credibility and faster product learning loops.

## Scope guardrails (MVP)

Ship only these section types for V1:

1. Hero section: image, headline, subheadline, one CTA label + URL.
2. Content section: heading, rich text, optional image, image alignment.
3. Logo/photo strip: 3-6 images with required alt text.
4. Reuse existing image handling pipeline and upload safeguards.

Explicitly out of scope:

- Full drag-and-drop builder
- Arbitrary custom HTML/script blocks
- Theme marketplace

## Delivery phases

## Phase 0 - SEO and crawlability foundations (1-2 days)

### Goals

- Ensure indexable public pages and explicit crawl rules.

### Work items

1. Add `robots.txt` route and template.
2. Add `sitemap.xml` route (tenant-aware and host-aware).
3. Include core public URLs: home, about, contact, newsletter, blog index/detail, calendar, event detail pages, photo albums.
4. Add canonical URL handling consistency checks in templates where missing.

### Acceptance criteria

- `GET /robots.txt` returns valid plaintext on public hosts.
- `GET /sitemap.xml` returns valid XML and only public/published resources.
- Search Console validation can be completed for production host(s).

## Phase 1 - Page section data model and rendering (2-4 days)

### Goals

- Move from plain `body` rendering to section-based pages while preserving existing content.

### Work items

1. Create section model(s), for example:
   - `PageSection` with `site`, `page`, `section_type`, `position`, `is_enabled`, shared presentation fields.
   - Optional per-type JSON payload field with strict server-side validation.
2. Add migration path:
   - Existing `SitePage.body` becomes a default content section for backward compatibility.
3. Update page rendering:
   - Replace single-body layout with section loop and per-type partial templates.
4. Preserve existing status/publish semantics from `SitePage`.

### Acceptance criteria

- Existing tenant pages continue to render after migration.
- New pages can render Hero + Content + Strip combinations.
- Mobile and desktop rendering passes baseline visual QA.

## Phase 2 - Editor experience for sections (2-4 days)

### Goals

- Enable non-technical managers to author sections quickly.

### Work items

1. Extend content management UI with:
   - Add/remove section controls
   - Reordering controls (up/down or drag handle backed by safe server update)
   - Section-type forms with validation
2. Reuse image processing (`prepare_image`, thumbnail behavior, format/size checks).
3. Add validations:
   - CTA URL format and protocol allowlist
   - Strip image count min/max
   - Required alt text for all strip images

### Acceptance criteria

- Managers can create and reorder all 3 MVP section types.
- Invalid section states are blocked with clear errors.
- Image uploads follow existing constraints and produce optimized assets.

## Phase 3 - Calendar credibility and lead capture (1-2 days)

### Goals

- Eliminate the “abandoned site” signal when no public events are scheduled.

### Work items

1. Replace hard empty-state copy with guided alternatives:
   - “No upcoming events yet” + CTA to newsletter signup and latest blog.
2. Seed a recurring platform-owned demo/training event visible publicly.
3. Add one low-price paid demo occurrence to validate visible payment flow.

### Acceptance criteria

- Public calendar never appears dead-end for first-time visitors.
- At least one recurring event appears in production demo tenant.
- Paid RSVP checkout path is verifiably live in demo.

## Phase 4 - Measurement and quality hardening (1-2 days)

### Goals

- Verify that upgrades improve discoverability and conversion.

### Work items

1. Add tests:
   - Section render coverage by type
   - Publish-state visibility for sectioned pages
   - `robots.txt` and `sitemap.xml` response tests
2. Track lightweight metrics:
   - Public page views
   - CTA clicks
   - Newsletter signups from public pages
   - Event RSVP starts/completions
3. Update docs and launch checklist.

### Acceptance criteria

- Automated tests cover the new public-page and SEO surface.
- Metrics are visible enough to compare before/after behavior.

## Suggested implementation mapping

- Content domain:
  - Extend models/forms/views in `content` app.
  - Add section partials in `templates/public/sections/`.
- Routing/domain:
  - Add SEO endpoints in `core` (or a dedicated SEO module).
  - Keep tenant host-awareness consistent with current request-site middleware behavior.
- Events/public credibility:
  - Update public calendar empty-state and seed content operations.

## Risks and mitigations

1. **Risk:** section schema complexity expands too fast.
   - **Mitigation:** lock to 3 section types and explicit field contracts.
2. **Risk:** migration breaks existing pages.
   - **Mitigation:** fallback render path from legacy `body` and staged rollout.
3. **Risk:** SEO endpoints leak non-public content.
   - **Mitigation:** strict filtering by published visibility and public-host constraints.

## Sequencing recommendation

1. Phase 0 first (crawl/index foundations).
2. Phase 1 and 2 next (actual page value).
3. Phase 3 immediately after (calendar trust signal).
4. Phase 4 to close with confidence.

## Definition of done for the whole upgrade

- Tenant home/about/contact/newsletter pages can be composed from MVP sections.
- Public pages are crawlable with valid `robots.txt` and `sitemap.xml`.
- Empty public calendar no longer reads as abandoned.
- At least one demo recurring event and one paid demo flow are live.
- Tests and docs are updated to protect the new behavior.