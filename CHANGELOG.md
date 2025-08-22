# Changelog

All notable changes to this project will be documented in this file.
This project follows [Semantic Versioning](https://semver.org/).

## [0.1.0-beta] - 2025-08-21
### Added
- Initial Render deployment prep (Starter plan to avoid cold starts).
- `clients/` directory with **demo** and **swx** configs (branding, FAQ, pricing).
- Multi‑location quoting flow (front/back/left sleeve/right sleeve) and color counts.
- Branded PDF generation (ReportLab).
- Project housekeeping: `.gitignore`, repo rename to **ScreenPrintBot**.

### Changed
- Repository moved from `Bot` to `ScreenPrintBot` under Hex‑Kitty org.
- Requirements pinned; Gunicorn confirmed as entry point (`gunicorn app:app`).

### Known Limitations (to be addressed soon)
- Email sending not yet implemented (Postmark planned).
- Logging is minimal/ephemeral (no dashboard yet).

---

## [Unreleased]
- Email sending via Postmark (`POSTMARK_TOKEN`, `SHOP_EMAIL`).
- Persistent per‑shop logging and simple export.
- README/Docs expansion and screenshots.