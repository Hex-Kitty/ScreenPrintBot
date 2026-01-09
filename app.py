"""
QuickQuote + Chatbot Application
================================
Production-ready Flask application for screen print quote generation.

Phase 1 Code Review - Fixed Version
Fixes applied:
  1. Environment variable validation (startup crash prevention)
  2. Session cleanup (memory leak prevention)
  3. Standardized API responses
  4. Input validation
  5. Calculation logging
  6. Max colors config validation
  + Path traversal protection (security)
  + HTTP timeout on Postmark calls (reliability)
  + Improved error handling throughout
"""

import os
import sys
import json
import re
import time
import random
import io
import uuid
import logging
from datetime import datetime
from logging.handlers import TimedRotatingFileHandler
from typing import Optional, Tuple, Dict, Any, List
from decimal import Decimal, ROUND_HALF_UP, getcontext

import requests
from flask import (
    Flask, request, jsonify, render_template, abort, 
    redirect, url_for, make_response
)
from werkzeug.middleware.proxy_fix import ProxyFix
from dotenv import load_dotenv
load_dotenv()

# ==============================================================================
# FIX #1: ENVIRONMENT VARIABLE VALIDATION
# ==============================================================================

REQUIRED_ENV_VARS = {
    "POSTMARK_TOKEN": "Postmark API token for sending emails",
    "FROM_EMAIL": "Email address to send from (e.g., quote@screenprintbot.com)",
}

OPTIONAL_ENV_VARS = {
    "SHOP_BCC": "BCC email for shop owner (defaults to empty)",
    "POSTMARK_STREAM": "Postmark message stream (defaults to 'outbound')",
    "FLASK_DEBUG": "Enable debug mode (defaults to '0')",
    "FORCE_WIZARD": "Force wizard flow (defaults to 'false')",
}

def validate_environment():
    """Validate required environment variables at startup."""
    missing = []
    for var, description in REQUIRED_ENV_VARS.items():
        if var not in os.environ or not os.environ[var].strip():
            missing.append(f"  - {var}: {description}")
    
    if missing:
        error_msg = "Missing required environment variables:\n" + "\n".join(missing)
        print(error_msg, file=sys.stderr)
        raise RuntimeError(error_msg)
    
    print("✓ Environment variables validated", file=sys.stdout)

# Validate at import time (before app starts serving requests)
validate_environment()

# ==============================================================================
# APP INITIALIZATION
# ==============================================================================

APP_ROOT = os.path.dirname(__file__)
CLIENTS_DIR = os.path.join(APP_ROOT, "clients")

app = Flask(__name__)

# Trust Render/Proxy headers for correct client IP/proto
app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1)

# Feature flags
FORCE_WIZARD = os.getenv("FORCE_WIZARD", "false").lower() == "true"

# ==============================================================================
# FIX #3: STANDARDIZED API RESPONSES
# ==============================================================================

def api_error(message: str, code: int = 400, **kwargs) -> tuple:
    """
    Standard error response format.
    
    Returns:
        tuple: (JSON response, HTTP status code)
    
    Example:
        return api_error("Missing customer_email")
        return api_error("Server error", 500, details="...")
    """
    payload = {
        "ok": False,
        "error": message,
    }
    payload.update(kwargs)
    return jsonify(payload), code


def api_success(data=None, **kwargs) -> tuple:
    """
    Standard success response format.
    
    Returns:
        tuple: (JSON response, 200 status code)
    
    Example:
        return api_success({"quote_id": 123})
        return api_success(body, message="Email sent")
    """
    payload = {"ok": True}
    if data is not None:
        if isinstance(data, dict):
            payload.update(data)
        else:
            payload["data"] = data
    payload.update(kwargs)
    return jsonify(payload), 200


# ==============================================================================
# FIX #4: INPUT VALIDATION UTILITIES
# ==============================================================================

# Email regex for validation
EMAIL_PATTERN = re.compile(r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$')


def validate_quantity(qty: Any, min_val: int = 1, max_val: int = 100000) -> Tuple[bool, Optional[str], Optional[int]]:
    """
    Validate quantity is a reasonable integer.
    
    Returns:
        tuple: (is_valid, error_message, cleaned_value)
    """
    if qty is None:
        return (False, "Quantity is required", None)
    
    try:
        qty = int(qty)
    except (TypeError, ValueError):
        return (False, "Quantity must be a number", None)
    
    if qty < min_val:
        return (False, f"Quantity must be at least {min_val}", None)
    if qty > max_val:
        return (False, f"Quantity cannot exceed {max_val:,}", None)
    
    return (True, None, qty)


def validate_email(email: Any) -> Tuple[bool, Optional[str], Optional[str]]:
    """
    Validate email format.
    
    Returns:
        tuple: (is_valid, error_message, cleaned_value)
    """
    if not email or not isinstance(email, str):
        return (False, "Email is required", None)
    
    email = email.strip().lower()
    
    if len(email) > 254:
        return (False, "Email address too long", None)
    
    if not EMAIL_PATTERN.match(email):
        return (False, "Invalid email format", None)
    
    return (True, None, email)


def validate_garment_cost(cost: Any, max_val: float = 100.0) -> Tuple[bool, Optional[str], Optional[float]]:
    """
    Validate custom garment cost.
    
    Returns:
        tuple: (is_valid, error_message, cleaned_value)
    """
    if cost is None:
        return (True, None, None)  # Optional field
    
    try:
        cost = float(cost)
    except (TypeError, ValueError):
        return (False, "Garment cost must be a number", None)
    
    if cost < 0:
        return (False, "Garment cost cannot be negative", None)
    if cost > max_val:
        return (False, f"Garment cost cannot exceed ${max_val:.2f}", None)
    
    return (True, None, round(cost, 2))


def validate_colors(colors: Any, max_val: int = 12) -> Tuple[bool, Optional[str], Optional[int]]:
    """
    Validate color count.
    
    Returns:
        tuple: (is_valid, error_message, cleaned_value)
    """
    if colors is None:
        return (False, "Color count is required", None)
        
    try:
        colors = int(colors)
    except (TypeError, ValueError):
        return (False, "Colors must be a number", None)
    
    if colors < 1:
        return (False, "Must have at least 1 color", None)
    if colors > max_val:
        return (False, f"Cannot exceed {max_val} colors", None)
    
    return (True, None, colors)


def validate_tenant(tenant: str) -> Tuple[bool, Optional[str]]:
    """
    Validate tenant identifier (prevents path traversal).
    
    Returns:
        tuple: (is_valid, error_message)
    """
    if not tenant:
        return (False, "Tenant is required")
    
    # Only allow alphanumeric, underscore, hyphen (no path components)
    if not re.match(r'^[a-zA-Z0-9_-]+$', tenant):
        return (False, "Invalid tenant identifier")
    
    # Prevent path traversal attempts
    if '..' in tenant or '/' in tenant or '\\' in tenant:
        return (False, "Invalid tenant identifier")
    
    # Check tenant directory exists
    tenant_path = os.path.join(CLIENTS_DIR, tenant)
    if not os.path.isdir(tenant_path):
        return (False, f"Tenant '{tenant}' not found")
    
    # Verify path didn't escape CLIENTS_DIR (belt and suspenders)
    real_path = os.path.realpath(tenant_path)
    clients_real = os.path.realpath(CLIENTS_DIR)
    if not real_path.startswith(clients_real):
        return (False, "Invalid tenant path")
    
    return (True, None)


# ==============================================================================
# LOGGING CONFIGURATION
# ==============================================================================

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

    # Console handler (shows up in Render Logs)
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(logging.INFO)
    logger_txt.addHandler(console_handler)

# Redaction patterns
EMAIL_REDACT_RE = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")
PHONE_REDACT_RE = re.compile(r"\+?\d[\d\-\s().]{7,}\d")


def _redact(text: str) -> str:
    """Redact PII from log messages."""
    if not text or not LOG_REDACT:
        return text or ""
    text = EMAIL_REDACT_RE.sub("[email redacted]", text)
    text = PHONE_REDACT_RE.sub("[phone redacted]", text)
    return text


def log_turn(session_id: str, role: str, message: str, meta: Optional[Dict[str, Any]] = None) -> None:
    """Log a conversation turn."""
    if not LOG_ENABLED:
        return
    
    ts = datetime.utcnow().isoformat(timespec="seconds") + "Z"
    safe_msg = _redact(message or "")
    
    entry = {
        "ts": ts,
        "session_id": session_id,
        "tenant": (meta or {}).get("tenant"),
        "ip": request.headers.get("X-Forwarded-For", request.remote_addr) if request else None,
        "route": request.path if request else None,
        "ua": request.headers.get("User-Agent", "") if request else "",
        "role": role,
        "message": safe_msg,
        "meta": meta or {},
    }
    
    if logger_json:
        logger_json.info(json.dumps(entry, ensure_ascii=False))
    if logger_txt:
        sid_short = (session_id or "")[:8]
        tenant = (meta or {}).get("tenant") or "-"
        logger_txt.info(f"{tenant} {sid_short} {role.upper()}: {safe_msg}")


# ==============================================================================
# FIX #2: SESSION MANAGEMENT WITH CLEANUP
# ==============================================================================

SESSION_MAX_AGE = 3600  # 1 hour in seconds

# Session stores (keyed by (tenant, sid))
QUOTE_SESSIONS: Dict[Tuple[str, str], Dict[str, Any]] = {}
PENDING_BRANCH: Dict[Tuple[str, str], Dict[str, Any]] = {}


def _cleanup_expired_sessions() -> None:
    """Remove sessions older than SESSION_MAX_AGE seconds."""
    now = time.time()
    
    # Clean QUOTE_SESSIONS
    expired_quotes = [
        key for key, val in QUOTE_SESSIONS.items()
        if now - val.get("created_at", now) > SESSION_MAX_AGE
    ]
    for key in expired_quotes:
        del QUOTE_SESSIONS[key]
    
    # Clean PENDING_BRANCH
    expired_branches = [
        key for key, val in PENDING_BRANCH.items()
        if now - val.get("created_at", now) > SESSION_MAX_AGE
    ]
    for key in expired_branches:
        del PENDING_BRANCH[key]
    
    if expired_quotes or expired_branches:
        print(f"Session cleanup: removed {len(expired_quotes)} quote sessions, {len(expired_branches)} branches")


def _get_sid() -> str:
    """Get or create a stable session ID via cookie."""
    sid = request.cookies.get("sid")
    if not sid:
        sid = uuid.uuid4().hex[:16]
    return sid


# ==============================================================================
# JSON CACHE WITH MTIME TRACKING
# ==============================================================================

_json_cache: Dict[Tuple[str, str], Dict[str, Any]] = {}


def _load_json(tenant: str, name: str) -> Any:
    """
    Load a JSON file for a tenant with caching and path traversal protection.
    """
    # Validate tenant first (path traversal protection)
    valid, error = validate_tenant(tenant)
    if not valid:
        abort(404, error)
    
    # Only allow specific JSON file names
    allowed_names = {"faq", "pricing", "config"}
    if name not in allowed_names:
        abort(404, f"Unknown config file: {name}")
    
    path = os.path.join(CLIENTS_DIR, tenant, f"{name}.json")
    
    if not os.path.isfile(path):
        abort(404, f"{name}.json not found for tenant '{tenant}'")
    
    mtime = os.path.getmtime(path)
    key = (tenant, name)
    cached = _json_cache.get(key)
    
    if cached and cached["mtime"] == mtime:
        return cached["data"]
    
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
    except json.JSONDecodeError as e:
        abort(500, f"Invalid JSON in {name}.json for tenant '{tenant}': {e}")
    except IOError as e:
        abort(500, f"Cannot read {name}.json for tenant '{tenant}': {e}")
    
    _json_cache[key] = {"data": data, "mtime": mtime}
    return data


def _load_all(tenant: str) -> Dict[str, Any]:
    """Load all config files for a tenant."""
    return {
        "faq": _load_json(tenant, "faq"),
        "pricing": _load_json(tenant, "pricing"),
        "config": _load_json(tenant, "config"),
    }


# ==============================================================================
# PARSING HELPERS
# ==============================================================================

_WORDS = re.compile(r"\b\w+\b", re.IGNORECASE)


def _normalize(text: str) -> str:
    """Normalize text for matching."""
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


# ==============================================================================
# MULTI-LOCATION FREEFORM PARSING
# ==============================================================================

_LOC_ALIASES = {
    "front": "front",
    "back": "back",
    "left sleeve": "left_sleeve",
    "right sleeve": "right_sleeve",
    "sleeve": "left_sleeve",
    "sleeves": "sleeves",     # expands to both
    "left": "left_sleeve",
    "right": "right_sleeve",
    "pocket": "pocket",
}


def _label_for(loc: str) -> str:
    """Get display label for a location."""
    return {"left_sleeve": "Left Sleeve", "right_sleeve": "Right Sleeve"}.get(
        loc, loc.replace("_", " ").title()
    )


def _detect_quantity(text: str) -> Optional[int]:
    """Detect quantity from text."""
    t = text.lower()
    m = re.search(r"(\d+)\s*(?:t-?shirt|tshirt|t-?shirts|tshirts|tee|tees|shirt|shirts|piece|pieces|pc|pcs)\b", t)
    if m:
        return int(m.group(1))
    m2 = re.search(r"(?:qty|quantity)\s*[:\-]?\s*(\d+)\b", t)
    if m2:
        return int(m2.group(1))
    nums = [int(n) for n in re.findall(r"\b\d+\b", t)]
    return max(nums) if nums else None


def _expand_sleeves(loc: str) -> List[str]:
    """Expand 'sleeves' to both left and right."""
    if loc == "sleeves":
        return ["left_sleeve", "right_sleeve"]
    if loc == "sleeve":
        return ["left_sleeve"]
    return [loc]


def _parse_freeform_request(user_message: str, cfg: dict) -> Dict[str, Any]:
    """Parse a freeform quote request with multiple locations."""
    text = user_message.lower()
    result: Dict[str, Any] = {
        "quantity": _detect_quantity(text),
        "locations": [],
        "global_colors": None
    }

    pat_after = re.compile(r"(\d{1,2})\s*c(?:olors?)?\s*(front|back|left sleeve|right sleeve|sleeves?|pocket)\b")
    pat_before = re.compile(r"(front|back|left sleeve|right sleeve|sleeves?|pocket)\s*(\d{1,2})\s*c(?:olors?)?\b")

    consumed = []
    max_colors = int((cfg or {}).get("printing", {}).get("max_colors", 12))

    for m in pat_after.finditer(text):
        c = int(m.group(1))
        loc_key = _LOC_ALIASES.get(m.group(2), m.group(2).replace(" ", "_"))
        for loc in _expand_sleeves(loc_key):
            result["locations"].append({
                "location": loc,
                "colors": min(c, max_colors)
            })
        consumed.append((m.start(), m.end()))

    for m in pat_before.finditer(text):
        c = int(m.group(2))
        loc_key = _LOC_ALIASES.get(m.group(1), m.group(1).replace(" ", "_"))
        for loc in _expand_sleeves(loc_key):
            result["locations"].append({
                "location": loc,
                "colors": min(c, max_colors)
            })
        consumed.append((m.start(), m.end()))

    has_front_back = re.search(r"\bfront\s*(?:\+|&|and|\/)\s*back\b", text)
    if has_front_back and not any(l["location"] in {"front", "back"} for l in result["locations"]):
        result["locations"].extend([
            {"location": "front", "colors": None},
            {"location": "back", "colors": None}
        ])

    for name, norm in [
        ("front", "front"), ("back", "back"), ("left sleeve", "left_sleeve"),
        ("right sleeve", "right_sleeve"), ("pocket", "pocket"), ("sleeves", "sleeves")
    ]:
        if re.search(rf"\b{name}\b", text) and not any(
            l["location"] in _expand_sleeves(norm) for l in result["locations"]
        ):
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


# ==============================================================================
# FAQ HELPERS
# ==============================================================================

def get_faq_items(payload: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Get clean FAQ items from payload."""
    items = payload.get("faqs") or payload.get("faq") or []
    clean: List[Dict[str, Any]] = []
    for it in items:
        if not isinstance(it, dict):
            continue
        if "_comment" in it:
            continue
        clean.append(it)
    return clean


def get_faq_match(faq_list: List[Dict[str, Any]], user_message: str) -> Optional[Dict[str, Any]]:
    """Match user message against FAQ triggers."""
    text = _normalize(user_message)
    for item in faq_list:
        triggers = item.get("triggers") or item.get("tags") or []
        if isinstance(triggers, str):
            triggers = [triggers]
        norm_triggers = [_normalize(t) for t in triggers if isinstance(t, str)]
        if any(trig in text for trig in norm_triggers):
            return item
    return None


# ==============================================================================
# PRICING / QUOTING (SINGLE-LOCATION LEGACY)
# ==============================================================================

def price_quote(pricing: dict, quantity: int, colors: int) -> Optional[str]:
    """Generate a legacy single-location price quote."""
    try:
        sp = pricing["screen_print"]
        base = float(sp.get("garment_base", 0.0))
        min_qty = int(sp.get("min_qty", 1))
        max_qty = int(sp.get("max_qty", 10**9))
        tiers = sp["tiers"][f"{colors}_color"]
    except Exception:
        return None

    if quantity < min_qty:
        alt = pricing.get(
            "alt_small_order_message",
            f"Sorry, our minimum for screen printing is {min_qty}. For smaller orders we recommend DTF transfers."
        )
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
            return (
                f"For {quantity} pieces with {colors} color(s), it's ${pp:.2f} per piece "
                f"(incl. {base:.2f} garment). Estimated total: ${total:.2f}."
            )
    return None


def get_pricing_response(pricing_data: dict, user_message: str) -> Optional[str]:
    """Get pricing response if user is asking for a quote."""
    words = set(_WORDS.findall(user_message.lower()))
    pricing_intent = {"price", "pricing", "quote", "cost", "how", "much"}
    if words & pricing_intent:
        qty, cols = extract_quantity_and_colors(user_message)
        if qty is None or cols is None:
            need = []
            if qty is None:
                need.append("quantity")
            if cols is None:
                need.append("number of colors")
            return f"Happy to quote! I just need the {', '.join(need)}."
        return price_quote(pricing_data, qty, cols)

    qty, cols = extract_quantity_and_colors(user_message)
    if qty and cols:
        return price_quote(pricing_data, qty, cols)
    return None


# ==============================================================================
# BRANCH SUPPORT / RESPONSE HELPERS
# ==============================================================================

def _respond(
    message: str,
    buttons: Optional[List[Dict[str, str]]] = None,
    extra: Optional[Dict[str, Any]] = None
) -> Dict[str, Any]:
    """Create a standard chatbot response."""
    if buttons:
        payload = {
            "type": "branch",
            "prompt": message,
            "options": [
                {"label": b.get("label", "Option"), "value": b.get("value", b.get("label", "Option"))}
                for b in buttons
            ],
            "reply": message,
            "answer": message,
        }
    else:
        payload = {"type": "answer", "reply": message, "answer": message}
    if extra:
        payload.update(extra)
    return payload


# ==============================================================================
# CONFIG & POLICY HELPERS
# ==============================================================================

def _shop_max_colors(cfg: dict) -> int:
    """Get max colors from shop config."""
    pr = (cfg or {}).get("printing", {}) or {}
    return int(pr.get("max_colors") or 6)


def _shop_placements(cfg: dict) -> List[str]:
    """Get available placements from shop config."""
    pr = (cfg or {}).get("printing", {}) or {}
    return list(pr.get("placements") or ["front", "back", "left_sleeve", "right_sleeve"])


def _small_order_policy(cfg: dict) -> Dict[str, str]:
    """Get small order policy from config."""
    ui = (cfg or {}).get("ui", {}) or {}
    so = ui.get("small_order", {}) or {}
    suggest = (so.get("suggest") or ("dtf" if ui.get("dtf_enabled", True) else "none")).lower()
    return {
        "suggest": suggest,
        "link": so.get("link"),
        "label": so.get("label") or (
            "DTF transfers" if suggest == "dtf" else ("Embroidery" if suggest == "embroidery" else "")
        ),
        "cta_get": so.get("cta_get") or (
            "Get DTF Quote" if suggest == "dtf" else ("Get Embroidery Quote" if suggest == "embroidery" else "")
        ),
        "cta_alt": so.get("cta_alt") or "Change Quantity"
    }


# ==============================================================================
# SESSION MANAGEMENT HELPERS
# ==============================================================================

def _start_new_quote_session(tenant: str, sid: str) -> Dict[str, Any]:
    """Start a new quote session."""
    QUOTE_SESSIONS[(tenant, sid)] = {
        "created_at": time.time(),  # FIX #2: Add timestamp for cleanup
        "step": "ask_qty",
        "quantity": None,
        "locations": [],
        "tier": None,
        "pending": {"location": None, "colors": None}
    }
    pricing = _load_json(tenant, "pricing")
    return _respond(
        "How many shirts?",
        _qty_buttons_from_pricing(pricing),
        {"state": {"step": "ask_qty"}}
    )


def _start_prefilled_session(
    tenant: str, sid: str, cfg: dict, quantity: int, locations: List[Dict[str, int]]
) -> Dict[str, Any]:
    """Start a session with pre-filled values."""
    QUOTE_SESSIONS[(tenant, sid)] = {
        "created_at": time.time(),  # FIX #2: Add timestamp for cleanup
        "step": "ask_more",
        "quantity": quantity,
        "locations": locations[:],
        "tier": None,
        "pending": {"location": None, "colors": None}
    }
    return _respond(
        "Add another print location?",
        [{"label": "Yes", "value": "yes"}, {"label": "No", "value": "no"}],
        {"state": {"step": "ask_more"}}
    )


# ==============================================================================
# BUTTON GENERATORS
# ==============================================================================

def _qty_buttons_from_pricing(pricing: dict) -> List[Dict[str, str]]:
    """Generate quantity buttons from pricing tiers."""
    try:
        one_color = pricing["screen_print"]["tiers"]["1_color"]
    except Exception:
        return [{"label": x, "value": x} for x in ["12", "24", "48", "72", "100", "200", "250", "300"]]

    def lb(k: str) -> int:
        b = str(k).replace("–", "-")
        if "+" in b:
            return int(b.replace("+", "").split("-")[0])
        return int(b.split("-")[0])

    keys = list(one_color.keys())
    keys.sort(key=lb)

    buttons = ["12", "24"]
    for k in keys:
        b = str(k).replace("–", "-").strip()
        low = lb(b)
        label = f"{low}+" if "+" in b else str(low)
        if label not in buttons:
            buttons.append(label)

    return [{"label": x, "value": x} for x in buttons]


def _placement_buttons(cfg: dict, chosen: List[Dict[str, Any]]) -> List[Dict[str, str]]:
    """Generate placement buttons excluding already chosen."""
    picked = {p["location"] for p in chosen}
    allowed = _shop_placements(cfg)
    opts = []
    for loc in allowed:
        if loc in picked:
            continue
        opts.append({"label": _label_for(loc), "value": f"placement:{loc}"})
    opts.append({"label": "Custom…", "value": "custom_location"})
    return opts


def _color_buttons(cfg: dict) -> List[Dict[str, str]]:
    """Generate color selection buttons."""
    maxc = _shop_max_colors(cfg)
    labels = [f"{i}c" for i in range(1, min(maxc, 6) + 1)]
    if maxc > 6:
        labels.append(f"7–{maxc}c")
    return [{"label": l, "value": l.replace("–", "-")} for l in labels]


def _tier_buttons(cfg: dict):
    """Generate garment tier buttons."""
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


# ==============================================================================
# PRICING LOOKUPS
# ==============================================================================

def _run_charge_per_shirt(pricing: dict, qty: int, colors: int) -> Optional[float]:
    """Get per-shirt run charge for given quantity and colors."""
    try:
        tiers = pricing["screen_print"]["tiers"][f"{colors}_color"]
    except Exception:
        return None
    for band, price in tiers.items():
        b = str(band).replace("–", "-").strip()
        if "+" in b:
            lo = int(b.replace("+", "").split("-")[0])
            if qty >= lo:
                return float(price)
        else:
            lo, hi = [int(x) for x in b.split("-")]
            if lo <= qty <= hi:
                return float(price)
    return None


def _blank_price_from_config_or_pricing(
    cfg: dict, pricing: dict, chosen_tier: Optional[str]
) -> float:
    """Get blank garment price from config or pricing."""
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


# ==============================================================================
# MONEY HELPERS
# ==============================================================================

getcontext().prec = 9
_CENTS = Decimal("0.01")


def _money(x: Decimal) -> Decimal:
    """Round to cents."""
    return x.quantize(_CENTS, rounding=ROUND_HALF_UP)


# ==============================================================================
# FIX #6: COLOR CAP VALIDATION HELPERS
# ==============================================================================

def _per_loc_color_cap(cfg: dict, loc: str) -> Optional[int]:
    """Get per-placement color cap from config."""
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
    return None


def _max_colors_from_pricing(pricing: dict) -> int:
    """Get max colors available in pricing tiers."""
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


def _apply_color_caps(
    cfg: dict, pricing: dict, qty: int, locs: List[Dict[str, int]]
) -> Tuple[List[Dict[str, int]], bool]:
    """
    Clamp colors per placement to (per-placement cap) and (pricing max tier).
    Returns (new_locs, any_clamped).
    """
    pricing_cap = _max_colors_from_pricing(pricing)
    any_clamped = False
    out: List[Dict[str, int]] = []
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


def _validate_colors_against_config(
    cfg: dict, colors: int, placement: str = None
) -> Tuple[bool, int, bool]:
    """
    Check if colors exceeds shop maximums.
    Returns: (valid: bool, clamped_colors: int, was_clamped: bool)
    """
    max_global = int((cfg or {}).get("printing", {}).get("max_colors", 12))
    
    if placement and "console" in cfg:
        max_per_placement = cfg["console"].get("max_colors_per_placement", {})
        max_placement = max_per_placement.get(placement, max_global)
    else:
        max_placement = max_global
    
    effective_max = min(max_global, max_placement)
    
    if colors > effective_max:
        return (False, effective_max, True)
    
    return (True, colors, False)


# ==============================================================================
# UPSELL HELPERS
# ==============================================================================

def _upsell_rules(cfg: dict) -> dict:
    """Get upsell rules from config."""
    c = (cfg or {}).get("console", {}) or {}
    ups = (c.get("upsell_module") or {})
    items = ups.get("items") or []
    items_map = {}
    for it in items:
        k = (it.get("key") or "").strip()
        if not k:
            continue
        items_map[k] = {
            "label": it.get("label") or k,
            "rate_per_sqft": float(it.get("rate_per_sqft", 0.0))
        }
    precision = int((ups.get("ui") or {}).get("precision", 2))
    return {
        "enabled": bool(ups.get("enabled", False)),
        "precision": precision,
        "items_map": items_map
    }


def _compute_upsell_total_from_payload(
    cfg: dict, upsell_payload: Optional[Dict[str, Any]]
) -> Optional[Dict[str, Any]]:
    """Validate and compute upsell totals from payload."""
    if not upsell_payload:
        return None
    rules = _upsell_rules(cfg)
    if not rules["enabled"]:
        return None
    key = (upsell_payload.get("key") or "").strip()
    if not key:
        return None
    meta = rules["items_map"].get(key)
    if not meta:
        return None
    try:
        width = float(upsell_payload.get("width_in") or 0.0)
        height = float(upsell_payload.get("height_in") or 0.0)
        qty = int(upsell_payload.get("qty") or 0)
    except Exception:
        return None
    if width <= 0 or height <= 0 or qty <= 0:
        return None

    rate = float(meta["rate_per_sqft"])
    area_sqft = (width * height) / 144.0
    total = round(area_sqft * rate * qty, rules["precision"])

    return {
        "key": key,
        "label": upsell_payload.get("label") or meta["label"],
        "width_in": round(width, 2),
        "height_in": round(height, 2),
        "qty": int(qty),
        "rate_per_sqft": round(rate, 4),
        "area_sqft": round(area_sqft, 2),
        "total": float(total)
    }


# ==============================================================================
# QUOTE COMPUTATION
# ==============================================================================

def _compute_quote_total(
    pricing: dict, cfg: dict, quantity: int, locations: List[Dict[str, int]], chosen_tier: Optional[str]
) -> Optional[Dict[str, Any]]:
    """Compute quote total for chatbot flow."""
    sp = pricing.get("screen_print", {})
    min_qty = int(sp.get("min_qty", 1))
    max_qty = int(sp.get("max_qty", 10**9))
    
    if quantity < min_qty:
        msg = pricing.get(
            "alt_small_order_message",
            f"Sorry, our minimum for screen printing is {min_qty}."
        )
        return {"error": msg}
    if quantity > max_qty:
        return {
            "error": f"That's a big order! For {quantity} pieces, please contact us for a custom quote so we can give you the best bulk rate."
        }

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


def _summary_text(quantity: int, locations: List[Dict[str, int]], cfg: dict, chosen_tier: Optional[str]) -> str:
    """Generate summary text for confirmation step."""
    locs = ", ".join(f"{l['location'].replace('_', ' ')} {l['colors']}c" for l in locations)
    garments = (cfg or {}).get("garments", {}) or {}
    if garments.get("tiers_enabled") and chosen_tier:
        label = garments.get("tiers", {}).get(chosen_tier, {}).get("label", chosen_tier.title())
        return f"Summary ➜ Qty {quantity}, {locs}, Shirt: {label}. Compute?"
    return f"Summary ➜ Qty {quantity}, {locs}. Compute?"


# ==============================================================================
# GREETING DETECTION
# ==============================================================================

_GREETING_TOKENS = {
    "hi", "hello", "hey", "yo", "howdy", "hiya", "sup", "whats", "what's", "up", "there"
}


def _is_greeting(msg: str) -> bool:
    """Check if message is a greeting."""
    t = _normalize(msg)
    if not t:
        return False
    if t in {"hi", "hello", "hey", "yo", "howdy", "hi there", "hello there", "hey there"}:
        return True
    tokens = [w for w in t.split() if w.isalpha()]
    if not tokens:
        return False
    if len(tokens) <= 3 and tokens[0] == "good" and tokens[-1] in {"morning", "afternoon", "evening"}:
        return True
    non_greet = [w for w in tokens if w not in _GREETING_TOKENS]
    return len(tokens) <= 4 and len(non_greet) == 0


def _pick_greeting(cfg: dict) -> str:
    """Pick a random greeting for the shop."""
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


# ==============================================================================
# MAIN QUOTE FLOW
# ==============================================================================

def _handle_quote_flow(
    tenant: str, cfg: dict, pricing: dict, sid: str, user_message: str
) -> Optional[Dict[str, Any]]:
    """Handle the step-by-step quote flow."""
    key = (tenant, sid)
    s = QUOTE_SESSIONS.get(key)
    if s is None:
        return None

    msg = user_message.strip().lower()

    # GLOBAL RESET HOOK
    if msg in {"reset", "restart", "start over", "start-over", "new quote", "new-quote", "clear"}:
        QUOTE_SESSIONS.pop(key, None)
        return _start_new_quote_session(tenant, sid)

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

    # Step: ask quantity
    if s["step"] == "ask_qty":
        nums = re.findall(r'\d+', msg)
        if nums:
            s["quantity"] = max(int(nums[0]), 1)
            min_qty = int(pricing.get("screen_print", {}).get("min_qty", 48))
            if s["quantity"] < min_qty:
                s["step"] = "small_order"
                return _small_order_branch(s["quantity"])
            s["step"] = "ask_loc"
            return _respond(
                "First location — pick one.",
                _placement_buttons(cfg, s["locations"]),
                {"state": {"step": "ask_loc"}}
            )
        return _respond(
            "How many shirts?",
            _qty_buttons_from_pricing(pricing),
            {"state": {"step": "ask_qty"}}
        )

    # Step: small-order actions
    if s["step"] == "small_order":
        if msg in {"change_qty", "change quantity", "qty", "quantity"}:
            s.update({"step": "ask_qty", "quantity": None})
            return _respond(
                "No problem — how many shirts?",
                _qty_buttons_from_pricing(pricing),
                {"state": {"step": "ask_qty"}}
            )
        if msg in {"dtf", "embroidery"}:
            QUOTE_SESSIONS.pop(key, None)
            pol = _small_order_policy(cfg)
            link = pol["link"]
            label = pol["label"] or msg.title()
            link_txt = f" — see options here: {link}" if link else ""
            return _respond(f"Great — we'll follow up with {label} options shortly. 👍{link_txt}")
        return _small_order_branch(s.get("quantity") or 0)

    # Step: ask location
    if s["step"] == "ask_loc":
        parsed = _parse_location_colors(user_message)
        if parsed["location"] and parsed["colors"]:
            s["locations"].append({
                "location": parsed["location"],
                "colors": int(parsed["colors"])
            })
            s["pending"] = {"location": None, "colors": None}
            s["step"] = "ask_more"
            return _respond(
                "Add another print location?",
                [{"label": "Yes", "value": "yes"}, {"label": "No", "value": "no"}],
                {"state": {"step": "ask_more"}}
            )

        if msg.startswith("placement:"):
            loc = msg.split(":", 1)[1]
            s["pending"] = {"location": loc, "colors": None}
            s["step"] = "ask_colors"
            return _respond(
                f"How many colors for {_label_for(loc)}?",
                _color_buttons(cfg),
                {"state": {"step": "ask_colors"}}
            )

        if msg == "custom_location" or (parsed["location"] and not parsed["colors"]):
            pending_loc = parsed["location"] if parsed["location"] else None
            if pending_loc:
                s["pending"] = {"location": pending_loc, "colors": None}
                s["step"] = "ask_colors"
                return _respond(
                    f"How many colors for {_label_for(pending_loc)}?",
                    _color_buttons(cfg),
                    {"state": {"step": "ask_colors"}}
                )
            return _respond(
                'Type the location (front, back, left sleeve, right sleeve) and colors, e.g., "back 2 colors".',
                _placement_buttons(cfg, s["locations"]),
                {"state": {"step": "ask_loc"}}
            )

        return _respond(
            "Pick a print location.",
            _placement_buttons(cfg, s["locations"]),
            {"state": {"step": "ask_loc"}}
        )

    # Step: ask colors
    if s["step"] == "ask_colors":
        maxc = _shop_max_colors(cfg)
        chosen = None
        if re.fullmatch(r"\d{1,2}c", msg):
            chosen = int(msg[:-1])
        elif msg.startswith("7-"):
            chosen = min(7, maxc)
        elif msg in {"7+c", "7+"}:
            chosen = min(7, maxc)
        else:
            nums = re.findall(r'\d+', msg)
            if nums:
                chosen = min(int(nums[0]), maxc)

        if chosen and 1 <= chosen <= maxc:
            s["locations"].append({
                "location": s["pending"]["location"],
                "colors": int(chosen)
            })
            s["pending"] = {"location": None, "colors": None}
            s["step"] = "ask_more"
            return _respond(
                "Add another print location?",
                [{"label": "Yes", "value": "yes"}, {"label": "No", "value": "no"}],
                {"state": {"step": "ask_more"}}
            )

        return _respond(
            f"How many colors for {_label_for(s['pending']['location'])}? (You can also type 1–{maxc})",
            _color_buttons(cfg),
            {"state": {"step": "ask_colors"}}
        )

    # Step: add more placements?
    if s["step"] == "ask_more":
        if msg in ("yes", "y"):
            s["step"] = "ask_loc"
            return _respond(
                "Next location — pick one.",
                _placement_buttons(cfg, s["locations"]),
                {"state": {"step": "ask_loc"}}
            )
        if msg in ("no", "n"):
            garments = (cfg or {}).get("garments", {}) or {}
            if garments.get("tiers_enabled"):
                s["step"] = "ask_tier"
                return _respond(
                    "Choose a shirt option:",
                    _tier_buttons(cfg),
                    {"state": {"step": "ask_tier"}}
                )
            else:
                s["step"] = "confirm"
                return _respond(
                    _summary_text(s["quantity"], s["locations"], cfg, None),
                    [{"label": "Compute", "value": "yes"}, {"label": "Start Over", "value": "no"}],
                    {"state": {"step": "confirm"}}
                )
        return _respond(
            "Please reply yes or no: add another print location?",
            [{"label": "Yes", "value": "yes"}, {"label": "No", "value": "no"}],
            {"state": {"step": "ask_more"}}
        )

    # Step: choose garment tier
    if s["step"] == "ask_tier":
        garments = (cfg or {}).get("garments", {}) or {}
        if garments.get("tiers_enabled") and msg in (garments.get("tiers", {}) or {}).keys():
            s["tier"] = msg
            s["step"] = "confirm"
            return _respond(
                _summary_text(s["quantity"], s["locations"], cfg, s["tier"]),
                [{"label": "Compute", "value": "yes"}, {"label": "Start Over", "value": "no"}],
                {"state": {"step": "confirm"}}
            )
        return _respond(
            "Please choose a shirt option.",
            _tier_buttons(cfg),
            {"state": {"step": "ask_tier"}}
        )

    # Step: confirm + compute
    if s["step"] == "confirm":
        if msg in ("yes", "y", "compute"):
            result = _compute_quote_total(pricing, cfg, s["quantity"], s["locations"], s.get("tier"))
            if result and "error" in result:
                QUOTE_SESSIONS.pop(key, None)
                return _respond(result["error"])
            if result:
                QUOTE_SESSIONS.pop(key, None)
                lines = [
                    f"Per-shirt print: ${result['per_shirt_print']:.2f}",
                    f"Blank: ${result['blank_per_shirt']:.2f}",
                    f"Per-shirt out-the-door: ${result['per_shirt_out_the_door']:.2f}",
                    f"Grand total ({result['quantity']}): ${result['grand_total']:.2f}"
                ]

                quote_payload = {
                    "quantity": result["quantity"],
                    "locations": [
                        {"location": l["location"], "colors": int(l["colors"])}
                        for l in result["locations"]
                    ],
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
            return _respond("Sorry—couldn't compute that quote. Please try again.")
        
        if msg in ("no", "n", "start over", "start-over", "new quote", "new-quote"):
            s.clear()
            s.update({
                "created_at": time.time(),
                "step": "ask_qty",
                "quantity": None,
                "locations": [],
                "tier": None,
                "pending": {"location": None, "colors": None}
            })
            return _respond(
                "No problem—how many shirts?",
                _qty_buttons_from_pricing(pricing),
                {"state": {"step": "ask_qty"}}
            )
        
        return _respond(
            "Type 'Compute' to calculate or 'Start Over' to reset.",
            [{"label": "Compute", "value": "yes"}, {"label": "Start Over", "value": "no"}],
            {"state": {"step": "confirm"}}
        )

    return None


def _parse_location_colors(text: str) -> Dict[str, Optional[Any]]:
    """Parse location and colors from text snippet."""
    t = text.lower().strip()
    m = re.search(r'\b(\d{1,2})\s*(?:c|color|colors|clr|clrs)?\b', t)
    colors = int(m.group(1)) if m else None
    loc = None
    tokens = ["left sleeve", "right sleeve", "front", "back", "sleeve", "pocket", "left", "right"]
    for k in sorted(tokens, key=len, reverse=True):
        if re.search(rf'\b{k}\b', t):
            loc = _LOC_ALIASES.get(k, k.replace(" ", "_"))
            if k in ("left", "right"):
                loc = f"{k}_sleeve"
            break
    return {"location": loc, "colors": colors}


def _maybe_start_quote_flow(
    tenant: str, cfg: dict, sid: str, user_message: str
) -> Optional[Dict[str, Any]]:
    """Start a quote flow if user intent detected."""
    text = _normalize(user_message)
    if text in {"reset", "restart", "start over", "start-over", "new quote", "new-quote", "clear"}:
        return _start_new_quote_session(tenant, sid)

    trigger = any(k in text for k in ["quote", "price", "pricing", "estimate", "cost"]) or bool(re.findall(r'\d+', text))
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
            "created_at": time.time(),
            "step": "ask_loc",
            "quantity": qty,
            "locations": [],
            "tier": None,
            "pending": {"location": None, "colors": None}
        }
        return _respond(
            "First location — pick one.",
            _placement_buttons(cfg, []),
            {"state": {"step": "ask_loc"}}
        )

    return _start_new_quote_session(tenant, sid)


# ==============================================================================
# PDF GENERATION
# ==============================================================================

from reportlab.pdfgen import canvas as rl_canvas
from reportlab.lib.pagesizes import LETTER
from reportlab.lib.units import inch
from reportlab.lib.utils import ImageReader


def _render_quote_pdf(tenant: str, cfg: dict, pricing: dict, payload: Dict[str, Any]) -> bytes:
    """Render a quote PDF with optional screen print and upsell sections."""
    quantity = int(payload.get("quantity", 0) or 0)
    locations = payload.get("locations") or []
    tier = payload.get("tier")

    sp_result = None
    if quantity > 0 and isinstance(locations, list) and len(locations) > 0:
        sp_result = _compute_quote_total(pricing, cfg, quantity, locations, tier)
        if sp_result and "error" in sp_result:
            sp_result = None

    upsell_payload = payload.get("upsell")
    ups = _compute_upsell_total_from_payload(cfg, upsell_payload)

    if not sp_result and not ups:
        raise ValueError("Nothing to render (no valid placements or upsell).")

    total_sum = 0.0
    if sp_result:
        total_sum += float(sp_result.get("grand_total", 0.0))
    if ups:
        total_sum += float(ups.get("total", 0.0))

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
            c.drawImage(
                img, x_margin, y - 0.6*inch,
                width=1.4*inch, height=0.6*inch,
                preserveAspectRatio=True, mask='auto'
            )
        except Exception:
            pass

    c.setFont("Helvetica-Bold", 16)
    c.drawString(x_margin + 1.6*inch, y, f"{brand} — Quote")
    y -= 0.25 * inch
    c.setFont("Helvetica", 10)
    now_str = datetime.utcnow().strftime("%Y-%m-%d %H:%MZ")
    c.drawString(x_margin + 1.6*inch, y, f"Generated: {now_str}")
    y -= 0.4 * inch

    ui = (cfg or {}).get("ui", {}) or {}
    email = ui.get("support_email") or ""
    phone = (cfg or {}).get("phone") or ui.get("support_phone") or ""
    website = (cfg or {}).get("website") or ui.get("shop_url") or ""
    contact_bits = [b for b in [email, phone, website] if b]
    if contact_bits:
        c.setFont("Helvetica", 10)
        c.drawString(x_margin, y, "Contact: " + "  •  ".join(contact_bits))
        y -= 0.3 * inch

    if sp_result:
        c.setFont("Helvetica-Bold", 12)
        c.drawString(x_margin, y, f"Quantity: {sp_result['quantity']}")
        y -= 0.25 * inch

        garments = (cfg or {}).get("garments", {}) or {}
        tier_label = None
        if garments.get("tiers_enabled") and tier:
            tier_label = garments.get("tiers", {}).get(tier, {}).get("label", tier.title())
            c.setFont("Helvetica", 10)
            c.drawString(x_margin, y, f"Garment: {tier_label}")
            y -= 0.22 * inch

        c.setFont("Helvetica-Bold", 11)
        c.drawString(x_margin, y, "Print Locations")
        y -= 0.2 * inch
        c.setFont("Helvetica", 10)
        for loc in sp_result["locations"]:
            c.drawString(
                x_margin, y,
                f"• {loc['location'].replace('_', ' ').title()} — {int(loc['colors'])} color(s) @ ${loc['per_shirt_run']:.2f}/shirt"
            )
            y -= 0.2 * inch
        y -= 0.1 * inch

        c.setFont("Helvetica-Bold", 11)
        c.drawString(x_margin, y, "Screen Print Pricing")
        y -= 0.22 * inch
        c.setFont("Helvetica", 10)
        c.drawString(x_margin, y, f"Per-shirt print: ${sp_result['per_shirt_print']:.2f}")
        y -= 0.18 * inch
        c.drawString(x_margin, y, f"Blank garment: ${sp_result['blank_per_shirt']:.2f}")
        y -= 0.18 * inch
        c.drawString(x_margin, y, f"Per-shirt total: ${sp_result['per_shirt_out_the_door']:.2f}")
        y -= 0.28 * inch

    if ups:
        c.setFont("Helvetica-Bold", 11)
        c.drawString(x_margin, y, "Upsell Items")
        y -= 0.22 * inch
        c.setFont("Helvetica", 10)
        dims = f'{ups["width_in"]:.1f}" × {ups["height_in"]:.1f}"'
        c.drawString(x_margin, y, f'• {ups["label"]} — {dims}, Qty {ups["qty"]}')
        y -= 0.18 * inch
        c.drawString(x_margin, y, f'  Area: {ups["area_sqft"]:.2f} sq ft  •  Rate: ${ups["rate_per_sqft"]:.2f}/sq ft')
        y -= 0.18 * inch
        c.drawString(x_margin, y, f'  Line total: ${ups["total"]:.2f}')
        y -= 0.28 * inch

    c.setFont("Helvetica-Bold", 12)
    c.drawString(x_margin, y, f"Estimated grand total: ${total_sum:.2f}")
    y -= 0.32 * inch

    c.setFont("Helvetica-Oblique", 9)
    c.drawString(x_margin, y, "Estimate only — taxes, add-ons, and artwork review may apply. Thanks for the opportunity!")

    c.showPage()
    c.save()
    pdf_bytes = buf.getvalue()
    buf.close()
    return pdf_bytes


# ==============================================================================
# MAIN CHATBOT ORCHESTRATION
# ==============================================================================

def chatbot_response(tenant: str, data: Dict[str, Any], user_message: str, sid: str) -> Dict[str, Any]:
    """Main chatbot response handler."""
    enable_branching = data.get("config", {}).get("ui", {}).get("enable_branching", True)

    handled = _handle_quote_flow(tenant, data.get("config", {}), data.get("pricing", {}), sid, user_message)
    if handled:
        return handled

    if _normalize(user_message) in {"reset", "restart", "start over", "start-over", "new quote", "new-quote", "clear"}:
        return _start_new_quote_session(tenant, sid)

    if FORCE_WIZARD:
        started = _maybe_start_quote_flow(tenant, data.get("config", {}), sid, user_message)
        if started:
            return started

    if _is_greeting(user_message):
        greet = _pick_greeting(data.get("config", {}))
        return _respond(greet, [{"label": "Get a Quote", "value": "quote"}])

    start_quote = _maybe_start_quote_flow(tenant, data.get("config", {}), sid, user_message)
    if start_quote:
        return start_quote

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
                    "created_at": time.time(),  # FIX #2: Add timestamp
                    "id": matched_item.get("id"),
                    "options": options
                }
                payload = {
                    "type": "branch",
                    "prompt": matched_item.get("prompt", "Choose an option:"),
                    "options": [
                        {"label": o.get("label", "Option"), "value": o.get("label", "Option")}
                        for o in options
                    ],
                    "answer": matched_item.get("prompt", "")
                }
                return payload
            else:
                if options:
                    ans = options[0].get("answer", "Can you clarify what part you're asking about?")
                    return {"type": "answer", "reply": ans, "answer": ans}
                ans = matched_item.get("prompt", "Can you clarify what part you're asking about?")
                return {"type": "answer", "reply": ans, "answer": ans}

        faq_answer = matched_item.get("answer")
        if faq_answer:
            if matched_item.get("action") == "start_quote":
                pr = get_pricing_response(data["pricing"], user_message)
                if pr:
                    return {"type": "answer", "reply": pr, "answer": pr}
                qty2, cols2 = extract_quantity_and_colors(user_message)
                need = []
                if qty2 is None:
                    need.append("quantity")
                if cols2 is None:
                    need.append("number of colors")
                if need:
                    msg = (
                        "Great—let's get you a quick quote. Please reply with your "
                        + " and ".join(need) + ' (e.g., "72 shirts, 3 colors").'
                    )
                    return {"type": "answer", "reply": msg, "answer": msg}
            return {"type": "answer", "reply": faq_answer, "answer": faq_answer}

    pr = get_pricing_response(data["pricing"], user_message)
    if pr:
        return {"type": "answer", "reply": pr, "answer": pr}

    msg = "I'm not sure yet—try asking about hours, directions, or say a quantity and number of colors for a quote."
    return {"type": "answer", "reply": msg, "answer": msg}


# ==============================================================================
# ROUTES - BASIC
# ==============================================================================

@app.get("/__version")
def __version():
    """Version endpoint for health checks."""
    return {"ok": True}


@app.get("/api/ping")
def api_ping():
    """Ping endpoint."""
    return {"pong": True}


@app.route("/ping")
def ping():
    """Simple ping."""
    return "pong", 200


@app.route("/health")
def health():
    """Health check endpoint."""
    return "ok", 200


@app.route("/", methods=["GET"])
def root_redirect():
    """Redirect root to home."""
    return redirect(url_for("home"))


@app.route("/home", methods=["GET"])
def home():
    """Home page listing all tenants."""
    tenants = []
    for t in sorted(
        d for d in os.listdir(CLIENTS_DIR)
        if os.path.isdir(os.path.join(CLIENTS_DIR, d))
    ):
        name = t
        try:
            cfg = _load_json(t, "config")
            name = cfg.get("brand_name", t)
        except Exception:
            pass
        tenants.append({"id": t, "name": name, "logo": f"/static/logos/{t}.png"})
    return render_template("landing.html", tenants=tenants)


# ==============================================================================
# ROUTES - EMAIL
# ==============================================================================

# HTTP timeout for external API calls
HTTP_TIMEOUT = 30  # seconds


@app.route("/api/email-estimate", methods=["POST"])
def email_estimate():
    """Send email estimate via Postmark."""
    data = request.get_json(silent=True) or {}
    customer_email = data.get("customer_email")
    
    # FIX #4: Validate email
    valid, error, email = validate_email(customer_email)
    if not valid:
        return api_error(error)
    
    subject = data.get("subject", "Your Estimate from QuickQuote Console")
    html_body = data.get("html_body", "<p>This is a test estimate.</p>")
    text_body = data.get("text_body", "This is a test estimate.")

    payload = {
        "From": os.environ["FROM_EMAIL"],
        "To": email,
        "Bcc": os.environ.get("SHOP_BCC", ""),
        "Subject": subject,
        "HtmlBody": html_body,
        "TextBody": text_body,
        "MessageStream": os.environ.get("POSTMARK_STREAM", "outbound")
    }

    headers = {
        "Accept": "application/json",
        "Content-Type": "application/json",
        "X-Postmark-Server-Token": os.environ["POSTMARK_TOKEN"],
    }

    try:
        # IMPROVEMENT: Add timeout to prevent hanging
        r = requests.post(
            "https://api.postmarkapp.com/email",
            json=payload,
            headers=headers,
            timeout=HTTP_TIMEOUT
        )
    except requests.Timeout:
        log_turn("email", "error", "Postmark timeout", meta={"to": email})
        return api_error("Email service timeout. Please try again.", 504)
    except requests.RequestException as e:
        log_turn("email", "error", f"Postmark request failed: {e}", meta={"to": email})
        return api_error("Email service unavailable. Please try again.", 503)

    try:
        body = r.json()
    except Exception:
        body = {"raw": r.text}

    print("POSTMARK status:", r.status_code)
    print("POSTMARK body:", body)

    if r.status_code >= 400:
        return api_error(body.get("Message", "Email failed"), r.status_code)
    
    return api_success(body, message="Email sent successfully")


# ==============================================================================
# ROUTES - CHATBOT
# ==============================================================================

@app.route("/bot/<tenant>", methods=["GET"])
def bot_ui(tenant: str):
    """Chatbot UI for a tenant."""
    # Validate tenant
    valid, error = validate_tenant(tenant)
    if not valid:
        abort(404, error)
    
    data = _load_all(tenant)
    return render_template("index.html", cfg=data["config"], faq=get_faq_items(data["faq"]), tenant=tenant)


@app.route("/client/<tenant>", methods=["GET"])
def client_alias(tenant: str):
    """Alias to support older links."""
    return redirect(url_for("bot_ui", tenant=tenant), code=302)


@app.route("/api/ask/<tenant>", methods=["POST"])
def ask(tenant: str):
    """Chatbot ask endpoint."""
    # FIX #2: Clean up expired sessions on every request
    _cleanup_expired_sessions()
    
    # Validate tenant
    valid, error = validate_tenant(tenant)
    if not valid:
        return api_error(error, 404)
    
    msg = (request.get_json() or {}).get("message", "").strip()
    if not msg:
        return api_error("Message is required", 400)
    
    data = _load_all(tenant)
    sid = _get_sid()

    log_turn(sid, "user", msg, meta={"tenant": tenant})

    result = chatbot_response(tenant, data, msg, sid)

    reply_text = result.get("reply") or result.get("answer") or json.dumps(result)
    log_turn(sid, "bot", reply_text, meta={"tenant": tenant})

    resp = jsonify(result)
    resp.set_cookie("sid", sid, max_age=60*60*24*30, samesite="Lax", secure=True)
    return resp


@app.route("/quote", methods=["POST"])
def quote_compat():
    """Legacy quote endpoint for compatibility."""
    payload = (request.get_json() or {})
    msg = (payload.get("message") or "").strip()
    tenant = payload.get("tenant") or payload.get("client") or "swx"
    
    if not msg:
        return api_error("Invalid request", 400)
    
    # Validate tenant
    valid, error = validate_tenant(tenant)
    if not valid:
        return api_error(error, 404)
    
    data = _load_all(tenant)
    sid = _get_sid()

    log_turn(sid, "user", msg, meta={"tenant": tenant})

    result = chatbot_response(tenant, data, msg, sid)

    reply_text = result.get("reply") or result.get("answer") or json.dumps(result)
    log_turn(sid, "bot", reply_text, meta={"tenant": tenant})

    resp = jsonify(result)
    resp.set_cookie("sid", sid, max_age=60*60*24*30, samesite="Lax", secure=True)
    return resp


# ==============================================================================
# ROUTES - QUICKQUOTE CONSOLE
# ==============================================================================

@app.route("/console/<tenant>", methods=["GET"])
def console_ui(tenant: str):
    """QuickQuote Console UI for a tenant."""
    # Validate tenant
    valid, error = validate_tenant(tenant)
    if not valid:
        abort(404, error)
    
    cfg = _load_json(tenant, "config")
    return render_template("console.html", cfg=cfg, tenant=tenant)


def _console_rules(cfg: dict) -> dict:
    """Get console pricing rules from config."""
    c = (cfg or {}).get("console", {}) or {}

    garments = c.get("garments") or []
    gmap = {(g.get("key") or "").strip(): g for g in garments if g.get("key")}

    ex = (c.get("extras") or {})
    rush_rate = float(ex.get("rush_multiplier", 0.50))
    extras_per_shirt = {
        "fold_bag": float(ex.get("fold_bag_per_shirt", 0.0)),
        "names": float(ex.get("names_per_shirt", 0.0)),
        "numbers": float(ex.get("numbers_per_shirt", 0.0)),
        "heat_press": float(ex.get("heat_press_per_shirt", 0.0)),
        "tagging": float(ex.get("tagging_per_shirt", 0.0)),
    }

    garment_pct = float(
        c.get("garment_markup_pct",
              (c.get("markup") or {}).get("garment_pct", 0.40))
    )

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
        "rush_rate": rush_rate,
        "extras_per_shirt": extras_per_shirt,
        "screen": screen_cfg,
    }


def _normalize_console_payload_v2(payload: Dict[str, Any]) -> Tuple[int, List[Dict[str, int]], Optional[str], Optional[str]]:
    """Normalize console quote payload."""
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
    Console quote API with garments, markup, extras, screen charges, and upsell.
    
    Supports:
      - Standard screen print flow (requires qty>0 and placements)
      - Upsell-only flow (no garments/qty needed)
      - Mixed (both)
    """
    # FIX #2: Clean up expired sessions
    _cleanup_expired_sessions()
    
    # Validate tenant
    valid, error = validate_tenant(tenant)
    if not valid:
        return api_error(error, 404)
    
    try:
        body = request.get_json(force=True, silent=True) or {}
        
        # FIX #4: Validate quantity if provided
        raw_qty = body.get("quantity")
        if raw_qty is not None:
            valid, error, qty = validate_quantity(raw_qty, min_val=0)  # Allow 0 for upsell-only
            if not valid:
                return api_error(error)
        else:
            qty = 0
        
        # Get locations with validation
        raw_places = body.get("placements") or body.get("locations") or []
        locations: List[Dict[str, int]] = []
        for i, it in enumerate(raw_places):
            name = (it.get("name") or it.get("location") or "").strip().lower()
            if not name:
                continue
            
            # FIX #4: Validate colors
            raw_colors = it.get("colors")
            valid, error, colors = validate_colors(raw_colors, max_val=12)
            if not valid:
                return api_error(f"Placement {i+1} ({name}): {error}")
            
            locations.append({"location": name, "colors": colors})
        
        gkey = (body.get("garment_key") or "").strip() or None
        locs = locations

        cfg = _load_json(tenant, "config")
        pricing = _load_json(tenant, "pricing")
        rules = _console_rules(cfg)
        
        customer_supplied = body.get("customer_supplied_garment", False)

        # Upsell (optional)
        upsell_in = body.get("upsell")
        ups = _compute_upsell_total_from_payload(cfg, upsell_in)

        # If NO screen-print placements/qty AND NO valid upsell, error
        if (qty <= 0 or not locs) and not ups:
            return api_error("Missing quantity/placements or upsell item")

        # Initialize variables
        per_loc = []
        per_shirt_print = 0.0
        garment_cost = 0.0
        garment_client = 0.0
        garment_label = None
        garment_mode = "preset"
        garment_markup_pct = rules["garment_markup_pct"]
        screen_block = None
        screen_total = 0.0
        colors_clamped = False

        if qty > 0 and locs:
            # FIX #6: Apply color caps
            locs_capped, any_clamped = _apply_color_caps(cfg, pricing, qty, locs)
            colors_clamped = bool(any_clamped)
            if not locs_capped:
                return api_error("No valid placements after applying color caps")

            # Determine garment
            gmap = rules["garments_map"]
            
            if customer_supplied:
                garment_cost = 0.0
                garment_label = "Customer Supplied"
                garment_mode = "customer_supplied"
            else:
                # FIX #4: Validate manual garment cost
                manual_cost = body.get("manual_garment_cost", None)
                manual_label = (body.get("manual_garment_label") or "").strip() or "Custom garment"

                if manual_cost is not None:
                    valid, error, cleaned_cost = validate_garment_cost(manual_cost, max_val=100.0)
                    if not valid:
                        return api_error(error)
                    garment_cost = cleaned_cost
                    garment_label = manual_label
                    garment_mode = "custom"
                else:
                    if not gkey or gkey not in gmap:
                        return api_error("Select a garment (or check 'Customer is supplying')")
                    gmeta = gmap[gkey]
                    garment_cost = float(gmeta.get("cost", 0.0))
                    if garment_cost <= 0:
                        return api_error("Invalid garment cost")
                    garment_label = gmeta.get("label")

            garment_client = garment_cost * (1.0 + garment_markup_pct)

            # Print run charges
            for spec in locs_capped:
                colors = int(spec["colors"])
                run = _run_charge_per_shirt(pricing, qty, colors)
                if run is None:
                    return api_error("Pricing table missing for that color count")
                per_shirt_print += float(run)
                per_loc.append({
                    "location": spec["location"],
                    "colors": colors,
                    "per_shirt_run": round(float(run), 2)
                })

            # Screen charges
            scfg = rules["screen"]
            admin_waive = bool(body.get("adminWaiveScreens"))
            if scfg["enabled"]:
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

        # Base per-shirt math
        cost_per_shirt = garment_cost + per_shirt_print if (qty > 0 and locs) else 0.0
        client_per_shirt = garment_client + per_shirt_print if (qty > 0 and locs) else 0.0

        cost_subtotal = cost_per_shirt * qty if qty > 0 else 0.0
        client_subtotal_base = client_per_shirt * qty if qty > 0 else 0.0

        # Per-shirt extras
        extras_flags = body.get("extras") or {}
        ex_prices = rules["extras_per_shirt"]
        per_shirt_selected_sum = 0.0
        extras_out = {}

        def add_per_shirt_extra(key: str):
            nonlocal per_shirt_selected_sum
            enabled = bool(extras_flags.get(key)) if qty > 0 else False
            per = ex_prices.get(key, 0.0) if enabled else 0.0
            total = per * qty
            extras_out[f"{key}_per_shirt"] = round(per, 2)
            extras_out[f"{key}_total"] = round(total, 2)
            per_shirt_selected_sum += per

        for key in ("fold_bag", "names", "numbers", "heat_press", "tagging"):
            add_per_shirt_extra(key)

        per_shirt_extras_total = per_shirt_selected_sum * qty if qty > 0 else 0.0

        # Subtotals
        upsell_total = float(ups["total"]) if ups else 0.0
        client_subtotal = client_subtotal_base + per_shirt_extras_total + screen_total + upsell_total

        # Rush
        rush_on = bool(extras_flags.get("rush"))
        rush_rate = rules["rush_rate"] if rush_on else 0.0
        rush_multiplier = 1.0 + rush_rate
        rush_amount = client_subtotal * rush_rate

        client_grand = client_subtotal * rush_multiplier
        cost_grand = cost_subtotal

        # FIX #5: Log calculation for debugging
        calculation_log = {
            "tenant": tenant,
            "qty": qty,
            "garment": {
                "mode": garment_mode,
                "label": garment_label,
                "cost": garment_cost,
                "markup_pct": garment_markup_pct,
                "client_price": garment_client,
            },
            "print": {
                "per_shirt": per_shirt_print,
                "locations": per_loc,
            },
            "extras": {
                "per_shirt_sum": per_shirt_selected_sum,
                "total": per_shirt_extras_total,
                "rush_rate": rush_rate,
                "rush_amount": rush_amount,
            },
            "screens": screen_block,
            "upsell": ups,
            "totals": {
                "cost_subtotal": cost_subtotal,
                "client_subtotal": client_subtotal,
                "client_grand": client_grand,
            }
        }

        log_turn(
            session_id=f"quote-{time.time()}",
            role="calculation",
            message=f"Console quote generated",
            meta=calculation_log
        )

        # Build response
        params_block = {
            "garment_key": (gkey if (qty > 0 and locs and garment_mode == "preset") else None),
            "garment_label": (garment_label if (qty > 0 and locs) else None),
            "garment_cost": round(garment_cost, 2) if (qty > 0 and locs) else 0.0,
            "garment_markup_pct": garment_markup_pct,
            "rush_rate": rush_rate,
            "rush_multiplier": rush_multiplier,
            "colors_clamped": bool(colors_clamped),
            "garment_mode": (garment_mode if (qty > 0 and locs) else None)
        }

        out = {
            "quantity": qty,
            "locations": per_loc if (qty > 0 and locs) else [],
            "params": params_block,
            "costs": {
                "print_per_shirt": round(per_shirt_print, 2) if (qty > 0 and locs) else 0.0,
                "garment_cost_per_shirt": round(garment_cost, 2) if (qty > 0 and locs) else 0.0,
                "garment_client_per_shirt": round(garment_client, 2) if (qty > 0 and locs) else 0.0,
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
        if ups:
            out["upsell"] = ups

        return jsonify(out)

    except Exception as e:
        log_turn("api_quote", "error", str(e), meta={"tenant": tenant})
        return api_error(str(e), 400)


# ==============================================================================
# ROUTES - PDF DOWNLOAD
# ==============================================================================

@app.route("/api/download_quote/<tenant>", methods=["POST"])
def download_quote(tenant: str):
    """Download quote as PDF."""
    # Validate tenant
    valid, error = validate_tenant(tenant)
    if not valid:
        return api_error(error, 404)
    
    try:
        payload = request.get_json(force=True, silent=False) or {}
        quantity = int(payload.get("quantity", 0) or 0)
        locations = payload.get("locations") or []
        upsell_payload = payload.get("upsell")

        if (quantity <= 0 or not isinstance(locations, list) or not locations) and not upsell_payload:
            return api_error("Missing or invalid quote data (need placements or upsell)")

        cfg = _load_json(tenant, "config")
        pricing = _load_json(tenant, "pricing")
        pdf_bytes = _render_quote_pdf(tenant, cfg, pricing, payload)

        resp = make_response(pdf_bytes)
        resp.headers["Content-Type"] = "application/pdf"
        base_qty = quantity if quantity > 0 else (upsell_payload.get("qty") if isinstance(upsell_payload, dict) else 1)
        fname = f"{tenant}_quote_{base_qty}.pdf"
        resp.headers["Content-Disposition"] = f'attachment; filename="{fname}"'
        return resp
    except Exception as e:
        return api_error(str(e), 400)


# ==============================================================================
# ERROR HANDLERS
# ==============================================================================

@app.errorhandler(403)
def e403(e):
    """Handle 403 errors."""
    print("⚠️  403 handler hit for path:", request.path, "| reason:", e)
    return "Forbidden", 403


@app.errorhandler(404)
def e404(e):
    """Handle 404 errors."""
    return api_error("Not found", 404)


@app.errorhandler(Exception)
def on_unhandled_error(e):
    """Handle unhandled exceptions."""
    # In debug, let Flask show the full traceback page
    if app.debug:
        raise e

    # In non-debug, log and return friendly message
    try:
        if logger_txt:
            logger_txt.info(f"EXC on {request.path}: {e}")
        if logger_json:
            logger_json.info(json.dumps({
                "ts": datetime.utcnow().isoformat(timespec="seconds") + "Z",
                "route": request.path,
                "error": str(e),
                "tenant": (request.view_args or {}).get("tenant")
            }))
    except Exception:
        pass
    
    return make_response("Sorry—something went wrong. Please try the step-by-step quote.", 500)

# ==============================================================================
# CUSTOMER PORTAL ROUTES - Add to app.py
# ==============================================================================
# Add these routes after the existing console routes (around line 2003)
# Also add the email helper functions

# ==============================================================================
# CUSTOMER PORTAL - CONFIGURATION HELPER
# ==============================================================================

def _get_portal_config(cfg: dict, pricing: dict) -> dict:
    """
    Build the configuration object for the customer portal JavaScript.
    This combines garment catalog, printing tiers, and extras into one object.
    """
    portal = cfg.get("customer_portal", {}) or {}
    
    # Default garment catalog if not configured
    default_garments = {
        "categories": [
            {
                "key": "tshirts",
                "label": "T-Shirts",
                "items": [
                    {"key": "gildan-2000", "label": "Gildan 2000", "cost": 3.45, "price": 5.75},
                    {"key": "port-pc380", "label": "Port & Co PC380", "cost": 3.69, "price": 6.15},
                    {"key": "sporttek-st350", "label": "Sport-Tek ST350", "cost": 4.13, "price": 6.88},
                    {"key": "nextlevel-6210", "label": "Next Level 6210", "cost": 4.19, "price": 6.98}
                ]
            },
            {
                "key": "longsleeve",
                "label": "Long Sleeve Shirts",
                "items": [
                    {"key": "gildan-g2400", "label": "Gildan G2400", "cost": 5.05, "price": 8.42}
                ]
            },
            {
                "key": "sweatshirts",
                "label": "Sweatshirts & Hoodies",
                "items": [
                    {"key": "gildan-18000", "label": "Gildan 18000 Crewneck", "cost": 9.32, "price": 15.53},
                    {"key": "laneseven-ls14001", "label": "Lane Seven LS14001 Hoodie", "cost": 9.75, "price": 16.25},
                    {"key": "gildan-sf500b", "label": "Gildan SF500B Youth Hoodie", "cost": 10.82, "price": 18.03},
                    {"key": "port-pc78zh", "label": "Port & Co PC78ZH Zip Hoodie", "cost": 13.04, "price": 21.73},
                    {"key": "gildan-sf600", "label": "Gildan SF600 Zip Hoodie", "cost": 16.42, "price": 27.37}
                ]
            }
        ]
    }
    
    # Use configured garments or defaults
    garments = portal.get("garments", default_garments)
    
    # Get printing tiers from pricing.json
    printing = {}
    if pricing and "screen_print" in pricing:
        printing["tiers"] = pricing["screen_print"].get("tiers", {})
    
    # Extras configuration
    console_cfg = cfg.get("console", {}) or {}
    extras_cfg = console_cfg.get("extras", {}) or {}
    
    extras = {
        "rush_rate": float(extras_cfg.get("rush_multiplier", 0.50)),
        "names_per_item": float(extras_cfg.get("names_per_shirt", 2.00)),
        "numbers_per_item": float(extras_cfg.get("numbers_per_shirt", 2.00)),
        "fold_bag_per_item": float(extras_cfg.get("fold_bag_per_shirt", 1.25)),
        "tagging_per_item": float(extras_cfg.get("tagging_per_shirt", 0.50))
    }

    max_colors = console_cfg.get("max_colors_per_placement", {
    "front": 6,
    "back": 6,
    "left_sleeve": 3,
    "right_sleeve": 3
})
    
    return {
        "garments": garments,
        "printing": printing,
        "extras": extras,
        "max_colors_per_placement": max_colors
    }


# ==============================================================================
# CUSTOMER PORTAL - PAGE ROUTE
# ==============================================================================

@app.route("/quote/<tenant>")
def customer_portal(tenant: str):
    """Serve the customer-facing quote portal."""
    # Validate tenant
    valid, error = validate_tenant(tenant)
    if not valid:
        abort(404, error)
    
    cfg = _load_json(tenant, "config")
    pricing = _load_json(tenant, "pricing")
    
    # Check if portal is enabled (optional - defaults to enabled)
    portal_cfg = cfg.get("customer_portal", {})
    if portal_cfg.get("enabled") == False:
        abort(404, "Quote portal is not enabled for this shop")
    
    # Build portal config for JavaScript
    portal_config = _get_portal_config(cfg, pricing)
    
    return render_template(
        "portal.html",
        cfg=cfg,
        tenant=tenant,
        portal_config=portal_config
    )


# ==============================================================================
# CUSTOMER PORTAL - QUOTE SUBMISSION API
# ==============================================================================

@app.post("/api/customer-quote/<tenant>")
def api_customer_quote(tenant: str):
    """
    Handle customer quote submission from the portal.
    
    Validates the quote, recalculates server-side to prevent manipulation,
    sends email to customer and shop notification.
    """
    # Validate tenant
    valid, error = validate_tenant(tenant)
    if not valid:
        return api_error(error, 404)
    
    try:
        body = request.get_json(force=True, silent=True) or {}
        
        # Extract and validate required fields
        # Quantity
        raw_qty = body.get("quantity")
        valid, error, qty = validate_quantity(raw_qty, min_val=12)
        if not valid:
            return api_error(error)
        
        # Garment
        garment_key = (body.get("garment_key") or "").strip()
        garment_label = (body.get("garment_label") or "").strip()
        garment_price = body.get("garment_price")
        
        if not garment_key or not garment_label:
            return api_error("Please select a garment")
        
        try:
            garment_price = float(garment_price)
            if garment_price <= 0:
                raise ValueError()
        except (TypeError, ValueError):
            return api_error("Invalid garment price")
        
        # Locations
        locations = body.get("locations") or []
        if not locations or not isinstance(locations, list):
            return api_error("Please select at least one print location")
        
        validated_locations = []
        for i, loc in enumerate(locations):
            loc_name = (loc.get("location") or "").strip().lower()
            if not loc_name:
                continue
            
            raw_colors = loc.get("colors")
            valid, error, colors = validate_colors(raw_colors, max_val=6)
            if not valid:
                return api_error(f"Location {loc_name}: {error}")
            
            validated_locations.append({
                "location": loc_name,
                "colors": colors
            })
        
        if not validated_locations:
            return api_error("Please select at least one print location with colors")
        
        # Extras
        extras = body.get("extras") or {}
        rush = bool(extras.get("rush"))
        names = bool(extras.get("names"))
        numbers = bool(extras.get("numbers"))
        
        # Notes
        notes = (body.get("notes") or "").strip()[:1000]  # Limit notes length
        
        # Customer info
        customer = body.get("customer") or {}
        customer_name = (customer.get("name") or "").strip()
        customer_email = (customer.get("email") or "").strip()
        customer_phone = (customer.get("phone") or "").strip()
        customer_company = (customer.get("company") or "").strip()
        
        if not customer_name or len(customer_name) < 2:
            return api_error("Please enter your name")
        
        valid, error, customer_email = validate_email(customer_email)
        if not valid:
            return api_error(error)
        
        # Load config for server-side calculation
        cfg = _load_json(tenant, "config")
        pricing = _load_json(tenant, "pricing")
        portal_config = _get_portal_config(cfg, pricing)
        
        # SERVER-SIDE QUOTE CALCULATION (prevents price manipulation)
        # Garment total
        garment_total = qty * garment_price
        
        # Print total
        print_total = 0.0
        for loc in validated_locations:
            colors = loc["colors"]
            tier_key = f"{colors}_color"
            tiers = portal_config["printing"].get("tiers", {}).get(tier_key, {})
            
            print_cost = 0.50 * colors  # Fallback
            for band, price in tiers.items():
                clean_band = str(band).replace("–", "-")
                if "+" in clean_band:
                    min_qty = int(clean_band.replace("+", "").split("-")[0])
                    if qty >= min_qty:
                        print_cost = float(price)
                        break
                elif "-" in clean_band:
                    parts = clean_band.split("-")
                    min_qty, max_qty = int(parts[0]), int(parts[1])
                    if min_qty <= qty <= max_qty:
                        print_cost = float(price)
                        break
            
            print_total += print_cost * qty
        
        # Extras total
        extras_total = 0.0
        extras_breakdown = []
        
        if names:
            names_cost = portal_config["extras"]["names_per_item"] * qty
            extras_total += names_cost
            extras_breakdown.append({"name": "Individual Names", "amount": names_cost})
        
        if numbers:
            numbers_cost = portal_config["extras"]["numbers_per_item"] * qty
            extras_total += numbers_cost
            extras_breakdown.append({"name": "Individual Numbers", "amount": numbers_cost})

        if extras.get('fold_bag'):
            fold_bag_cost = portal_config["extras"]["fold_bag_per_item"] * qty
            extras_total += fold_bag_cost
            extras_breakdown.append({"name": "Fold & Bag", "amount": fold_bag_cost})

        if extras.get('tagging'):
            tagging_cost = portal_config["extras"]["tagging_per_item"] * qty
            extras_total += tagging_cost
            extras_breakdown.append({"name": "Tagging", "amount": tagging_cost})
        
        # Subtotal
        subtotal = garment_total + print_total + extras_total
        
        # Rush
        rush_amount = 0.0
        if rush:
            rush_rate = portal_config["extras"]["rush_rate"]
            rush_amount = subtotal * rush_rate
            extras_breakdown.append({"name": "Rush Order", "amount": rush_amount, "is_rush": True})
        
        # Total
        total = subtotal + rush_amount
        per_item = total / qty
        
        # Build quote summary for emails
        quote_summary = {
            "quantity": qty,
            "garment": garment_label,
            "garment_price": garment_price,
            "garment_total": round(garment_total, 2),
            "locations": [
                {
                    "name": _label_for(loc["location"]),
                    "colors": loc["colors"]
                }
                for loc in validated_locations
            ],
            "print_total": round(print_total, 2),
            "extras": extras_breakdown,
            "extras_total": round(extras_total + rush_amount, 2),
            "subtotal": round(subtotal, 2),
            "rush": rush,
            "rush_amount": round(rush_amount, 2),
            "total": round(total, 2),
            "per_item": round(per_item, 2),
            "notes": notes
        }
        
        customer_info = {
            "name": customer_name,
            "email": customer_email,
            "phone": customer_phone,
            "company": customer_company
        }
        
        # Log the quote
        log_turn(
            session_id=f"portal-{time.time()}",
            role="customer_quote",
            message=f"Customer quote: {qty}x {garment_label} = ${total:.2f}",
            meta={
                "tenant": tenant,
                "customer_email": customer_email,
                "quote_summary": quote_summary
            }
        )
        
        # Send emails
        shop_name = cfg.get("shop_name", tenant)
        
        # 1. Email to customer
        customer_email_sent = _send_customer_quote_email(
            tenant=tenant,
            cfg=cfg,
            customer=customer_info,
            quote=quote_summary,
            shop_name=shop_name
        )
        
        # 2. Email to shop (notification)
        shop_email_sent = _send_shop_notification_email(
            tenant=tenant,
            cfg=cfg,
            customer=customer_info,
            quote=quote_summary,
            shop_name=shop_name
        )
        
        return api_success({
            "quote_total": round(total, 2),
            "per_item": round(per_item, 2),
            "customer_email_sent": customer_email_sent,
            "shop_email_sent": shop_email_sent
        })
        
    except Exception as e:
        log_turn("api_customer_quote", "error", str(e), meta={"tenant": tenant})
        return api_error(str(e), 400)


# ==============================================================================
# CUSTOMER PORTAL - EMAIL HELPERS
# ==============================================================================

def _send_customer_quote_email(tenant: str, cfg: dict, customer: dict, quote: dict, shop_name: str) -> bool:
    """Send quote confirmation email to customer."""
    try:
        # Build email body
        locations_text = "\n".join([
            f"  • {loc['name']}: {loc['colors']} color{'s' if loc['colors'] > 1 else ''}"
            for loc in quote["locations"]
        ])
        
        extras_text = ""
        if quote["extras"]:
            extras_lines = []
            for extra in quote["extras"]:
                if extra.get("is_rush"):
                    extras_lines.append(f"  • Rush Order (+50%): ${extra['amount']:.2f}")
                else:
                    extras_lines.append(f"  • {extra['name']}: ${extra['amount']:.2f}")
            extras_text = "\n" + "\n".join(extras_lines)
        
        notes_text = ""
        if quote.get("notes"):
            notes_text = f"\n\nYour Notes:\n{quote['notes']}"
        
        body_text = f"""Hi {customer['name'].split()[0]},

Thanks for requesting a quote from {shop_name}!

Here's your quote summary:

{quote['quantity']} × {quote['garment']} @ ${quote['garment_price']:.2f}/ea = ${quote['garment_total']:.2f}

Print Locations:
{locations_text}

Printing: ${quote['print_total']:.2f}{extras_text}

━━━━━━━━━━━━━━━━━━━━━━━━━━
ESTIMATED TOTAL: ${quote['total']:.2f}
(${quote['per_item']:.2f} per item)
━━━━━━━━━━━━━━━━━━━━━━━━━━{notes_text}

What's next?
We'll review your request and get back to you within 24 hours to finalize details and artwork.

Questions? Just reply to this email.

Thanks,
{shop_name}
"""

        # Build HTML version
        locations_html = "".join([
            f"<li>{loc['name']}: {loc['colors']} color{'s' if loc['colors'] > 1 else ''}</li>"
            for loc in quote["locations"]
        ])
        
        extras_html = ""
        if quote["extras"]:
            extras_items = "".join([
                f"<li>{'Rush Order (+50%)' if extra.get('is_rush') else extra['name']}: ${extra['amount']:.2f}</li>"
                for extra in quote["extras"]
            ])
            extras_html = f"<ul>{extras_items}</ul>"
        
        notes_html = ""
        if quote.get("notes"):
            notes_html = f"<p><strong>Your Notes:</strong><br>{quote['notes']}</p>"
        
        body_html = f"""
<!DOCTYPE html>
<html>
<head>
    <style>
        body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; line-height: 1.6; color: #333; }}
        .container {{ max-width: 600px; margin: 0 auto; padding: 20px; }}
        .header {{ background: #0066cc; color: white; padding: 20px; text-align: center; border-radius: 8px 8px 0 0; }}
        .content {{ background: #f9f9f9; padding: 25px; border-radius: 0 0 8px 8px; }}
        .quote-box {{ background: white; padding: 20px; border-radius: 8px; margin: 20px 0; border: 1px solid #ddd; }}
        .total-box {{ background: #0066cc; color: white; padding: 15px; border-radius: 8px; text-align: center; margin: 20px 0; }}
        .total-box .amount {{ font-size: 28px; font-weight: bold; }}
        .total-box .per-item {{ font-size: 14px; opacity: 0.9; }}
        ul {{ margin: 10px 0; padding-left: 20px; }}
        li {{ margin: 5px 0; }}
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <h1 style="margin: 0;">Your Quote from {shop_name}</h1>
        </div>
        <div class="content">
            <p>Hi {customer['name'].split()[0]},</p>
            <p>Thanks for requesting a quote! Here's what we put together for you:</p>
            
            <div class="quote-box">
                <h3 style="margin-top: 0;">{quote['quantity']} × {quote['garment']}</h3>
                <p>@ ${quote['garment_price']:.2f}/ea = ${quote['garment_total']:.2f}</p>
                
                <h4>Print Locations:</h4>
                <ul>{locations_html}</ul>
                <p>Printing: ${quote['print_total']:.2f}</p>
                
                {f"<h4>Extras:</h4>{extras_html}" if extras_html else ""}
            </div>
            
            <div class="total-box">
                <div class="amount">${quote['total']:.2f}</div>
                <div class="per-item">${quote['per_item']:.2f} per item</div>
            </div>
            
            {notes_html}
            
            <h3>What's next?</h3>
            <p>We'll review your request and get back to you within 24 hours to finalize details and artwork.</p>
            
            <p>Questions? Just reply to this email.</p>
            
            <p>Thanks,<br><strong>{shop_name}</strong></p>
        </div>
    </div>
</body>
</html>
"""

        # Send via Postmark
        postmark_token = os.environ.get("POSTMARK_TOKEN")
        from_email = os.environ.get("FROM_EMAIL")
        stream = os.environ.get("POSTMARK_STREAM", "outbound")
        
        payload = {
            "From": from_email,
            "To": customer["email"],
            "Subject": f"Your Quote from {shop_name} - ${quote['total']:.2f}",
            "TextBody": body_text,
            "HtmlBody": body_html,
            "MessageStream": stream
        }
        
        resp = requests.post(
            "https://api.postmarkapp.com/email",
            headers={
                "Accept": "application/json",
                "Content-Type": "application/json",
                "X-Postmark-Server-Token": postmark_token
            },
            json=payload,
            timeout=30
        )
        
        return resp.status_code == 200
        
    except Exception as e:
        print(f"Error sending customer email: {e}")
        return False


def _send_shop_notification_email(tenant: str, cfg: dict, customer: dict, quote: dict, shop_name: str) -> bool:
    """Send notification email to shop owner about new quote request."""
    try:
        # Get shop notification email
        portal_cfg = cfg.get("customer_portal", {}) or {}
        shop_email = portal_cfg.get("notification_email") or os.environ.get("SHOP_BCC")
        
        if not shop_email:
            print(f"No shop notification email configured for {tenant}")
            return False
        
        # Build email body
        locations_text = "\n".join([
            f"  • {loc['name']}: {loc['colors']} color{'s' if loc['colors'] > 1 else ''}"
            for loc in quote["locations"]
        ])
        
        extras_text = "None"
        if quote["extras"]:
            extras_lines = []
            for extra in quote["extras"]:
                if extra.get("is_rush"):
                    extras_lines.append(f"  • Rush Order: ${extra['amount']:.2f}")
                else:
                    extras_lines.append(f"  • {extra['name']}: ${extra['amount']:.2f}")
            extras_text = "\n".join(extras_lines)
        
        contact_info = f"""Name: {customer['name']}
Email: {customer['email']}"""
        if customer.get("phone"):
            contact_info += f"\nPhone: {customer['phone']}"
        if customer.get("company"):
            contact_info += f"\nCompany: {customer['company']}"
        
        notes_text = quote.get("notes", "None")
        if not notes_text:
            notes_text = "None"
        
        body_text = f"""🎉 New Quote Request!

{contact_info}

━━━━━━━━━━━━━━━━━━━━━━━━━━
QUOTE DETAILS
━━━━━━━━━━━━━━━━━━━━━━━━━━

Quantity: {quote['quantity']}
Garment: {quote['garment']} @ ${quote['garment_price']:.2f}/ea

Print Locations:
{locations_text}

Extras:
{extras_text}

━━━━━━━━━━━━━━━━━━━━━━━━━━
QUOTED TOTAL: ${quote['total']:.2f} (${quote['per_item']:.2f}/ea)
━━━━━━━━━━━━━━━━━━━━━━━━━━

Customer Notes:
{notes_text}

---
Reply to {customer['email']} to follow up.
"""

        # Send via Postmark
        postmark_token = os.environ.get("POSTMARK_TOKEN")
        from_email = os.environ.get("FROM_EMAIL")
        stream = os.environ.get("POSTMARK_STREAM", "outbound")
        
        payload = {
            "From": from_email,
            "To": shop_email,
            "ReplyTo": customer["email"],
            "Subject": f"🎉 New Quote: {quote['quantity']}x {quote['garment']} - ${quote['total']:.2f}",
            "TextBody": body_text,
            "MessageStream": stream
        }
        
        resp = requests.post(
            "https://api.postmarkapp.com/email",
            headers={
                "Accept": "application/json",
                "Content-Type": "application/json",
                "X-Postmark-Server-Token": postmark_token
            },
            json=payload,
            timeout=30
        )
        
        return resp.status_code == 200
        
    except Exception as e:
        print(f"Error sending shop notification: {e}")
        return False


# ==============================================================================
# MAIN ENTRY POINT
# ==============================================================================

if __name__ == "__main__":
    debug = os.getenv("FLASK_DEBUG", "0") == "1"
    app.run(host="127.0.0.1", port=5050, debug=debug)

