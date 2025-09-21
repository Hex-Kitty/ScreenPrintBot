# ScreenPrintBot

ScreenPrintBot is a Flask-based application that generates instant screen-printing quotes and branded PDF/email summaries for print shops.  
It is now at **v1.1.2** and live at [app.screenprintbot.com](https://app.screenprintbot.com).

---

## 🆕 What’s New (v1.1.2)
- **Quantity Guardrail**
  - Limited max quantity entry to **1000** to prevent overflow or accidental extra zeros.
- **Custom Garment Note**
  - Added inline note beside custom garment input: *“Max price allowed is $100.”*  
  - Prevents confusion if markup pushes numbers higher.
- **Breakdown Clarity**
  - Renamed *“Base Subtotal”* to *“Items Subtotal”* to avoid screen-printing jargon.  
  - Rush fee now highlighted in **red** for visibility.  
  - Totals reorganized: *Items Subtotal → Rush Fee → Subtotal (before tax)* grouped at the top of breakdown instead of Extras.
- **Email Estimate Sync**
  - HTML email output now mirrors console breakdown exactly (garments, placements, extras, upsells).  
  - Consistent grouping/order ensures console and emails are identical.
- **UI Polish**
  - Fixed placement chips and number field quirks.  
  - Minor spacing/consistency fixes across breakdown panels.

---

## 🆕 What’s New (v1.1.1)
- **FAQs Expansion**
  - Added more common questions and refined answers for better customer support.
  - Console now pulls from the updated FAQ set automatically.
- **Sticky Totals Fix (Mobile)**
  - Resolved overlap issue where chips/buttons could scroll over the totals panel.
  - Totals bar now stays pinned above content using z-index + sticky positioning.
  - Includes an iOS-friendly fallback for Safari edge cases.

---

## 🆕 What’s New (v1.1.0)
- **Custom Garment Entry**
  - Input box for garment label and cost, with clear button and mode badge.
  - Switches between preset garment mode and custom garment mode automatically.
- **Upsell Items Module**
  - Add-on products (Signs, Sublimation, Stickers, DTF).
  - Width/height/qty inputs with per-sqft pricing.
  - Totals are displayed separately in console and emails.
- **Upsell in Estimates**
  - Upsells excluded from “price per shirt” math.
  - Now shown as their own section in breakdown + emails.
- **Email Estimate Enhancements**
  - Postmark emails mirror live console breakdown.
  - Includes upsell line items and per-shirt pricing.
- **Mobile/Responsive Layout**
  - Sidebar sticky behavior.
  - Stacked layout under 1024px.
  - Chip scrolling and improved button spacing.
- **Reset Behavior**
  - Resets all fields including custom garment and upsell selections.
- **UI/UX Polish**
  - Active upsell badge shows the specific item instead of generic “Upsell”.
  - Cleaner screens tooltip and label updates.

---

## 🚀 Features
- **Live quoting:** Instant garment + print pricing.  
- **Custom Garment Mode:** Enter any garment name and cost if not in presets.  
- **Upsell Items:** Add banners, stickers, sublimation, or DTF with size-based pricing.  
- **Extras Module:** Rush, fold & bag, names, numbers, heat press, tagging.  
- **Multi-location support:** Front, Back, Left Sleeve, Right Sleeve.  
- **Flexible color counts:** Config-driven, 1–10 colors.  
- **DTF Guardrail:** Suggests DTF when below per-shop screen-print minimum.  
- **Branded PDFs & Emails:** Includes shop logo, colors, and Postmark integration.  
- **Responsive Design:** Works smoothly on desktop, tablet, and mobile.  
- **Config-driven:** Each shop can define its own garments, colors, markup, and upsell rates via `/clients/{shop}/config.json`.  

---

## ⚙️ Configuration
See `/clients/demo/config.json` for an example of how shops define:  
- Branding (logo, colors, fonts)  
- Garment catalog + markup %  
- Screen charges and extras  
- Upsell items (labels, per-sqft rates, size limits)  