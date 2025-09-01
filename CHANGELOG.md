# Changelog

All notable changes to this project will be documented in this file.
This project follows [Semantic Versioning](https://semver.org/).

## [1.0.0] - 2025-09-01
### Added
- **Branding & UI**
  - New ScreenPrintBot brand (logo + palette).
  - Neutral theme for multi-tenant consoles (works with any shop brand).
  - “Demo / v1.0” badges and layout polish.
  - Mobile safety rail: content locked to right column on small screens.

- **Email**
  - Postmark integration (server token via `POSTMARK_TOKEN`).
  - Dedicated **Message Stream** (`outbound-estimates`) via `POSTMARK_STREAM`.
  - Template-driven estimate emails using alias **`quote_v1`**.
  - BCC support (`SHOP_BCC`).

- **Config & Theming**
  - JSON config supports `colors`, `ui`, `buttons`, `logo_scale`, etc.
  - Favicon pipeline (16/32/ico) served from `/static`.

- **Landing Page**
  - New SaaS-style hero + card layout.
  - Buttons aligned to brand palette, size/contrast tuned.

### Changed
- Render environment variables now documented in README.
- Safer email env usage + structured logging of Postmark responses.

### Known Limitations
- Persistent per-shop logging and export still pending.

---

## [0.3.0-beta] - 2025-08-29
### Added
- **Sidebar Breakdown Upgrade**: Garment, Ink/Print, and Extras now itemized with customer-facing pricing and per-placement details.
- **Dynamic Color Buttons**: Placement color counts now driven by config (`max_colors_per_placement`) with clean 1–10 layout (no more “6+”).
- **Per-Shop Minimum Quantities**: Configurable screen-print minimums per shop (e.g., 12 vs 48). If quantity is below min, console suggests DTF instead of quoting.
- **UI Polish**: Gray backgrounds on cards, clearer spacing, per-placement labels, and Beta 0.3 badge for tracking updates.

### Changed
- Fixed quoting math to align with pricing.json (e.g., 100 shirts: 1c = $1.68, 2c = $2.53).
- Refined breakdown to show garment markup price instead of shop cost.
- “Compute” button relabeled to **Quick Quote** for clarity.

### Known Limitations
- Email sending not yet implemented (Postmark integration planned).

---

## [0.2.0-beta] - 2025-08-25
### Added
- **QuickQuote Console MVP**: First live deploy to Render at `app.screenprintbot.com`.
- **Chat History on Index Page**: Scrollable conversation log so users can view their session inline.

### Changed
- Polished quoting flow with corrected order and min-qty warnings.
- Restored FAQ/greeting intents with improved normalization.
- Verified multi-user sessions running smoothly in production.

### Known Limitations
- Email sending not yet implemented (Postmark planned).
- Logging is minimal/ephemeral (no dashboard yet).

---

## [0.1.0-beta] - 2025-08-21
### Added
- Initial Render deployment prep (Starter plan to avoid cold starts).
- `clients/` directory with **demo** and **swx** configs (branding, FAQ, pricing).
- Multi-location quoting flow (front/back/left sleeve/right sleeve) and color counts.
- Branded PDF generation (ReportLab).
- Project housekeeping: `.gitignore`, repo rename to **ScreenPrintBot**.

### Changed
- Repository moved from `Bot` to `ScreenPrintBot` under Hex-Kitty org.
- Requirements pinned; Gunicorn confirmed as entry point (`gunicorn app:app`).

### Known Limitations (to be addressed soon)
- Email sending not yet implemented (Postmark planned).
- Logging is minimal/ephemeral (no dashboard yet).

---

## [Unreleased]
- Persistent per-shop logging and simple export.
- README/Docs expansion and screenshots.