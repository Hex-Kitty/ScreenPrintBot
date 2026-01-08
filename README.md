# ScreenPrintBot

ScreenPrintBot is a Flask-based application that generates instant screen-printing quotes and branded PDF/email summaries for print shops.  
It is now at **v1.2.0** and live at [app.screenprintbot.com](https://app.screenprintbot.com).

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

### Developer Experience
- **`.env` Support**: Uses `python-dotenv` for local development.
- **Code Organization**: Docstrings, type hints, and logical sections throughout.
- **Debug Mode**: Now off by default (secure by default).

---

## 🆕 What's New (v1.1.2)
- **Quantity Guardrail**: Limited max quantity entry to **1000** to prevent overflow.
- **Custom Garment Note**: Inline note: *"Max price allowed is $100."*
- **Breakdown Clarity**: Renamed *"Base Subtotal"* to *"Items Subtotal"*; rush fee in **red**.
- **Email Estimate Sync**: HTML email now mirrors console breakdown exactly.

---

## 🆕 What's New (v1.1.1)
- **FAQs Expansion**: More common questions and refined answers.
- **Sticky Totals Fix (Mobile)**: Resolved overlap issue on mobile devices.

---

## 🆕 What's New (v1.1.0)
- **Custom Garment Entry**: Input box for garment label and cost.
- **Upsell Items Module**: Add-on products (Signs, Sublimation, Stickers, DTF).
- **Email Estimate Enhancements**: Postmark emails mirror live console breakdown.
- **Mobile/Responsive Layout**: Sidebar sticky behavior, stacked layout under 1024px.

---

## 🚀 Features
- **Live quoting:** Instant garment + print pricing.  
- **Custom Garment Mode:** Enter any garment name and cost if not in presets.  
- **Upsell Items:** Add banners, stickers, sublimation, or DTF with size-based pricing.  
- **Extras Module:** Rush, fold & bag, names, numbers, heat press, tagging.  
- **Multi-location support:** Front, Back, Left Sleeve, Right Sleeve.  
- **Flexible color counts:** Config-driven, 1–12 colors.  
- **DTF Guardrail:** Suggests DTF when below per-shop screen-print minimum.  
- **Branded PDFs & Emails:** Includes shop logo, colors, and Postmark integration.  
- **Responsive Design:** Works smoothly on desktop, tablet, and mobile.  
- **Config-driven:** Each shop defines garments, colors, markup, and upsell rates via `/clients/{shop}/config.json`.  

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

4. Visit: `http://localhost:5050/console/demo`

### Shop Configuration
See `/clients/demo/config.json` for an example of how shops define:  
- Branding (logo, colors, fonts)  
- Garment catalog + markup %  
- Screen charges and extras  
- Upsell items (labels, per-sqft rates, size limits)

---

## 🚢 Deployment (Render)

1. Push to GitHub:
   ```bash
   git add .
   git commit -m "v1.2.0: Production hardening release"
   git push origin main
   ```

2. Render auto-deploys from `main` branch.

3. Verify env vars are set in Render Dashboard → Environment.

4. Check logs for: `✓ Environment variables validated`

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
├── static/             # CSS, JS, logos
├── logs/               # Chat and calculation logs
├── requirements.txt
├── CHANGELOG.md
└── README.md
```

---

## 📝 License

Proprietary — ScreenPrintBot / Halftone Cat
