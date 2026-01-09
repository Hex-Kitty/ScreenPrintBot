# ScreenPrintBot

ScreenPrintBot is a Flask-based application that generates instant screen-printing quotes and branded PDF/email summaries for print shops.  
It is now at **v1.3.0** and live at [app.screenprintbot.com](https://app.screenprintbot.com).

---

## 🆕 What's New (v1.3.0) — Customer Portal Release

### Customer-Facing Quote Portal
- **Self-Service Quotes**: Customers can generate their own quotes 24/7 at `/quote/{tenant}`.
- **4-Step Wizard**: Quantity → Garment → Print Locations → Contact Info.
- **Real-Time Pricing**: Running total updates as customers make selections.
- **Supply-Own-Garments**: Toggle for print-only quotes when customer provides garments.
- **Automatic Emails**: Quote confirmation sent to customer + notification to shop.

### 2026 Pricing & 12-Color Support
- Updated all print pricing tiers to 2026 rates.
- Added 11-color and 12-color tiers (previously maxed at 10).
- Dynamic color limits per tenant (e.g., SWX: 12/12/4/4, Demo: 6/6/3/3).

### Per-Tenant Theming
- Portal supports dark/light mode per tenant.
- SWX: Light theme with red accents.
- Demo: Dark theme with cyan accents.
- 20+ CSS variables for full customization.

---

## 🆕 What's New (v1.2.0) — Production Hardening Release

### Security & Stability
- **Environment Validation**: App validates required env vars at startup with clear error messages.
- **Path Traversal Protection**: Tenant IDs validated to prevent directory escape attacks.
- **Session Cleanup**: Sessions now expire after 1 hour, preventing memory leaks.
- **HTTP Timeouts**: External API calls (Postmark) timeout after 30s instead of hanging.

### Input Validation
- **Quantity**: 1–100,000 range enforced server-side.
- **Colors**: 1–12 per placement, auto-clamped to config limits.
- **Email**: Format validated before sending.
- **Garment Cost**: $0–$100 for custom entries.

### API Improvements
- **Standardized Responses**: All endpoints return `{"ok": true/false, ...}` format.
- **Better Errors**: Validation failures return clear, actionable messages.
- **Calculation Logging**: Full quote breakdowns logged to `logs/chat.jsonl`.

---

## 🚀 Features

### QuickQuote Console (Shop-Facing)
- **Live quoting:** Instant garment + print pricing.  
- **Custom Garment Mode:** Enter any garment name and cost if not in presets.  
- **Upsell Items:** Add banners, stickers, sublimation, or DTF with size-based pricing.  
- **Extras Module:** Rush, fold & bag, names, numbers, heat press, tagging.  
- **Multi-location support:** Front, Back, Left Sleeve, Right Sleeve.  
- **Flexible color counts:** Config-driven, 1–12 colors.  
- **DTF Guardrail:** Suggests DTF when below per-shop screen-print minimum.  
- **Branded PDFs & Emails:** Includes shop logo, colors, and Postmark integration.

### Customer Portal (Customer-Facing)
- **Self-service quotes:** Customers generate quotes without shop interaction.
- **4-step wizard:** Guided flow with validation at each step.
- **Supply-own-garments:** Print-only pricing when customer provides blanks.
- **Mobile responsive:** Works on desktop, tablet, and phone.
- **Dual emails:** Customer receives quote, shop receives lead notification.

### Multi-Tenant Architecture
- **Per-shop configs:** Each shop defines garments, colors, markup, and upsell rates.
- **Theming:** Dark/light mode with custom accent colors per tenant.
- **Separate pricing:** Each tenant can have unique pricing tiers.

---

## ⚙️ Configuration

### Environment Variables

**Required:**
| Variable | Description |
|----------|-------------|
| `POSTMARK_TOKEN` | Postmark API server token |
| `FROM_EMAIL` | Email address to send from (e.g., `quote@screenprintbot.com`) |

**Optional:**
| Variable | Description | Default |
|----------|-------------|---------|
| `SHOP_BCC` | BCC email for shop owner | (empty) |
| `POSTMARK_STREAM` | Postmark message stream | `outbound` |
| `FLASK_DEBUG` | Enable debug mode | `0` |

### Local Development

1. Install dependencies:
   ```bash
   pip install -r requirements.txt
   pip install python-dotenv
   ```

2. Create `.env` file:
   ```
   POSTMARK_TOKEN=your_token_here
   FROM_EMAIL=quote@screenprintbot.com
   FLASK_DEBUG=1
   ```

3. Run:
   ```bash
   python app.py
   ```

4. Visit:
   - Console: `http://localhost:5050/console/demo`
   - Portal: `http://localhost:5050/quote/demo`

### Shop Configuration

See `/clients/demo/config.json` for an example of how shops define:  
- Branding (logo, colors, fonts)  
- Garment catalog + markup %  
- Screen charges and extras  
- Upsell items (labels, per-sqft rates, size limits)
- Max colors per placement
- Portal theme (dark/light mode)

#### Example: Max Colors Per Placement
```json
{
  "console": {
    "max_colors_per_placement": {
      "front": 12,
      "back": 12,
      "left_sleeve": 4,
      "right_sleeve": 4
    }
  }
}
```

#### Example: Portal Theme
```json
{
  "customer_portal": {
    "theme": {
      "mode": "light",
      "primary": "#EF4444",
      "accent": "#EF4444"
    },
    "notification_email": "orders@yourshop.com"
  }
}
```

---

## 🚢 Deployment (Render)

1. Push to GitHub:
   ```bash
   git add .
   git commit -m "v1.3.0: Customer portal release"
   git push origin main
   ```

2. Render auto-deploys from `main` branch.

3. Verify env vars are set in Render Dashboard → Environment.

4. Check logs for: `✔ Environment variables validated`

---

## 📁 Project Structure

```
├── app.py              # Main Flask application
├── clients/            # Per-tenant configurations
│   ├── demo/
│   │   ├── config.json
│   │   ├── pricing.json
│   │   └── faq.json
│   └── swx/
├── templates/          # Jinja2 templates
│   ├── console.html    # Shop-facing quote tool
│   ├── portal.html     # Customer-facing quote wizard
│   └── index.html      # Landing page
├── static/             # CSS, JS, logos
├── logs/               # Chat and calculation logs
├── requirements.txt
├── CHANGELOG.md
└── README.md
```

---

## 🔗 Routes

| Route | Description |
|-------|-------------|
| `/` | Landing page |
| `/console/{tenant}` | Shop-facing quote console |
| `/quote/{tenant}` | Customer-facing quote portal |
| `/api/quote/{tenant}` | Console quote API |
| `/api/customer-quote/{tenant}` | Portal quote submission API |

---

## 📝 License

Proprietary — ScreenPrintBot / Halftone Cat
