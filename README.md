# ScreenPrintBot

ScreenPrintBot is a Flask-based application that generates instant screen-printing quotes and branded PDF/email summaries for print shops.  
It is now at **v1.0.0** and live at [app.screenprintbot.com](https://app.screenprintbot.com).

---

## 🆕 What’s New (v1.0.0)
- **Branding & UI**
  - New ScreenPrintBot identity (logo + favicon + neutral theme).
  - Per-shop branding via JSON config (logos, colors, markup).
  - Cleaner console badges (`DEMO`, `v1.0`), tuned spacing and layouts.
  - Mobile polish: console stacks properly on narrow screens.

- **Email Estimates**
  - Integrated with [Postmark](https://postmarkapp.com/).
  - Dedicated message stream (`outbound-estimates`).
  - Template-driven estimates (alias: `quote_v1`).
  - Includes shop BCC option (`SHOP_BCC`).
  - Logs Postmark response codes for debugging.

- **Landing Page**
  - SaaS-style hero with CTA.
  - Tenant cards with logos, demo chatbot link, and QuickQuote Console link.
  - Unified button styles across site.

---

## 🚀 Features
- Multi-location quoting (Front, Back, Left Sleeve, Right Sleeve).
- Flexible color counts (1–10, config-driven).
- Per-shop minimums (screen-print vs DTF guardrail).
- Branded PDF generation with line items and totals.
- Configurable UI (colors, button styles, logos).
- Estimate delivery via **Postmark email templates**.
- Ready for deployment on [Render](https://render.com).

---

## ⚙️ Configuration
Each shop is defined by a JSON config in `/clients/`:

```json
{
  "id": "demo",
  "name": "ScreenPrintBot",
  "logo": "/static/logos/demo.png",
  "colors": {
    "accent": "#0d9488"
  },
  "buttons": {
    "bg": "#0d9488"
  },
  "pricing": "pricing_demo.json",
  "min_qty": 48,
  "bcc": "shop@example.com"
}