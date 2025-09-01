import os, json, re, time, random, io, requests
from typing import Optional, Tuple, Dict, Any, List
from flask import Flask, request, jsonify, render_template, abort, redirect, url_for, make_response

APP_ROOT = os.path.dirname(__file__)
CLIENTS_DIR = os.path.join(APP_ROOT, "clients")

app = Flask(__name__)

import time
BOOT_TS = time.strftime("%Y-%m-%d %H:%M:%S")

@app.get("/__version")
def __version():
    return {"ok": True, "boot": BOOT_TS}

@app.get("/api/ping")
def api_ping():
    return {"ok": True, "pong": True}

@app.route("/api/email-estimate", methods=["POST"])
def email_estimate():
    data = request.get_json(silent=True) or {}
    customer_email = data.get("customer_email")
    subject = data.get("subject", "Your Estimate from QuickQuote Console")
    html_body = data.get("html_body", "<p>This is a test estimate.</p>")
    text_body = data.get("text_body", "This is a test estimate.")

    if not customer_email:
        return jsonify({"ok": False, "error": "Missing customer_email"}), 400

    payload = {
        "From": os.environ["FROM_EMAIL"],
        "To": customer_email,
        "Bcc": os.environ.get("SHOP_BCC", ""),
        "Subject": subject,
        "HtmlBody": html_body,
        "TextBody": text_body,
    }

    headers = {
        "Accept": "application/json",
        "Content-Type": "application/json",
        "X-Postmark-Server-Token": os.environ["POSTMARK_TOKEN"],
    }

    # Call Postmark and be defensive about response format
    r = requests.post("https://api.postmarkapp.com/email", json=payload, headers=headers)

    try:
        body = r.json()
    except Exception:
        body = {"raw": r.text}

    # Log to Render logs for visibility
    print("POSTMARK status:", r.status_code)
    print("POSTMARK body:", body)

    return jsonify(body), r.status_code


# Trust Render/Proxy headers for correct client IP/proto
from werkzeug.middleware.proxy_fix import ProxyFix
app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1)

# ---------------- Feature flags ----------------
FORCE_WIZARD = os.getenv("FORCE_WIZARD", "false").lower() == "true"

# =========================
# >>> LOGGING PATCH START
# =========================
import uuid, logging, sys, json as _json_mod, re as _re_mod, os as _os_mod
from datetime import datetime
from logging.handlers import TimedRotatingFileHandler
from typing import Optional as _Optional, Dict as _Dict, Any as _Any
from flask import request as _flask_request

LOG_ENABLED: bool = True
LOG_DIR: str = "logs"
LOG_REDACT: bool = True

logger_json = None
logger_txt = None
if LOG_ENABLED:
    os.makedirs(LOG_DIR, exist_ok=True)

    # File handler for JSON logs
    json_handler = TimedRotatingFileHandler(
        filename=os.path.join(LOG_DIR, "chat.jsonl"),
        when="midnight",
        backupCount=7,
        encoding="utf-8",
        utc=True,
    )
    json_handler.setLevel(logging.INFO)
    logger_json = logging.getLogger("chat.json")
    logger_json.setLevel(logging.INFO)
    logger_json.addHandler(json_handler)

    # File handler for text logs
    txt_handler = TimedRotatingFileHandler(
        filename=os.path.join(LOG_DIR, "chat.txt"),
        when="midnight",
        backupCount=7,
        encoding="utf-8",
        utc=True,
    )
    txt_handler.setLevel(logging.INFO)
    txt_formatter = logging.Formatter(
        "[%(asctime)sZ] %(message)s", datefmt="%Y-%m-%d %H:%M:%S"
    )
    txt_handler.setFormatter(txt_formatter)
    logger_txt = logging.getLogger("chat.txt")
    logger_txt.setLevel(logging.INFO)
    logger_txt.addHandler(txt_handler)

    # Console handler (shows up in Render Logs) — attach to ONE logger to avoid dupes
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(logging.INFO)
    if logger_txt:
        logger_txt.addHandler(console_handler)
    # (Optional) if you prefer JSON in console, attach to logger_json instead of logger_txt.

EMAIL_RE = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")
PHONE_RE = re.compile(r"\+?\d[\d\-\s().]{7,}\d")

def _redact(text: str) -> str:
    if not text or not LOG_REDACT:
        return text or ""
    text = EMAIL_RE.sub("[email redacted]", text)
    text = PHONE_RE.sub("[phone redacted]", text)
    return text

def log_turn(session_id: str, role: str, message: str, meta: Optional[Dict[str, Any]] = None) -> None:
    if not LOG_ENABLED:
        return
    ts = datetime.utcnow().isoformat(timespec="seconds") + "Z"
    safe_msg = _redact(message or "")
    entry = {
        "ts": ts,
        "session_id": session_id,
        "tenant": (meta or {}).get("tenant"),
        "ip": request.headers.get("X-Forwarded-For", request.remote_addr),
        "route": request.path,
        "ua": request.headers.get("User-Agent", ""),
        "role": role,
        "message": safe_msg,
        "meta": meta or {},
    }
    if logger_json:
        logger_json.info(_json_mod.dumps(entry, ensure_ascii=False))
    if logger_txt:
        sid_short = (session_id or "")[:8]
        tenant = (meta or {}).get("tenant") or "-"
        logger_txt.info(f"{tenant} {sid_short} {role.UPPER() if hasattr(role,'UPPER') else role.upper()}: {safe_msg}")
# =========================
# >>> LOGGING PATCH END
# =========================

# ---------- stable session id via cookie ----------
def _get_sid() -> str:
    sid = request.cookies.get("sid")
    if not sid:
        sid = uuid.uuid4().hex[:16]
    return sid

# ---------- small JSON cache with mtime ----------
_json_cache: Dict[Tuple[str, str], Dict[str, Any]] = {}
def _load_json(tenant: str, name: str) -> Any:
    path = os.path.join(CLIENTS_DIR, tenant, f"{name}.json")
    if not os.path.isfile(path):
        abort(404, f"{name}.json not found for tenant '{tenant}'")
    mtime = os.path.getmtime(path)
    key = (tenant, name)
    cached = _json_cache.get(key)
    if cached and cached["mtime"] == mtime:
        return cached["data"]
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)
    _json_cache[key] = {"data": data, "mtime": mtime}
    return data

def _load_all(tenant: str) -> Dict[str, Any]:
    return {
        "faq": _load_json(tenant, "faq"),
        "pricing": _load_json(tenant, "pricing"),
        "config": _load_json(tenant, "config"),
    }

# ---------- parsing helpers ----------
_WORDS = re.compile(r"\b\w+\b", re.IGNORECASE)

def _normalize(text: str) -> str:
    t = text.lower()
    t = re.sub(r"[^\w\s]", " ", t)
    t = re.sub(r"\s+", " ", t).strip()
    return t

_NUMBER_WORDS = {
    "one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6,
    "seven": 7, "eight": 8, "nine": 9, "ten": 10, "eleven": 11, "twelve": 12
}

def extract_quantity_and_colors(msg: str) -> Tuple[Optional[int], Optional[int]]:
    """Legacy single-location helper. Kept for FAQ and fallback answers."""
    text = msg.lower()

    colors: Optional[int] = None
    colors_pat = re.compile(
        r"(?:(\d+)|(" + "|".join(_NUMBER_WORDS.keys()) + r"))\s*[- ]*(?:color|colors|colour|colours|c|clr|clrs)\b"
    )
    m_col = colors_pat.search(text)
    if m_col:
        colors = int(m_col.group(1)) if m_col.group(1) else _NUMBER_WORDS.get(m_col.group(2), None)

    qty: Optional[int] = None
    m_qty1 = re.search(
        r"(\d+)\s*(?:t-?shirt|tshirt|t-?shirts|tshirts|tee|tees|shirt|shirts|piece|pieces|pc|pcs)\b",
        text
    )
    if m_qty1:
        qty = int(m_qty1.group(1))
    if qty is None:
        m_qty2 = re.search(r"(?:qty|quantity)\s*[:\-]?\s*(\d+)\b", text)
        if m_qty2:
            qty = int(m_qty2.group(1))

    if qty is None or colors is None:
        nums = [int(n) for n in re.findall(r"\d+", text)]
        if nums:
            color_candidates = [n for n in nums if 1 <= n <= 12]
            qty_candidates = [n for n in nums if n not in color_candidates] or nums
            if qty is None and qty_candidates:
                qty = max(qty_candidates)
            if colors is None and color_candidates:
                colors = color_candidates[0]

    if colors is None:
        if re.search(r"\b\d+\b", text):
            for w, val in _NUMBER_WORDS.items():
                if re.search(rf"\b{w}\b", text):
                    colors = val
                    break

    return qty, colors

# ---------- NEW: multi-location freeform parsing ----------
_LOC_ALIASES = {
    "front": "front",
    "back": "back",
    "left sleeve": "left_sleeve",
    "right sleeve": "right_sleeve",
    "sleeve": "left_sleeve",
    "sleeves": "sleeves",   # expands to both
    "left": "left_sleeve",
    "right": "right_sleeve",
    "pocket": "pocket",
}

def _label_for(loc: str) -> str:
    return {"left_sleeve":"Left Sleeve", "right_sleeve":"Right Sleeve"}.get(loc, loc.replace("_"," ").title())

def _detect_quantity(text: str) -> Optional[int]:
    t = text.lower()
    m = re.search(r"(\d+)\s*(?:t-?shirt|tshirt|t-?shirts|tshirts|tee|tees|shirt|shirts|piece|pieces|pc|pcs)\b", t)
    if m: return int(m.group(1))
    m2 = re.search(r"(?:qty|quantity)\s*[:\-]?\s*(\d+)\b", t)
    if m2: return int(m2.group(1))
    nums = [int(n) for n in re.findall(r"\b\d+\b", t)]
    return max(nums) if nums else None

def _expand_sleeves(loc: str) -> List[str]:
    if loc == "sleeves":
        return ["left_sleeve", "right_sleeve"]
    if loc == "sleeve":
        return ["left_sleeve"]  # assume left if singular/ambiguous
    return [loc]

def _parse_freeform_request(user_message: str, cfg: dict) -> Dict[str, Any]:
    text = user_message.lower()
    result: Dict[str, Any] = {"quantity": _detect_quantity(text), "locations": [], "global_colors": None}

    pat_after = re.compile(r"(\d{1,2})\s*c(?:olors?)?\s*(front|back|left sleeve|right sleeve|sleeves?|pocket)\b")
    pat_before = re.compile(r"(front|back|left sleeve|right sleeve|sleeves?|pocket)\s*(\d{1,2})\s*c(?:olors?)?\b")

    consumed = []

    for m in pat_after.finditer(text):
        c = int(m.group(1))
        loc_key = _LOC_ALIASES.get(m.group(2), m.group(2).replace(" ","_"))
        for loc in _expand_sleeves(loc_key):
            result["locations"].append({"location": loc, "colors": min(c, int((cfg or {}).get("printing", {}).get("max_colors", 12)))})
        consumed.append((m.start(), m.end()))

    for m in pat_before.finditer(text):
        c = int(m.group(2))
        loc_key = _LOC_ALIASES.get(m.group(1), m.group(1).replace(" ","_"))
        for loc in _expand_sleeves(loc_key):
            result["locations"].append({"location": loc, "colors": min(c, int((cfg or {}).get("printing", {}).get("max_colors", 12)))})
        consumed.append((m.start(), m.end()))

    has_front_back = re.search(r"\bfront\s*(?:\+|&|and|\/)\s*back\b", text)
    if has_front_back and not any(l["location"] in {"front","back"} for l in result["locations"]):
        result["locations"].extend([{"location":"front","colors":None},{"location":"back","colors":None}])

    for name, norm in [("front","front"),("back","back"),("left sleeve","left_sleeve"),("right sleeve","right_sleeve"),("pocket","pocket"),("sleeves","sleeves")]:
        if re.search(rf"\b{name}\b", text) and not any(l["location"] in _expand_sleeves(norm) for l in result["locations"]):
            for loc in _expand_sleeves(norm):
                result["locations"].append({"location": loc, "colors": None})

    pruned = []
    last = 0
    for s, e in sorted(consumed):
        pruned.append(text[last:s])
        last = e
    pruned.append(text[last:])
    remainder = " ".join(pruned)

    m_global = re.search(r"\b(\d{1,2})\s*c(?:olors?)?\b", remainder)
    if m_global:
        result["global_colors"] = int(m_global.group(1))

    seen = set()
    deduped = []
    for ent in result["locations"]:
        key = ent["location"]
        if key in seen:
            idx = next((i for i, d in enumerate(deduped) if d["location"] == key), None)
            if idx is not None and deduped[idx]["colors"] is None and ent["colors"] is not None:
                deduped[idx]["colors"] = ent["colors"]
            continue
        seen.add(key)
        deduped.append(ent)
    result["locations"] = deduped

    return result

# ---------- FAQ helpers ----------
def get_faq_items(payload: Dict[str, Any]) -> List[Dict[str, Any]]:
    items = payload.get("faqs") or payload.get("faq") or []
    clean: List[Dict[str, Any]] = []
    for it in items:
        if not isinstance(it, dict): continue
        if "_comment" in it: continue
        clean.append(it)
    return clean

def get_faq_match(faq_list: List[Dict[str, Any]], user_message: str) -> Optional[Dict[str, Any]]:
    text = _normalize(user_message)
    for item in faq_list:
        triggers = item.get("triggers") or item.get("tags") or []
        if isinstance(triggers, str):
            triggers = [triggers]
        norm_triggers = [_normalize(t) for t in triggers if isinstance(t, str)]
        if any(trig in text for trig in norm_triggers):
            return item
    return None

# ---------- pricing / quoting (single-location legacy) ----------
def price_quote(pricing: dict, quantity: int, colors: int) -> Optional[str]:
    try:
        sp = pricing["screen_print"]
        base = float(sp.get("garment_base", 0.0))
        min_qty = int(sp.get("min_qty", 1))
        max_qty = int(sp.get("max_qty", 10**9))
        tiers = sp["tiers"][f"{colors}_color"]
    except Exception:
        return None

    if quantity < min_qty:
        alt = pricing.get("alt_small_order_message",
                          f"Sorry, our minimum for screen printing is {min_qty}. For smaller orders we recommend DTF transfers.")
        return alt

    if quantity > max_qty:
        return f"That's a big order! For {quantity} pieces and {colors} color(s), please contact us for a custom quote so we can give you the best bulk rate."

    def _split_band(band: str) -> Tuple[int, Optional[int]]:
        b = band.replace("–", "-").strip()
        if "+" in b:
            lo = int(b.replace("+", "").strip())
            return lo, None
        lo, hi = [int(x) for x in b.split("-")]
        return lo, hi

    for band, print_price in tiers.items():
        lo, hi = _split_band(str(band))
        if (hi is None and quantity >= lo) or (hi is not None and lo <= quantity <= hi):
            pp = float(print_price) + base
            total = pp * quantity
            return (f"For {quantity} pieces with {colors} color(s), it's ${pp:.2f} per piece "
                    f"(incl. {base:.2f} garment). Estimated total: ${total:.2f}.")
    return None

def get_pricing_response(pricing_data: dict, user_message: str) -> Optional[str]:
    words = set(_WORDS.findall(user_message.lower()))
    pricing_intent = {"price", "pricing", "quote", "cost", "how", "much"}
    if words & pricing_intent:
        qty, cols = extract_quantity_and_colors(user_message)
        if qty is None or cols is None:
            need = []
            if qty is None: need.append("quantity")
            if cols is None: need.append("number of colors")
            return f"Happy to quote! I just need the {', '.join(need)}."
        return price_quote(pricing_data, qty, cols)

    qty, cols = extract_quantity_and_colors(user_message)
    if qty and cols:
        return price_quote(pricing_data, qty, cols)
    return None

# ---------- branch support state ----------
PENDING_BRANCH: Dict[Tuple[str, str], Dict[str, Any]] = {}

def _respond(message: str, buttons: Optional[List[Dict[str,str]]] = None, extra: Optional[Dict[str,Any]] = None) -> Dict[str, Any]:
    if buttons:
        payload = {
            "type": "branch",
            "prompt": message,
            "options": [{"label": b.get("label","Option"), "value": b.get("value", b.get("label","Option"))} for b in buttons],
            "reply": message,
            "answer": message,
        }
    else:
        payload = {"type": "answer", "reply": message, "answer": message}
    if extra:
        payload.update(extra)
    return payload

# Session store for quote flow (keyed by tenant + sid)
QUOTE_SESSIONS: Dict[Tuple[str,str], Dict[str,Any]] = {}

# --- Config + policy helpers ---
def _shop_max_colors(cfg: dict) -> int:
    pr = (cfg or {}).get("printing", {}) or {}
    return int(pr.get("max_colors") or 6)

def _shop_placements(cfg: dict) -> List[str]:
    pr = (cfg or {}).get("printing", {}) or {}
    return list(pr.get("placements") or ["front","back","left_sleeve","right_sleeve"])

def _small_order_policy(cfg: dict) -> Dict[str, str]:
    ui = (cfg or {}).get("ui", {}) or {}
    so = ui.get("small_order", {}) or {}
    suggest = (so.get("suggest") or ("dtf" if ui.get("dtf_enabled", True) else "none")).lower()
    return {
        "suggest": suggest,
        "link": so.get("link"),
        "label": so.get("label") or ("DTF transfers" if suggest=="dtf" else ("Embroidery" if suggest=="embroidery" else "")),
        "cta_get": so.get("cta_get") or ("Get DTF Quote" if suggest=="dtf" else ("Get Embroidery Quote" if suggest=="embroidery" else "")),
        "cta_alt": so.get("cta_alt") or "Change Quantity"
    }

# --- helper: start new session / reset ---
def _start_new_quote_session(tenant: str, sid: str) -> Dict[str, Any]:
    QUOTE_SESSIONS[(tenant, sid)] = {
        "step":"ask_qty",
        "quantity":None,
        "locations":[],
        "tier":None,
        "pending":{"location":None,"colors":None}
    }
    pricing = _load_json(tenant,"pricing")
    return _respond("How many shirts?", _qty_buttons_from_pricing(pricing), {"state":{"step":"ask_qty"}})

def _start_prefilled_session(tenant: str, sid: str, cfg: dict, quantity: int, locations: List[Dict[str,int]]) -> Dict[str, Any]:
    QUOTE_SESSIONS[(tenant, sid)] = {
        "step":"ask_more",
        "quantity":quantity,
        "locations": locations[:],
        "tier":None,
        "pending":{"location":None,"colors":None}
    }
    return _respond("Add another print location?", [{"label":"Yes","value":"yes"},{"label":"No","value":"no"}], {"state":{"step":"ask_more"}})

# --- Quantity buttons from pricing tiers (+ 12/24 first) ---
def _qty_buttons_from_pricing(pricing: dict) -> List[Dict[str,str]]:
    try:
        one_color = pricing["screen_print"]["tiers"]["1_color"]
    except Exception:
        return [{"label": x, "value": x} for x in ["12","24","48","72","100","200","250","300"]]

    def lb(k: str) -> int:
        b = str(k).replace("–","-")
        if "+" in b:
            return int(b.replace("+", "").split("-")[0])
        return int(b.split("-")[0])

    keys = list(one_color.keys())
    keys.sort(key=lb)

    buttons = ["12","24"]
    for k in keys:
        b = str(k).replace("–","-").strip()
        low = lb(b)
        label = f"{low}+" if "+" in b else str(low)
        if label not in buttons:
            buttons.append(label)

    return [{"label": x, "value": x} for x in buttons]

# --- Placement & Color buttons ---
def _placement_buttons(cfg: dict, chosen: List[Dict[str,Any]]) -> List[Dict[str,str]]:
    picked = {p["location"] for p in chosen}
    allowed = _shop_placements(cfg)
    opts = []
    for loc in allowed:
        if loc in picked:
            continue
        opts.append({"label": _label_for(loc), "value": f"placement:{loc}"})
    opts.append({"label":"Custom…","value":"custom_location"})
    return opts

def _color_buttons(cfg: dict) -> List[Dict[str,str]]:
    maxc = _shop_max_colors(cfg)
    labels = [f"{i}c" for i in range(1, min(maxc,6)+1)]
    if maxc > 6:
        labels.append(f"7–{maxc}c")
    return [{"label": l, "value": l.replace("–","-")} for l in labels]

# --- Garment tier buttons ---
def _tier_buttons(cfg: dict):
    garments = (cfg or {}).get("garments", {}) or {}
    tiers_enabled = bool(garments.get("tiers_enabled"))
    tiers = (garments.get("tiers", {}) or {})
    if not tiers_enabled or not tiers:
        return None
    preferred_order = ["good", "better", "best"]
    ordered_keys = [k for k in preferred_order if k in tiers] + [k for k in tiers.keys() if k not in preferred_order]
    btns = []
    for k in ordered_keys:
        meta = tiers.get(k, {}) or {}
        label = meta.get("label", k.title())
        bp = float(meta.get("blank_price", 0.0))
        btns.append({"label": f"{label} (${bp:.2f})", "value": k})
    return btns

# pricing lookups (supports "5000+")
def _run_charge_per_shirt(pricing: dict, qty: int, colors: int) -> Optional[float]:
    try:
        tiers = pricing["screen_print"]["tiers"][f"{colors}_color"]
    except Exception:
        return None
    for band, price in tiers.items():
        b = str(band).replace("–","-").strip()
        if "+" in b:
            lo = int(b.replace("+", "").split("-")[0])
            if qty >= lo:
                return float(price)
        else:
            lo, hi = [int(x) for x in b.split("-")]
            if lo <= qty <= hi:
                return float(price)
    return None

# blank price: tiers → single → garment_base
def _blank_price_from_config_or_pricing(cfg: dict, pricing: dict, chosen_tier: Optional[str]) -> float:
    garments = (cfg or {}).get("garments", {}) or {}
    if garments.get("tiers_enabled") and chosen_tier:
        tier = garments.get("tiers", {}).get(chosen_tier)
        if tier:
            return float(tier.get("blank_price", 0.0))
    if "single_blank_price" in garments:
        return float(garments.get("single_blank_price", 0.0))
    try:
        return float(pricing.get("screen_print", {}).get("garment_base", 0.0))
    except Exception:
        return 0.0

# Money helpers
from decimal import Decimal, ROUND_HALF_UP, getcontext
getcontext().prec = 9
_CENTS = Decimal("0.01")
def _money(x: Decimal) -> Decimal:
    return x.quantize(_CENTS, rounding=ROUND_HALF_UP)

# --------- NEW HELPERS: caps from config & pricing ----------
def _per_loc_color_cap(cfg: dict, loc: str) -> Optional[int]:
    """Per-placement cap from console.max_colors_per_placement, else printing.max_colors, else console.max_colors."""
    c = (cfg or {}).get("console", {}) or {}
    per = c.get("max_colors_per_placement") or {}
    if isinstance(per, dict) and loc in per and per[loc] is not None:
        try:
            return int(per[loc])
        except Exception:
            pass
    pr = (cfg or {}).get("printing", {}) or {}
    if pr.get("max_colors") is not None:
        try:
            return int(pr.get("max_colors"))
        except Exception:
            pass
    if c.get("max_colors") is not None:
        try:
            return int(c.get("max_colors"))
        except Exception:
            pass
    return None  # fall back later if needed

def _max_colors_from_pricing(pricing: dict) -> int:
    tiers = (pricing or {}).get("screen_print", {}).get("tiers", {}) or {}
    maxc = 0
    for k in tiers.keys():
        m = re.match(r"(\d+)_color$", str(k))
        if m:
            try:
                maxc = max(maxc, int(m.group(1)))
            except Exception:
                pass
    return maxc or 12

def _apply_color_caps(cfg: dict, pricing: dict, qty: int, locs: List[Dict[str,int]]) -> Tuple[List[Dict[str,int]], bool]:
    """Clamp colors per placement to (per-placement cap) and (pricing max tier). Returns (new_locs, any_clamped)."""
    pricing_cap = _max_colors_from_pricing(pricing)
    any_clamped = False
    out: List[Dict[str,int]] = []
    for spec in locs:
        loc = spec.get("location", "")
        colors = int(spec.get("colors") or 0)
        if colors <= 0:
            continue
        per_cap = _per_loc_color_cap(cfg, loc) or _shop_max_colors(cfg)
        new_colors = max(1, min(colors, per_cap, pricing_cap))
        if new_colors != colors:
            any_clamped = True
        out.append({"location": loc, "colors": new_colors})
    return out, any_clamped
# ------------------------------------------------------------

def _compute_quote_total(pricing: dict, cfg: dict, quantity: int, locations: List[Dict[str,int]], chosen_tier: Optional[str]) -> Optional[Dict[str,Any]]:
    sp = pricing.get("screen_print", {})
    min_qty = int(sp.get("min_qty", 1))
    max_qty = int(sp.get("max_qty", 10**9))
    if quantity < min_qty:
        msg = pricing.get("alt_small_order_message",
                          f"Sorry, our minimum for screen printing is {min_qty}.")
        return {"error": msg}
    if quantity > max_qty:
        return {"error": f"That's a big order! For {quantity} pieces, please contact us for a custom quote so we can give you the best bulk rate."}

    per_loc = []
    per_shirt_run_sum = Decimal("0")
    for spec in locations:
        colors = int(spec["colors"])
        run = _run_charge_per_shirt(pricing, quantity, colors)
        if run is None:
            return {"error": "Sorry, the pricing table doesn't cover that color count."}
        per_shirt_run_sum += Decimal(str(run))
        per_loc.append({
            "location": spec["location"],
            "colors": colors,
            "per_shirt_run": float(_money(Decimal(str(run))))
        })

    blank = Decimal(str(_blank_price_from_config_or_pricing(cfg, pricing, chosen_tier)))

    per_shirt_total = per_shirt_run_sum + blank
    grand_total = _money(per_shirt_total * Decimal(quantity))

    return {
        "quantity": quantity,
        "locations": per_loc,
        "per_shirt_print": float(_money(per_shirt_run_sum)),
        "blank_per_shirt": float(_money(blank)),
        "per_shirt_out_the_door": float(_money(per_shirt_total)),
        "grand_total": float(grand_total)
    }

def _summary_text(quantity: int, locations: List[Dict[str,int]], cfg: dict, chosen_tier: Optional[str]) -> str:
    locs = ", ".join(f"{l['location'].replace('_',' ')} {l['colors']}c" for l in locations)
    garments = (cfg or {}).get("garments", {}) or {}
    if garments.get("tiers_enabled") and chosen_tier:
        label = garments.get("tiers", {}).get(chosen_tier, {}).get("label", chosen_tier.title())
        return f"Summary ➜ Qty {quantity}, {locs}, Shirt: {label}. Compute?"
    return f"Summary ➜ Qty {quantity}, {locs}. Compute?"

_GREETING_TOKENS = {
    "hi","hello","hey","yo","howdy","hiya","sup","whats","what's","up","there"
}
def _is_greeting(msg: str) -> bool:
    t = _normalize(msg)
    if not t:
        return False
    if t in {"hi","hello","hey","yo","howdy","hi there","hello there","hey there"}:
        return True
    tokens = [w for w in t.split() if w.isalpha()]
    if not tokens:
        return False
    if len(tokens) <= 3 and tokens[0] == "good" and tokens[-1] in {"morning","afternoon","evening"}:
        return True
    non_greet = [w for w in tokens if w not in _GREETING_TOKENS]
    return len(tokens) <= 4 and len(non_greet) == 0

def _pick_greeting(cfg: dict) -> str:
    ui = (cfg or {}).get("ui", {}) or {}
    custom = ui.get("greetings")
    if isinstance(custom, list) and custom:
        return random.choice(custom)
    brand = (cfg or {}).get("brand_name") or "our shop"
    stock = [
        f"👋 Hi there! Welcome to {brand}.",
        f"Hello! Need a quick screen-print quote?",
        f"Hey! I can price tees fast — want a quote?",
        f"Hi! Tell me quantity + colors to get started."
    ]
    return random.choice(stock)

# ------------------ main quote flow ------------------
def _handle_quote_flow(tenant: str, cfg: dict, pricing: dict, sid: str, user_message: str) -> Optional[Dict[str, Any]]:
    key = (tenant, sid)
    s = QUOTE_SESSIONS.get(key)
    if s is None:
        return None

    msg = user_message.strip().lower()

    # GLOBAL RESET HOOK (works at any time during the flow)
    if msg in {"reset","restart","start over","start-over","new quote","new-quote","clear"}:
        QUOTE_SESSIONS.pop(key, None)
        return _start_new_quote_session(tenant, sid)

    # Helper: render small-order suggestion (config-driven)
    def _small_order_branch(qty: int):
        pol = _small_order_policy(cfg)
        min_qty = int(pricing.get("screen_print", {}).get("min_qty", 48))
        suggest = pol["suggest"]
        link = pol["link"]
        label = pol["label"]
        cta_get = pol["cta_get"]
        cta_alt = pol["cta_alt"]

        if suggest == "none":
            return _respond(
                f"Our screen-print minimum is {min_qty}.",
                [{"label": cta_alt, "value": "change_qty"}],
                {"state": {"step": "ask_qty"}}
            )

        link_txt = f" — see options here: {link}" if link else ""
        return _respond(
            f"Orders under {min_qty} are best with {label}—ask us for options!{link_txt}",
            [{"label": cta_get, "value": suggest}, {"label": cta_alt, "value": "change_qty"}],
            {"state": {"step": "small_order"}}
        )

    # ----- Step: ask quantity -----
    if s["step"] == "ask_qty":
        nums = re.findall(r'\d+', msg)
        if nums:
            s["quantity"] = max(int(nums[0]), 1)
            min_qty = int(pricing.get("screen_print", {}).get("min_qty", 48))
            if s["quantity"] < min_qty:
                s["step"] = "small_order"
                return _small_order_branch(s["quantity"])
            s["step"] = "ask_loc"
            return _respond("First location — pick one.", _placement_buttons(cfg, s["locations"]), {"state":{"step":"ask_loc"}})
        return _respond("How many shirts?", _qty_buttons_from_pricing(pricing), {"state":{"step":"ask_qty"}})

    # ----- Step: small-order actions -----
    if s["step"] == "small_order":
        if msg in {"change_qty","change quantity","qty","quantity"}:
            s.update({"step":"ask_qty","quantity":None})
            return _respond("No problem — how many shirts?", _qty_buttons_from_pricing(pricing), {"state":{"step":"ask_qty"}})
        if msg in {"dtf","embroidery"}:
            QUOTE_SESSIONS.pop(key, None)
            pol = _small_order_policy(cfg)
            link = pol["link"]
            label = pol["label"] or msg.title()
            link_txt = f" — see options here: {link}" if link else ""
            return _respond(f"Great — we’ll follow up with {label} options shortly. 👍{link_txt}")
        return _small_order_branch(s.get("quantity") or 0)

    # ----- Step: ask location OR color for pending placement -----
    if s["step"] == "ask_loc":
        parsed = _parse_location_colors(user_message)
        if parsed["location"] and parsed["colors"]:
            s["locations"].append({"location": parsed["location"], "colors": int(parsed["colors"])})
            s["pending"] = {"location": None, "colors": None}
            s["step"] = "ask_more"
            return _respond("Add another print location?", [{"label":"Yes","value":"yes"},{"label":"No","value":"no"}], {"state":{"step":"ask_more"}})

        if msg.startswith("placement:"):
            loc = msg.split(":",1)[1]
            s["pending"] = {"location": loc, "colors": None}
            s["step"] = "ask_colors"
            return _respond(f"How many colors for {_label_for(loc)}?", _color_buttons(cfg), {"state":{"step":"ask_colors"}})

        if msg == "custom_location" or (parsed["location"] and not parsed["colors"]):
            pending_loc = parsed["location"] if parsed["location"] else None
            if pending_loc:
                s["pending"] = {"location": pending_loc, "colors": None}
                s["step"] = "ask_colors"
                return _respond(f"How many colors for {_label_for(pending_loc)}?", _color_buttons(cfg), {"state":{"step":"ask_colors"}})
            return _respond("Type the location (front, back, left sleeve, right sleeve) and colors, e.g., “back 2 colors”.",
                            _placement_buttons(cfg, s["locations"]), {"state":{"step":"ask_loc"}})

        return _respond("Pick a print location.", _placement_buttons(cfg, s["locations"]), {"state":{"step":"ask_loc"}})

    # ----- Step: ask colors for the pending placement -----
    if s["step"] == "ask_colors":
        maxc = _shop_max_colors(cfg)
        chosen = None
        if re.fullmatch(r"\d{1,2}c", msg):
            chosen = int(msg[:-1])
        elif msg.startswith("7-"):
            chosen = min(7, maxc)
        elif msg in {"7+c","7+"}:
            chosen = min(7, maxc)
        else:
            nums = re.findall(r'\d+', msg)
            if nums:
                chosen = min(int(nums[0]), maxc)

        if chosen and 1 <= chosen <= maxc:
            s["locations"].append({"location": s["pending"]["location"], "colors": int(chosen)})
            s["pending"] = {"location": None, "colors": None}
            s["step"] = "ask_more"
            return _respond("Add another print location?", [{"label":"Yes","value":"yes"},{"label":"No","value":"no"}], {"state":{"step":"ask_more"}})

        return _respond(f"How many colors for {_label_for(s['pending']['location'])}? (You can also type 1–{maxc})",
                        _color_buttons(cfg), {"state":{"step":"ask_colors"}})

    # ----- Step: add more placements? -----
    if s["step"] == "ask_more":
        if msg in ("yes","y"):
            s["step"] = "ask_loc"
            return _respond("Next location — pick one.", _placement_buttons(cfg, s["locations"]), {"state":{"step":"ask_loc"}})
        if msg in ("no","n"):
            garments = (cfg or {}).get("garments", {}) or {}
            if garments.get("tiers_enabled"):
                s["step"] = "ask_tier"
                return _respond("Choose a shirt option:", _tier_buttons(cfg), {"state":{"step":"ask_tier"}})
            else:
                s["step"] = "confirm"
                return _respond(_summary_text(s["quantity"], s["locations"], cfg, None),
                                [{"label":"Compute","value":"yes"},{"label":"Start Over","value":"no"}],
                                {"state":{"step":"confirm"}})
        return _respond("Please reply yes or no: add another print location?",
                        [{"label":"Yes","value":"yes"},{"label":"No","value":"no"}],
                        {"state":{"step":"ask_more"}})

    # ----- Step: choose garment tier (optional) -----
    if s["step"] == "ask_tier":
        garments = (cfg or {}).get("garments", {}) or {}
        if garments.get("tiers_enabled") and msg in (garments.get("tiers", {}) or {}).keys():
            s["tier"] = msg
            s["step"] = "confirm"
            return _respond(_summary_text(s["quantity"], s["locations"], cfg, s["tier"]),
                            [{"label":"Compute","value":"yes"},{"label":"Start Over","value":"no"}],
                            {"state":{"step":"confirm"}})
        return _respond("Please choose a shirt option.", _tier_buttons(cfg), {"state":{"step":"ask_tier"}})

    # ----- Step: confirm + compute -----
    if s["step"] == "confirm":
        if msg in ("yes","y","compute"):
            result = _compute_quote_total(pricing, cfg, s["quantity"], s["locations"], s.get("tier"))
            if result and "error" in result:
                QUOTE_SESSIONS.pop(key, None)
                return _respond(result["error"])
            if result:
                QUOTE_SESSIONS.pop(key, None)
                lines = []
                lines.append(f"Per-shirt print: ${result['per_shirt_print']:.2f}")
                lines.append(f"Blank: ${result['blank_per_shirt']:.2f}")
                lines.append(f"Per-shirt out-the-door: ${result['per_shirt_out_the_door']:.2f}")
                lines.append(f"Grand total ({result['quantity']}): ${result['grand_total']:.2f}")

                quote_payload = {
                    "quantity": result["quantity"],
                    "locations": [{"location": l["location"], "colors": int(l["colors"])} for l in result["locations"]],
                    "tier": s.get("tier")
                }

                return _respond(
                    "\n".join(lines),
                    [
                        {"label": "⬇️ Download PDF", "value": "download_pdf"},
                        {"label": "New Quote", "value": "new quote"}
                    ],
                    {"quote": quote_payload}
                )

            QUOTE_SESSIONS.pop(key, None)
            return _respond("Sorry—couldn’t compute that quote. Please try again.")
        if msg in ("no","n","start over","start-over","new quote","new-quote"):
            s.clear()
            s.update({
                "step":"ask_qty",
                "quantity":None,
                "locations":[],
                "tier":None,
                "pending":{"location":None,"colors":None}
            })
            return _respond("No problem—how many shirts?", _qty_buttons_from_pricing(pricing), {"state":{"step":"ask_qty"}})
        return _respond("Type 'Compute' to calculate or 'Start Over' to reset.",
                        [{"label":"Compute","value":"yes"},{"label":"Start Over","value":"no"}],
                        {"state":{"step":"confirm"}})

    return None

# ---------- helper used inside ask_loc step (kept): parse one loc from a snippet ----------
def _parse_location_colors(text: str) -> Dict[str, Optional[Any]]:
    t = text.lower().strip()
    m = re.search(r'\b(\d{1,2})\s*(?:c|color|colors|clr|clrs)?\b', t)
    colors = int(m.group(1)) if m else None
    loc = None
    tokens = ["left sleeve", "right sleeve", "front", "back", "sleeve", "pocket", "left", "right"]
    for k in sorted(tokens, key=len, reverse=True):
        if re.search(rf'\b{k}\b', t):
            loc = _LOC_ALIASES.get(k, k.replace(" ","_"))
            if k in ("left", "right"):
                loc = f"{k}_sleeve"
            break
    return {"location": loc, "colors": colors}

# start a quote flow if user intent or numbers found
def _maybe_start_quote_flow(tenant: str, cfg: dict, sid: str, user_message: str) -> Optional[Dict[str,Any]]:
    text = _normalize(user_message)
    if text in {"reset","restart","start over","start-over","new quote","new-quote","clear"}:
        return _start_new_quote_session(tenant, sid)

    trigger = any(k in text for k in ["quote","price","pricing","estimate","cost"]) or bool(re.findall(r'\d+', text))
    if not trigger:
        return None

    key = (tenant, sid)
    if key in QUOTE_SESSIONS:
        return None

    parsed = _parse_freeform_request(user_message, cfg)
    qty = parsed["quantity"]
    locs = parsed["locations"] or []

    if parsed["global_colors"] is not None:
        for l in locs:
            if l["colors"] is None:
                l["colors"] = parsed["global_colors"]

    locs = [l for l in locs if l.get("colors")]

    if qty and locs:
        return _start_prefilled_session(tenant, sid, cfg, qty, locs)

    if qty:
        QUOTE_SESSIONS[(tenant, sid)] = {
            "step":"ask_loc",
            "quantity":qty,
            "locations":[],
            "tier":None,
            "pending":{"location":None,"colors":None}
        }
        return _respond("First location — pick one.", _placement_buttons(cfg, []), {"state":{"step":"ask_loc"}})

    return _start_new_quote_session(tenant, sid)
# =====================================================================

# =========================
# >>> PDF GENERATION
# =========================
from reportlab.pdfgen import canvas as rl_canvas
from reportlab.lib.pagesizes import LETTER
from reportlab.lib.units import inch
from reportlab.lib.utils import ImageReader

def _render_quote_pdf(tenant: str, cfg: dict, pricing: dict, payload: Dict[str, Any]) -> bytes:
    quantity = int(payload.get("quantity", 0) or 0)
    locations = payload.get("locations") or []
    tier = payload.get("tier")

    result = _compute_quote_total(pricing, cfg, quantity, locations, tier)
    if not result or "error" in result:
        raise ValueError(result.get("error") if isinstance(result, dict) else "Unable to compute")

    buf = io.BytesIO()
    c = rl_canvas.Canvas(buf, pagesize=LETTER)
    W, H = LETTER
    x_margin = 0.75 * inch
    y = H - 0.9 * inch

    brand = (cfg or {}).get("brand_name", tenant)
    logo_path = (cfg or {}).get("logo_path")
    if logo_path:
        actual_logo = logo_path
        if logo_path.startswith("/"):
            possible = os.path.join(APP_ROOT, logo_path.lstrip("/"))
            if os.path.isfile(possible):
                actual_logo = possible
        try:
            img = ImageReader(actual_logo)
            c.drawImage(img, x_margin, y - 0.6*inch, width=1.4*inch, height=0.6*inch, preserveAspectRatio=True, mask='auto')
        except Exception:
            pass
    c.setFont("Helvetica-Bold", 16)
    c.drawString(x_margin + 1.6*inch, y, f"{brand} — Quote")
    y -= 0.25*inch
    c.setFont("Helvetica", 10)
    now_str = datetime.utcnow().strftime("%Y-%m-%d %H:%MZ")
    c.drawString(x_margin + 1.6*inch, y, f"Generated: {now_str}")
    y -= 0.4*inch

    ui = (cfg or {}).get("ui", {}) or {}
    email = ui.get("support_email") or ""
    phone = (cfg or {}).get("phone") or ui.get("support_phone") or ""
    website = (cfg or {}).get("website") or ui.get("shop_url") or ""
    contact_bits = [b for b in [email, phone, website] if b]
    if contact_bits:
        c.setFont("Helvetica", 10)
        c.drawString(x_margin, y, "Contact: " + "  •  ".join(contact_bits))
        y -= 0.3*inch

    c.setFont("Helvetica-Bold", 12)
    c.drawString(x_margin, y, f"Quantity: {result['quantity']}")
    y -= 0.25*inch

    garments = (cfg or {}).get("garments", {}) or {}
    tier_label = None
    if garments.get("tiers_enabled") and tier:
        tier_label = garments.get("tiers", {}).get(tier, {}).get("label", tier.title())
        c.setFont("Helvetica", 10)
        c.drawString(x_margin, y, f"Garment: {tier_label}")
        y -= 0.22*inch

    c.setFont("Helvetica-Bold", 11)
    c.drawString(x_margin, y, "Print Locations")
    y -= 0.2*inch
    c.setFont("Helvetica", 10)
    for loc in result["locations"]:
        c.drawString(x_margin, y, f"• {loc['location'].replace('_',' ').title()} — {int(loc['colors'])} color(s) @ ${loc['per_shirt_run']:.2f}/shirt")
        y -= 0.2*inch
    y -= 0.1*inch

    c.setFont("Helvetica-Bold", 11)
    c.drawString(x_margin, y, "Pricing")
    y -= 0.22*inch
    c.setFont("Helvetica", 10)
    c.drawString(x_margin, y, f"Per-shirt print: ${result['per_shirt_print']:.2f}")
    y -= 0.18*inch
    c.drawString(x_margin, y, f"Blank garment: ${result['blank_per_shirt']:.2f}")
    y -= 0.18*inch
    c.drawString(x_margin, y, f"Per-shirt total: ${result['per_shirt_out_the_door']:.2f}")
    y -= 0.18*inch
    c.setFont("Helvetica-Bold", 12)
    c.drawString(x_margin, y, f"Estimated grand total ({result['quantity']}): ${result['grand_total']:.2f}")
    y -= 0.32*inch

    c.setFont("Helvetica-Oblique", 9)
    c.drawString(x_margin, y, "Estimate only — taxes, add-ons, and artwork review may apply. Thanks for the opportunity!")

    c.showPage()
    c.save()
    pdf_bytes = buf.getvalue()
    buf.close()
    return pdf_bytes

# ---------- main chatbot orchestration ----------
def chatbot_response(tenant: str, data: Dict[str, Any], user_message: str, sid: str) -> Dict[str, Any]:
    enable_branching = data.get("config", {}).get("ui", {}).get("enable_branching", True)

    handled = _handle_quote_flow(tenant, data.get("config", {}), data.get("pricing", {}), sid, user_message)
    if handled:
        return handled

    # Allow reset even when no active session and user types it
    if _normalize(user_message) in {"reset","restart","start over","start-over","new quote","new-quote","clear"}:
        return _start_new_quote_session(tenant, sid)

    # Force structured flow for beta (optional)
    if FORCE_WIZARD:
        started = _maybe_start_quote_flow(tenant, data.get("config", {}), sid, user_message)
        if started:
            return started

    if _is_greeting(user_message):
        greet = _pick_greeting(data.get("config", {}))
        return _respond(greet, [{"label":"Get a Quote","value":"quote"}])

    start_quote = _maybe_start_quote_flow(tenant, data.get("config", {}), sid, user_message)
    if start_quote:
        return start_quote

    # Legacy single-shot quote (kept for simple questions)
    qty, cols = extract_quantity_and_colors(user_message)
    if qty is not None and cols is not None:
        pr = price_quote(data["pricing"], qty, cols)
        if pr:
            return {"type": "answer", "reply": pr, "answer": pr}

    faq_items = get_faq_items(data["faq"])
    matched_item = get_faq_match(faq_items, user_message)
    if matched_item:
        if matched_item.get("type") == "branch":
            options = matched_item.get("options", []) or []
            if enable_branching and options:
                PENDING_BRANCH[(tenant, sid)] = {
                    "id": matched_item.get("id"),
                    "options": options
                }
                payload = {
                    "type": "branch",
                    "prompt": matched_item.get("prompt", "Choose an option:"),
                    "options": [{"label": o.get("label", "Option"), "value": o.get("label", "Option")} for o in options],
                    "answer": matched_item.get("prompt","")
                }
                return payload
            else:
                if options:
                    ans = options[0].get("answer", "Can you clarify what part you’re asking about?")
                    return {"type": "answer", "reply": ans, "answer": ans}
                ans = matched_item.get("prompt", "Can you clarify what part you’re asking about?")
                return {"type": "answer", "reply": ans, "answer": ans}

        faq_answer = matched_item.get("answer")
        if faq_answer:
            if matched_item.get("action") == "start_quote":
                pr = get_pricing_response(data["pricing"], user_message)
                if pr:
                    return {"type": "answer", "reply": pr, "answer": pr}
                qty2, cols2 = extract_quantity_and_colors(user_message)
                need = []
                if qty2 is None: need.append("quantity")
                if cols2 is None: need.append("number of colors")
                if need:
                    msg = "Great—let’s get you a quick quote. Please reply with your " + " and ".join(need) + ' (e.g., "72 shirts, 3 colors").'
                    return {"type": "answer", "reply": msg, "answer": msg}
            return {"type": "answer", "reply": faq_answer, "answer": faq_answer}

    pr = get_pricing_response(data["pricing"], user_message)
    if pr:
        return {"type": "answer", "reply": pr, "answer": pr}

    msg = "I'm not sure yet—try asking about hours, directions, or say a quantity and number of colors for a quote."
    return {"type": "answer", "reply": msg, "answer": msg}

# ---------- routes ----------
@app.route("/bot/<tenant>", methods=["GET"])
def bot_ui(tenant: str):
    data = _load_all(tenant)
    return render_template("index.html", cfg=data["config"], faq=get_faq_items(data["faq"]), tenant=tenant)

# --- QuickQuote Console page ---
@app.route("/console/<tenant>", methods=["GET"])
def console_ui(tenant: str):
    """
    Renders templates/console.html with the same per-tenant cfg you use on index.
    Visit: /console/<tenant>  (e.g., /console/swx)
    """
    cfg = _load_json(tenant, "config")
    return render_template("console.html", cfg=cfg, tenant=tenant)

# Alias to support older links
@app.route("/client/<tenant>", methods=["GET"])
def client_alias(tenant: str):
    return redirect(url_for("bot_ui", tenant=tenant), code=302)

@app.route("/api/ask/<tenant>", methods=["POST"])
def ask(tenant: str):
    msg = (request.get_json() or {}).get("message", "").strip()
    if not msg:
        return jsonify({"type": "answer", "reply": "Invalid request.", "answer": "Invalid request."}), 400
    data = _load_all(tenant)
    sid = _get_sid()

    session_id = sid
    log_turn(session_id, "user", msg, meta={"tenant": tenant})

    result = chatbot_response(tenant, data, msg, sid)

    reply_text = result.get("reply") or result.get("answer") or json.dumps(result)
    log_turn(session_id, "bot", reply_text, meta={"tenant": tenant})

    resp = jsonify(result)
    resp.set_cookie("sid", sid, max_age=60*60*24*30, samesite="Lax", secure=True)
    return resp

# ================================
# >>> QuickQuote Console API v2 (UPDATED)
# ================================
def _console_rules(cfg: dict) -> dict:
    """
    Pulls console pricing knobs from config.json
    """
    c = (cfg or {}).get("console", {}) or {}

    garments = c.get("garments") or []
    gmap = { (g.get("key") or "").strip(): g for g in garments if g.get("key") }

    ex = (c.get("extras") or {})  # per-shirt extras and rush rate (as +%)
    # rush in config is a rate: 0.50 => +50%
    rush_rate = float(ex.get("rush_multiplier", 0.50))  # treated as +% (added after subtotal)
    extras_per_shirt = {
        "fold_bag":   float(ex.get("fold_bag_per_shirt", 0.0)),
        "names":      float(ex.get("names_per_shirt", 0.0)),
        "numbers":    float(ex.get("numbers_per_shirt", 0.0)),
        "heat_press": float(ex.get("heat_press_per_shirt", 0.0)),
        "tagging":    float(ex.get("tagging_per_shirt", 0.0)),
    }

    # garment markup (retail over cost)
    garment_pct = float(
        c.get("garment_markup_pct",
              (c.get("markup") or {}).get("garment_pct", 0.40))
    )

    # screen charges block (one-time)
    sc = (c.get("screen_charges") or {})
    screen_cfg = {
        "enabled": bool(sc.get("enabled", False)),
        "price_per_screen": float(sc.get("price_per_screen", 0.0)),
        "count_white_underbase": bool(sc.get("count_white_underbase", False)),
        "waive_at_qty": (int(sc["waive_at_qty"]) if sc.get("waive_at_qty") not in (None, "",) else None),
        "max_screens": (int(sc["max_screens"]) if sc.get("max_screens") not in (None, "",) else None),
    }

    return {
        "garments_map": gmap,
        "garment_markup_pct": garment_pct,
        "rush_rate": rush_rate,                 # e.g., 0.50 means +50%
        "extras_per_shirt": extras_per_shirt,   # dict of per-shirt adders
        "screen": screen_cfg,                   # screen charge rules
    }

def _normalize_console_payload_v2(payload: Dict[str, Any]) -> Tuple[int, List[Dict[str,int]], Optional[str], Optional[str]]:
    """
    Body:
      {"quantity":72,"placements":[{"name":"front","colors":2}], "garment_key":"g5000",
       "extras":{"rush":true,"fold_bag":true,"names":true,...}, "adminWaiveScreens":false}
    Returns: (qty, locations, tier(None), garment_key)
    """
    qty = int(payload.get("quantity") or 0)
    raw_places = payload.get("placements") or payload.get("locations") or []
    locations: List[Dict[str, int]] = []
    for it in raw_places:
        name = (it.get("name") or it.get("location") or "").strip().lower()
        if not name:
            continue
        colors = int(it.get("colors") or 0)
        if colors <= 0:
            continue
        locations.append({"location": name, "colors": colors})
    garment_key = (payload.get("garment_key") or "").strip() or None
    return qty, locations, None, garment_key

@app.post("/api/quote/<tenant>")
def api_quote(tenant: str):
    """
    Compute a Console quote with garments, markup, extras (per-shirt),
    and optional one-time screen charges. Returns a response that
    keeps backward compatibility with the existing console UI.
    """
    try:
        body = request.get_json(force=True, silent=True) or {}
        qty, locs, _tier, gkey = _normalize_console_payload_v2(body)
        if qty <= 0 or not locs:
            return jsonify({"error": "Missing quantity or placements."}), 400

        cfg = _load_json(tenant, "config")
        pricing = _load_json(tenant, "pricing")
        rules = _console_rules(cfg)

        # ---- APPLY COLOR CAPS BEFORE LOOKUPS (per-placement + pricing tiers) ----
        locs_capped, any_clamped = _apply_color_caps(cfg, pricing, qty, locs)
        if not locs_capped:
            return jsonify({"error": "No valid placements after applying color caps."}), 400

        # --- Garment (cost -> retail via markup) ---
        gmap = rules["garments_map"]
        if not gkey or gkey not in gmap:
            return jsonify({"error":"Select a garment."}), 400
        gmeta = gmap[gkey]
        garment_cost = float(gmeta.get("cost", 0.0))
        if garment_cost <= 0:
            return jsonify({"error":"Invalid garment cost."}), 400
        garment_markup_pct = rules["garment_markup_pct"]
        garment_client = garment_cost * (1.0 + garment_markup_pct)

        # --- Print run charges (per placement, per shirt) ---
        per_shirt_print = 0.0
        per_loc = []
        for spec in locs_capped:
            colors = int(spec["colors"])
            run = _run_charge_per_shirt(pricing, qty, colors)
            if run is None:
                return jsonify({"error": "Pricing table missing for that color count."}), 400
            per_shirt_print += float(run)
            per_loc.append({
                "location": spec["location"],
                "colors": colors,
                "per_shirt_run": round(float(run), 2)
            })

        # --- Base per-shirt math ---
        cost_per_shirt = garment_cost + per_shirt_print   # internal
        client_per_shirt = garment_client + per_shirt_print

        cost_subtotal = cost_per_shirt * qty
        client_subtotal_base = client_per_shirt * qty

        # --- Per-shirt extras (retail line items) ---
        extras_flags = body.get("extras") or {}
        ex_prices = rules["extras_per_shirt"]
        per_shirt_selected_sum = 0.0
        extras_out = {}

        def add_per_shirt_extra(key: str):
            nonlocal per_shirt_selected_sum
            enabled = bool(extras_flags.get(key))
            per = ex_prices.get(key, 0.0) if enabled else 0.0
            total = per * qty
            extras_out[f"{key}_per_shirt"] = round(per, 2)
            extras_out[f"{key}_total"] = round(total, 2)
            per_shirt_selected_sum += per

        for key in ("fold_bag", "names", "numbers", "heat_press", "tagging"):
            add_per_shirt_extra(key)

        per_shirt_extras_total = per_shirt_selected_sum * qty

        # --- Screen charges (one-time, not per shirt) ---
        scfg = rules["screen"]
        admin_waive = bool(body.get("adminWaiveScreens"))
        screen_block = None
        screen_total = 0.0

        if scfg["enabled"]:
            # Count screens = sum(colors per selected placement)
            # +1 per placement if white underbase counts and that placement has ≥1 color
            count = 0
            for spec in locs_capped:
                c = max(0, int(spec["colors"]))
                if c > 0:
                    count += c
                    if scfg["count_white_underbase"]:
                        count += 1
            if scfg["max_screens"] is not None:
                count = min(count, scfg["max_screens"])

            waived_by = None
            if admin_waive:
                waived_by = "admin"
            elif scfg["waive_at_qty"] and qty >= int(scfg["waive_at_qty"]):
                waived_by = "qty"

            price_per_screen = scfg["price_per_screen"]
            screen_total = 0.0 if waived_by else (count * price_per_screen)

            screen_block = {
                "enabled": True,
                "count": int(count),
                "price_per_screen": round(price_per_screen, 2),
                "total": round(screen_total, 2),
                "waived": bool(waived_by),
                "waived_by": waived_by,
                "waive_at_qty": scfg["waive_at_qty"]
            }

        # --- Subtotals (client) ---
        client_subtotal = client_subtotal_base + per_shirt_extras_total + screen_total

        # --- Rush (as +% applied AFTER subtotal) ---
        rush_on = bool(extras_flags.get("rush"))
        rush_rate = rules["rush_rate"] if rush_on else 0.0     # 0.50 => +50%
        rush_multiplier = 1.0 + rush_rate
        rush_amount = client_subtotal * rush_rate

        client_grand = client_subtotal * rush_multiplier
        cost_grand = cost_subtotal  # extras & screens are retail-only in this v2

        # --- Shape response (keep your old fields; add new ones) ---
        out = {
            "quantity": qty,
            "locations": per_loc,
            "params": {
                "garment_key": gkey,
                "garment_label": gmeta.get("label"),
                "garment_cost": round(garment_cost, 2),
                "garment_markup_pct": garment_markup_pct,
                "rush_rate": rush_rate,
                "rush_multiplier": rush_multiplier,
                "colors_clamped": bool(any_clamped)
            },
            "costs": {
                "print_per_shirt": round(per_shirt_print, 2),
                "garment_cost_per_shirt": round(garment_cost, 2),
                "garment_client_per_shirt": round(garment_client, 2),
                "cost_subtotal": round(cost_subtotal, 2)
            },
            "extras": {
                **extras_out,
                "rush_applied": rush_on,
                "rush_amount": round(rush_amount, 2)
            },
            "totals": {
                "client_subtotal": round(client_subtotal, 2),
                "client_grand_total": round(client_grand, 2),
                "cost_grand_total": round(cost_grand, 2)
            }
        }
        if screen_block:
            out["screen_charges"] = screen_block

        return jsonify(out)

    except Exception as e:
        return jsonify({"error": str(e)}), 400
# ================================
# >>> End QuickQuote Console API v2
# ================================

# --- NEW: Download Quote PDF ---
@app.route("/api/download_quote/<tenant>", methods=["POST"])
def download_quote(tenant: str):
    try:
        payload = request.get_json(force=True, silent=False) or {}
        quantity = int(payload.get("quantity", 0) or 0)
        locations = payload.get("locations") or []
        if quantity <= 0 or not isinstance(locations, list) or not locations:
            return jsonify({"error": "Missing or invalid quote data."}), 400

        cfg = _load_json(tenant, "config")
        pricing = _load_json(tenant, "pricing")
        pdf_bytes = _render_quote_pdf(tenant, cfg, pricing, payload)

        resp = make_response(pdf_bytes)
        resp.headers["Content-Type"] = "application/pdf"
        fname = f"{tenant}_quote_{quantity}.pdf"
        resp.headers["Content-Disposition"] = f'attachment; filename="{fname}"'
        return resp
    except Exception as e:
        return jsonify({"error": str(e)}), 400

@app.route("/quote", methods=["POST"])
def quote_compat():
    payload = (request.get_json() or {})
    msg = (payload.get("message") or "").strip()
    tenant = payload.get("tenant") or payload.get("client") or "swx"  # safer default
    if not msg:
        return jsonify({"type": "answer", "reply": "Invalid request.", "answer": "Invalid request."}), 400
    data = _load_all(tenant)
    sid = _get_sid()

    session_id = sid
    log_turn(session_id, "user", msg, meta={"tenant": tenant})

    result = chatbot_response(tenant, data, msg, sid)

    reply_text = result.get("reply") or result.get("answer") or json.dumps(result)
    log_turn(session_id, "bot", reply_text, meta={"tenant": tenant})

    resp = jsonify(result)
    resp.set_cookie("sid", sid, max_age=60*60*24*30, samesite="Lax", secure=True)
    return resp

@app.route("/", methods=["GET"])
def root_redirect():
    return redirect(url_for("home"))

@app.route("/home", methods=["GET"])
def home():
    tenants = []
    for t in sorted(d for d in os.listdir(CLIENTS_DIR)
                    if os.path.isdir(os.path.join(CLIENTS_DIR, d))):
        name = t
        try:
            cfg = _load_json(t, "config")
            name = cfg.get("brand_name", t)
        except Exception:
            pass
        tenants.append({"id": t, "name": name, "logo": f"/static/logos/{t}.png"})
    return render_template("landing.html", tenants=tenants)

@app.route("/ping")
def ping():
    return "pong", 200

@app.route("/health")
def health():
    return "ok", 200

@app.errorhandler(403)
def e403(e):
    print("⚠️  403 handler hit for path:", request.path, "| reason:", e)
    return "Forbidden", 403

@app.errorhandler(Exception)
def on_unhandled_error(e):
    try:
        logger_txt and logger_txt.info(f"EXC on {request.path}: {e}")
        logger_json and logger_json.info(_json_mod.dumps({
            "ts": datetime.utcnow().isoformat(timespec="seconds")+"Z",
            "route": request.path,
            "error": str(e),
            "tenant": (request.view_args or {}).get("tenant")
        }))
    except Exception:
        pass
    return make_response("Sorry—something went wrong. Please try the step-by-step quote.", 500)

if __name__ == "__main__":
    debug = os.getenv("FLASK_DEBUG", "1") == "1"
    app.run(host="127.0.0.1", port=5050, debug=debug)