"""Logo Studio: instant vector (SVG) logo concepts generated locally, plus prompts for AI-rendered concepts."""
import hashlib
import re
from xml.sax.saxutils import escape

NAMED_COLORS = {
    "blue": "#2563eb", "navy": "#1e3a8a", "sky": "#0ea5e9", "cyan": "#06b6d4", "teal": "#0d9488",
    "green": "#16a34a", "emerald": "#059669", "lime": "#65a30d", "olive": "#6b7c32", "mint": "#34d399",
    "yellow": "#eab308", "gold": "#d4a017", "amber": "#f59e0b", "orange": "#f97316", "coral": "#fb7185",
    "red": "#dc2626", "crimson": "#be123c", "maroon": "#7f1d1d", "pink": "#ec4899", "rose": "#f43f5e",
    "magenta": "#d946ef", "purple": "#7c3aed", "violet": "#8b5cf6", "indigo": "#4f46e5", "lavender": "#a78bfa",
    "brown": "#92400e", "beige": "#d6c7a1", "black": "#0b0b0f", "white": "#ffffff", "gray": "#6b7280",
    "grey": "#6b7280", "silver": "#9ca3af", "charcoal": "#1f2937", "turquoise": "#14b8a6",
}

INDUSTRY_DEFAULTS = {
    "tech": (["#2563eb", "#06b6d4"], "nodes"), "software": (["#4f46e5", "#06b6d4"], "code"),
    "ai": (["#ef4444", "#3b82f6"], "nodes"), "finance": (["#0f766e", "#d4a017"], "bars"),
    "bank": (["#1e3a8a", "#d4a017"], "shield"), "health": (["#0ea5e9", "#22c55e"], "heart"),
    "medical": (["#0ea5e9", "#ef4444"], "plus"), "food": (["#f97316", "#16a34a"], "leaf"),
    "restaurant": (["#dc2626", "#f59e0b"], "leaf"), "coffee": (["#6f4e37", "#d6c7a1"], "leaf"),
    "education": (["#4f46e5", "#f59e0b"], "book"), "fashion": (["#111827", "#ec4899"], "diamond"),
    "beauty": (["#db2777", "#f9a8d4"], "diamond"), "travel": (["#0ea5e9", "#f97316"], "mountain"),
    "sport": (["#dc2626", "#111827"], "bolt"), "fitness": (["#16a34a", "#111827"], "bolt"),
    "energy": (["#f59e0b", "#16a34a"], "bolt"), "real estate": (["#1f2937", "#d4a017"], "house"),
    "construction": (["#f59e0b", "#1f2937"], "house"), "music": (["#7c3aed", "#ec4899"], "wave"),
    "media": (["#ef4444", "#111827"], "play"), "game": (["#7c3aed", "#22d3ee"], "play"),
    "eco": (["#16a34a", "#65a30d"], "leaf"), "security": (["#111827", "#2563eb"], "shield"),
}

SYMBOL_KEYWORDS = {
    "leaf": "leaf", "plant": "leaf", "nature": "leaf", "bolt": "bolt", "lightning": "bolt", "power": "bolt",
    "star": "star", "heart": "heart", "love": "heart", "mountain": "mountain", "peak": "mountain",
    "wave": "wave", "water": "wave", "ocean": "wave", "shield": "shield", "secure": "shield",
    "diamond": "diamond", "gem": "diamond", "house": "house", "home": "house", "book": "book",
    "plus": "plus", "cross": "plus", "node": "nodes", "network": "nodes", "molecule": "nodes", "ai": "nodes",
    "code": "code", "bracket": "code", "chart": "bars", "growth": "bars", "graph": "bars", "play": "play",
    "rocket": "arrow", "arrow": "arrow", "sun": "sun", "circle": "ring", "ring": "ring", "hexagon": "hex",
    "cube": "hex", "infinity": "infinity", "spark": "spark", "globe": "globe", "world": "globe",
}

FONTS = {
    "modern": "'Segoe UI', 'Helvetica Neue', Arial, sans-serif",
    "geometric": "'Century Gothic', 'Trebuchet MS', Futura, 'Segoe UI', sans-serif",
    "bold": "'Arial Black', 'Segoe UI Black', Impact, sans-serif",
    "serif": "Georgia, 'Times New Roman', serif",
    "elegant": "'Palatino Linotype', 'Book Antiqua', Palatino, Georgia, serif",
    "mono": "Consolas, 'Courier New', monospace",
    "script": "'Segoe Script', 'Brush Script MT', 'Lucida Handwriting', cursive",
    "rounded": "'Arial Rounded MT Bold', 'Segoe UI', sans-serif",
}


def _parse_colors(text):
    found = []
    for hx in re.findall(r"#(?:[0-9a-fA-F]{6}|[0-9a-fA-F]{3})\b", text or ""):
        if len(hx) == 4:
            hx = "#" + "".join(c * 2 for c in hx[1:])
        found.append(hx.lower())
    for word in re.findall(r"[a-zA-Z]+", (text or "").lower()):
        if word in NAMED_COLORS and NAMED_COLORS[word] not in found:
            found.append(NAMED_COLORS[word])
    return found


def _word_match(key, text):
    # Long keywords match word prefixes ("tech" -> "technology"); short ones ("ai") must be whole words.
    pattern = rf"\b{re.escape(key)}\w*" if len(key) >= 4 else rf"\b{re.escape(key)}s?\b"
    return re.search(pattern, text) is not None


def _industry_defaults(industry):
    ind = (industry or "").lower()
    for key, val in INDUSTRY_DEFAULTS.items():
        if _word_match(key, ind):
            return val
    return (["#ef4444", "#3b82f6"], "spark")


def _symbol_key(symbol_text, fallback):
    s = (symbol_text or "").lower()
    for word, key in SYMBOL_KEYWORDS.items():
        if _word_match(word, s):
            return key
    return fallback


def _luma(hex_color):
    h = hex_color.lstrip("#")
    r, g, b = (int(h[i:i + 2], 16) for i in (0, 2, 4))
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def _symbol(key, c1, c2):
    """SVG markup for a symbol drawn in a 100x100 box."""
    shapes = {
        "leaf": f'<path d="M20 80 C20 35 50 15 85 15 C85 55 65 85 20 80 Z" fill="{c1}"/><path d="M22 78 L70 30" stroke="{c2}" stroke-width="5" stroke-linecap="round"/>',
        "bolt": f'<path d="M58 5 L18 58 H46 L38 95 L82 38 H54 Z" fill="{c1}"/>',
        "star": f'<path d="M50 6 L62 38 L96 38 L68 58 L79 92 L50 71 L21 92 L32 58 L4 38 L38 38 Z" fill="{c1}"/>',
        "heart": f'<path d="M50 88 C10 60 5 35 22 20 C35 9 48 16 50 28 C52 16 65 9 78 20 C95 35 90 60 50 88 Z" fill="{c1}"/>',
        "mountain": f'<path d="M5 85 L38 30 L55 58 L66 42 L95 85 Z" fill="{c1}"/><path d="M38 30 L46 43 L38 40 L30 44 Z" fill="{c2}"/><circle cx="74" cy="22" r="9" fill="{c2}"/>',
        "wave": f'<path d="M5 45 C20 25 35 25 50 45 S80 65 95 45" stroke="{c1}" stroke-width="10" fill="none" stroke-linecap="round"/><path d="M5 68 C20 48 35 48 50 68 S80 88 95 68" stroke="{c2}" stroke-width="10" fill="none" stroke-linecap="round"/>',
        "shield": f'<path d="M50 5 L88 18 V48 C88 72 70 88 50 95 C30 88 12 72 12 48 V18 Z" fill="{c1}"/><path d="M34 50 L46 62 L68 38" stroke="#fff" stroke-width="8" fill="none" stroke-linecap="round" stroke-linejoin="round"/>',
        "diamond": f'<path d="M50 92 L8 38 L26 12 H74 L92 38 Z" fill="{c1}"/><path d="M8 38 H92 M26 12 L40 38 L50 92 L60 38 L74 12" stroke="{c2}" stroke-width="3" fill="none"/>',
        "house": f'<path d="M50 10 L92 46 H80 V90 H20 V46 H8 Z" fill="{c1}"/><rect x="40" y="58" width="20" height="32" rx="2" fill="{c2}"/>',
        "book": f'<path d="M10 20 C25 14 40 16 50 26 V88 C40 78 25 76 10 82 Z" fill="{c1}"/><path d="M90 20 C75 14 60 16 50 26 V88 C60 78 75 76 90 82 Z" fill="{c2}"/>',
        "plus": f'<rect x="36" y="8" width="28" height="84" rx="8" fill="{c1}"/><rect x="8" y="36" width="84" height="28" rx="8" fill="{c2}"/>',
        "nodes": f'<path d="M30 25 L62 52 M24 52 H62 M30 79 L62 52" stroke="{c2}" stroke-width="6" stroke-linecap="round"/><circle cx="30" cy="25" r="10" fill="{c1}"/><circle cx="24" cy="52" r="10" fill="{c2}"/><circle cx="30" cy="79" r="10" fill="{c1}"/><circle cx="70" cy="52" r="20" fill="{c1}"/>',
        "code": f'<path d="M35 22 L10 50 L35 78" stroke="{c1}" stroke-width="10" fill="none" stroke-linecap="round" stroke-linejoin="round"/><path d="M65 22 L90 50 L65 78" stroke="{c1}" stroke-width="10" fill="none" stroke-linecap="round" stroke-linejoin="round"/><path d="M56 15 L44 85" stroke="{c2}" stroke-width="8" stroke-linecap="round"/>',
        "bars": f'<rect x="10" y="58" width="18" height="32" rx="4" fill="{c2}"/><rect x="41" y="38" width="18" height="52" rx="4" fill="{c1}"/><rect x="72" y="14" width="18" height="76" rx="4" fill="{c1}"/>',
        "play": f'<circle cx="50" cy="50" r="44" fill="{c1}"/><path d="M40 30 L72 50 L40 70 Z" fill="#fff"/>',
        "arrow": f'<path d="M15 85 L85 15 M45 15 H85 V55" stroke="{c1}" stroke-width="12" fill="none" stroke-linecap="round" stroke-linejoin="round"/>',
        "sun": f'<circle cx="50" cy="50" r="20" fill="{c1}"/>' + "".join(
            f'<rect x="47" y="4" width="6" height="16" rx="3" fill="{c2}" transform="rotate({a} 50 50)"/>' for a in range(0, 360, 45)),
        "ring": f'<circle cx="50" cy="50" r="38" stroke="{c1}" stroke-width="12" fill="none"/><circle cx="50" cy="50" r="14" fill="{c2}"/>',
        "hex": f'<path d="M50 5 L89 27 V73 L50 95 L11 73 V27 Z" fill="{c1}"/><path d="M50 5 V50 L89 73 M50 50 L11 73" stroke="{c2}" stroke-width="4" fill="none"/>',
        "infinity": f'<path d="M50 50 C38 30 12 30 12 50 C12 70 38 70 50 50 C62 30 88 30 88 50 C88 70 62 70 50 50 Z" stroke="{c1}" stroke-width="10" fill="none"/>',
        "spark": f'<path d="M50 4 C54 36 64 46 96 50 C64 54 54 64 50 96 C46 64 36 54 4 50 C36 46 46 36 50 4 Z" fill="{c1}"/><circle cx="80" cy="20" r="7" fill="{c2}"/>',
        "globe": f'<circle cx="50" cy="50" r="40" stroke="{c1}" stroke-width="7" fill="none"/><ellipse cx="50" cy="50" rx="16" ry="40" stroke="{c2}" stroke-width="5" fill="none"/><path d="M12 50 H88 M18 30 H82 M18 70 H82" stroke="{c1}" stroke-width="4"/>',
    }
    return shapes.get(key, shapes["spark"])


def _initials(name):
    words = [w for w in re.split(r"[\s\-_]+", name) if w]
    if len(words) >= 2:
        return (words[0][0] + words[1][0]).upper()
    caps = re.findall(r"[A-Z]", name)
    if len(caps) >= 2:
        return (caps[0] + caps[1]).upper()
    return name[:1].upper() or "?"


def _wrap(body, bg, w=600, h=400):
    return (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {w} {h}" width="{w}" height="{h}">'
            f'<defs><linearGradient id="g" x1="0" y1="0" x2="1" y2="1"><stop offset="0" stop-color="{{C1}}"/>'
            f'<stop offset="1" stop-color="{{C2}}"/></linearGradient></defs>'
            f'<rect width="{w}" height="{h}" fill="{bg}"/>{body}</svg>')


def generate_concepts(brand, industry="", style="", colors="", symbol="", typography=""):
    """Returns a list of dicts: {title, svg}. Deterministic for the same input so 'regenerate' varies via style."""
    brand = (brand or "Brand").strip()[:40]
    name = escape(brand)
    default_colors, default_symbol = _industry_defaults(industry)
    palette = _parse_colors(colors) or default_colors
    c1 = palette[0]
    c2 = palette[1] if len(palette) > 1 else default_colors[1]
    if c2 == c1:
        c2 = default_colors[1] if default_colors[1] != c1 else "#111827"
    # Avoid white-on-white: if a color is very light, it becomes the background on dark variants.
    if _luma(c1) > 225:
        c1, c2 = c2, c1
    sym_key = _symbol_key(symbol, default_symbol)
    st = (style or "").lower()
    font_key = (typography or "").lower()
    font = next((v for k, v in FONTS.items() if k in font_key), None)
    if font is None:
        font = FONTS["serif"] if any(k in st for k in ("luxury", "elegant", "classic", "vintage")) else (
            FONTS["bold"] if any(k in st for k in ("bold", "sport", "strong")) else FONTS["geometric"])
    dark_bg = "#0b0d14"
    light_bg = "#ffffff"
    ink = "#0f172a"
    initials = escape(_initials(brand))
    tag = escape((industry or "").strip().upper()[:28])
    fs = max(34, min(64, int(560 / max(len(brand), 1))))
    sym = _symbol(sym_key, "url(#g)", c2)
    sym_white = _symbol(sym_key, "#ffffff", c2)
    tag_svg = lambda x, y, fill, anchor="middle": (
        f'<text x="{x}" y="{y}" font-family="{FONTS["modern"]}" font-size="13" letter-spacing="5" fill="{fill}" '
        f'text-anchor="{anchor}" opacity="0.7">{tag}</text>' if tag else "")

    concepts = [
        ("Symbol + wordmark",
         _wrap(f'<g transform="translate(250 70) scale(1.0)">{sym}</g>'
               f'<text x="300" y="260" font-family="{font}" font-size="{fs}" font-weight="700" fill="{ink}" text-anchor="middle">{name}</text>'
               + tag_svg(300, 300, ink), light_bg)),
        ("Horizontal lockup",
         _wrap(f'<g transform="translate(60 150) scale(1.0)">{sym}</g>'
               f'<text x="185" y="208" font-family="{font}" font-size="{min(fs, 58)}" font-weight="700" fill="{ink}">{name}</text>'
               + tag_svg(187, 238, ink, "start"), light_bg)),
        ("Monogram badge",
         _wrap(f'<circle cx="300" cy="160" r="92" fill="url(#g)"/>'
               f'<text x="300" y="{160 + 30}" font-family="{font}" font-size="84" font-weight="700" fill="#fff" text-anchor="middle">{initials}</text>'
               f'<text x="300" y="320" font-family="{font}" font-size="{min(fs, 46)}" font-weight="700" fill="{ink}" text-anchor="middle" letter-spacing="2">{name}</text>',
               light_bg)),
        ("App icon (dark)",
         _wrap(f'<rect x="220" y="60" width="160" height="160" rx="40" fill="url(#g)"/>'
               f'<g transform="translate(250 90) scale(1.0)">{sym_white}</g>'
               f'<text x="300" y="300" font-family="{font}" font-size="{min(fs, 50)}" font-weight="700" fill="#fff" text-anchor="middle">{name}</text>'
               + tag_svg(300, 335, "#fff"), dark_bg)),
        ("Wordmark",
         _wrap(f'<text x="300" y="215" font-family="{font}" font-size="{fs + 8}" font-weight="800" fill="url(#g)" text-anchor="middle" letter-spacing="1">{name}</text>'
               f'<rect x="250" y="240" width="100" height="6" rx="3" fill="{c2}"/>' + tag_svg(300, 280, ink), light_bg)),
        ("Emblem",
         _wrap(f'<path d="M300 40 L390 92 V196 L300 248 L210 196 V92 Z" fill="none" stroke="url(#g)" stroke-width="8"/>'
               f'<g transform="translate(262 106) scale(0.76)">{sym}</g>'
               f'<text x="300" y="315" font-family="{font}" font-size="{min(fs, 44)}" font-weight="700" fill="{ink}" text-anchor="middle" letter-spacing="4">{name.upper()}</text>'
               + tag_svg(300, 345, ink), light_bg)),
    ]
    out = []
    for title, svg in concepts:
        out.append({"title": title, "svg": svg.replace("{C1}", c1).replace("{C2}", c2)})
    return out


def ai_logo_prompt(brand, industry="", style="", colors="", symbol="", typography="", variant=0):
    looks = ["flat vector logo", "minimal geometric logo mark", "modern emblem logo", "clean lettermark logo"]
    parts = [f'{looks[variant % len(looks)]} for a brand named "{brand.strip()[:40]}"']
    if industry:
        parts.append(f"{industry.strip()[:60]} company")
    if style:
        parts.append(f"{style.strip()[:60]} style")
    if colors:
        parts.append(f"color palette: {colors.strip()[:60]}")
    if symbol:
        parts.append(f"symbol: {symbol.strip()[:80]}")
    if typography:
        parts.append(f"{typography.strip()[:40]} typography")
    parts.append("professional brand identity, centered, plain white background, crisp edges, high quality, "
                 "no mockup, no photo, no extra text")
    return ", ".join(parts)


def svg_fingerprint(svg):
    return hashlib.sha1(svg.encode()).hexdigest()[:10]
