# ScreenPrintBot

ScreenPrintBot is a Flask-based application that generates instant screen-printing quotes and branded PDF summaries for print shops.  
It is currently in **beta** and being tested with Sportswear Express.

---

## 🆕 What’s New
- **QuickQuote Console Beta 0.3** adds per-placement Ink/Print cost breakdown, garment markup display, and itemized Extras.
- **Dynamic minimums**: Each shop’s config controls screen-print minimums (e.g., 12 vs 48). Quantities below min automatically advise DTF instead of quoting.
- **UI updates**: Gray placement cards, friendlier “Quick Quote” button, and subtle Beta badge for version tracking.
- See [CHANGELOG.md](./CHANGELOG.md) for full release notes.

---

## 🚀 Features
- Multi-location quoting (Front, Back, Left Sleeve, Right Sleeve).
- Flexible color count (1–8 colors).
- Client-specific branding via `config.json` (logo, colors, FAQs, pricing).
- Branded PDF generation with line items and totals.
- Ready for deployment on [Render](https://render.com).