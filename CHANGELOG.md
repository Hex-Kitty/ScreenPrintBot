# Changelog

All notable changes to this project will be documented in this file.  
This project follows [Semantic Versioning](https://semver.org/).

## [1.3.0] - 2026-01-09
### Added
- **Customer Portal (Phase 2)**
  - New customer-facing quote wizard at `/quote/{tenant}`.
  - 4-step flow: Quantity → Garment → Print Locations → Contact Info.
  - Real-time running total with sticky footer.
  - Mobile-responsive design with dark/light theme support.

- **Supply-Own-Garments Option**
  - Customers can skip garment selection for print-only quotes.
  - Toggle checkbox in Step 1 hides garment section when checked.
  - Properly handles $0 garment pricing in calculations.

- **2026 Pricing Update**
  - Updated print pricing tiers to 2026 rates.
  - Added 11-color and 12-color tiers (previously maxed at 10).
  - All 8 quantity brackets updated: 48-71, 72-143, 144-287, 288-575, 576-999, 1000-2499, 2500-4999, 5000+.

- **Dynamic Max Colors Per Placement**
  - Portal reads `max_colors_per_placement` from tenant config.
  - Each tenant can set different limits (e.g., SWX: 12/12/4/4, Demo: 6/6/3/3).
  - Fallback defaults if not configured.

- **Per-Tenant Theming**
  - Portal supports dark/light mode per tenant.
  - SWX: Light theme with red accents (#EF4444).
  - Demo: Dark theme with cyan accents (#06B6D4).
  - 20+ CSS variables for full theme customization.

- **Customer Quote Emails**
  - Automatic email to customer with quote summary.
  - Shop notification email with full details + reply-to customer.
  - Uses existing Postmark integration.

### Changed
- **Portal Config Helper**
  - `_get_portal_config()` now includes `max_colors_per_placement`.
  - Extras pricing read from tenant's `console.extras` config.
  - Garment catalog supports categories with nested items.

- **Location Breakdown Display**
  - Step 4 summary now shows individual location prices.
  - Sticky footer shows location-by-location breakdown.

### Fixed
- **Checkbox Click Bug**
  - Supply-own-garments checkbox now responds to direct clicks.
  - Added `event.stopPropagation()` to prevent double-toggle.

- **Config Path Resolution**
  - Portal correctly reads from `CONFIG.max_colors_per_placement` with fallback.

---

## [1.2.0] - 2026-01-07
### Added
- **Environment Variable Validation**
  - App now validates required env vars (`POSTMARK_TOKEN`, `FROM_EMAIL`) at startup.
  - Clear error messages if vars are missing instead of cryptic crashes later.
  - Uses `python-dotenv` for local development (`.env` file support).

- **Session Cleanup (Memory Leak Fix)**
  - Sessions now have timestamps and expire after 1 hour.
  - Automatic cleanup runs on every chatbot/console request.
  - Prevents unbounded memory growth in production.

- **Input Validation**
  - Quantity: 1–100,000 range enforced.
  - Colors: 1–12 range enforced per placement.
  - Email: Format validation before sending.
  - Garment cost: $0–$100 range for custom entries.
  - All validation returns consistent JSON error responses.

- **Calculation Logging**
  - Every console quote now logs full calculation breakdown to `logs/chat.jsonl`.
  - Includes garment, print, extras, screens, upsell, and totals.
  - Makes debugging pricing issues much easier.

- **Path Traversal Protection (Security)**
  - Tenant IDs now validated (alphanumeric + underscore + hyphen only).
  - Prevents `../../etc/passwd` style attacks on config loading.
  - Resolved paths verified to stay within `clients/` directory.

- **HTTP Timeout on External Calls**
  - Postmark API calls now timeout after 30 seconds.
  - Returns proper 503/504 errors instead of hanging forever.

### Changed
- **Standardized API Responses**
  - All errors now return `{"ok": false, "error": "..."}` format.
  - All successes now return `{"ok": true, ...}` format.
  - Consistent across all endpoints.

- **Default Debug Mode**
  - Changed default `FLASK_DEBUG` from `1` to `0` (secure by default).
  - Must explicitly enable debug mode for development.

- **Code Organization**
  - Added docstrings to all major functions.
  - Organized into logical sections with clear headers.
  - Improved type hints throughout.

### Fixed
- **Logging Typo**
  - Fixed `role.UPPER()` → `role.upper()` in log formatting.

- **404 Error Handler**
  - Now returns JSON `{"ok": false, "error": "Not found"}` instead of HTML.

- **Curly Quote Syntax Error**
  - Fixed fancy quotes in string literal that caused Python syntax error.

### Security
- Tenant validation prevents directory traversal attacks.
- JSON file loading restricted to known filenames (`faq`, `pricing`, `config`).
- Resolved paths verified against `clients/` directory boundary.

---

## [1.1.2] - 2025-09-21
### Added
- **Custom Garment Note**
  - Inline note beside custom garment input: *"Max price allowed is $100."* for clarity.

### Changed
- **Breakdown Labels**
  - Renamed *"Base Subtotal"* to *"Items Subtotal"* to avoid screen-printing jargon.
  - Totals reorganized: *Items Subtotal → Rush Fee → Subtotal (before tax)* appear together instead of under Extras.
  - Rush fee highlighted in **red** for better visibility.

### Fixed
- **Quantity Guardrail**
  - Limited max garment quantity input to **1000** (was 10,000).  
  - Prevents overflow when users accidentally enter an extra zero.
- **Email Estimate Layout**
  - HTML email output now mirrors console breakdown exactly (garments, placements, extras, upsells).
  - Resolved mismatch where email and console showed different subtotal order.
- **UI/Console Bugs**
  - Fixed minor input quirks with placement chips and number fields.
  - Polished spacing and consistency across breakdown display.

---

## [1.1.1] - 2025-09-15
### Added
- **FAQs Expansion**
  - Added new common questions to the FAQ module for better customer guidance.
  - Improved existing answers for clarity and consistency.
  - Synced updates so shops automatically pull in the expanded FAQ set.

### Fixed
- **Mobile Totals Panel**
  - Resolved bug where chips/buttons could scroll over the totals panel on mobile.
  - Totals bar now stays pinned above content using z-index + sticky positioning.
  - Added iOS-friendly fallback snippet for stubborn Safari builds.

---

## [1.1.0] - 2025-09-05
### Added
- **Custom Garment Entry**: New input box for garment label and cost, with clear button and mode badge.
- **Upsell Items Module**: Add-on products (Signs, Sublimation, Stickers, DTF) with width/height/qty, per-sqft pricing, and instant calculation.
- **Upsell in Estimates**: Upsell line items now appear separately in both live console and emailed estimates.
- **Price per Shirt Fix**: Now excludes upsell costs, showing true garment + print average.
- **Email Estimate Enhancements**: Postmark emails now match live console breakdown, including upsell items and per-shirt pricing.
- **Mobile/Responsive Layout**: Sidebar sticky behavior, stacked layout under 1024px, chip scrolling, and improved button spacing.

### Changed
- **Reset Behavior**: Resets all fields, including custom garment and upsell selections.
- **Breakdown Rendering**: Prints subtotal lines for printed shirts, upsells, and grand total.
- **Upsell Badge**: Shows the specific active upsell item instead of a generic label.
- **Screens Tooltip**: Cleaner init and dynamic label updates.

### Fixed
- Error handling when upsell dims are incomplete.
- Edge cases in subtotal and per-shirt calculation.
- Minor visual polish in breakdown and console.

---

## [1.0.0] - 2025-09-01
### Added
- **Branding & UI**
  - New ScreenPrintBot brand (logo + palette).
  - Neutral theme for multi-tenant consoles (works with any shop brand).
  - "Demo / v1.0" badges and layout polish.
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
- **Dynamic Color Buttons**: Placement color counts now driven by config (`max_colors_per_placement`) with clean 1–10 layout (no more "6+").
- **Per-Shop Minimum Quantities**: Configurable screen-print minimums per shop (e.g., 12 vs 48). If quantity is below min, console suggests DTF instead of quoting.
- **UI Polish**: Gray backgrounds on cards, clearer spacing, per-placement labels, and Beta 0.3 badge for tracking updates.

### Changed
- Fixed quoting math to align with pricing.json (e.g., 100 shirts: 1c = $1.68, 2c = $2.53).
- Refined breakdown to show garment markup price instead of shop cost.
- "Compute" button relabeled to **Quick Quote** for clarity.

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

### Known Limitations
- Email sending not yet implemented (Postmark planned).
- Logging is minimal/ephemeral (no dashboard yet).

---

## [Unreleased]
- Rate limiting on email endpoints.
- Redis session storage for multi-instance scaling.
- Admin dashboard for quote history and analytics.
