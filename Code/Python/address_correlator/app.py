from flask import Flask, render_template, request, redirect, url_for, jsonify, flash
from flask_sqlalchemy import SQLAlchemy
from geopy.geocoders import Nominatim
from geopy.exc import GeocoderTimedOut, GeocoderServiceError
import re
import time

app = Flask(__name__)
app.config["SECRET_KEY"] = "change-this-secret-key"
app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///addresses.db"
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
db = SQLAlchemy(app)

geolocator = Nominatim(
    user_agent="address-correlator/1.0 (replace-with-your-contact)",
    timeout=12,
)

# ---------------------------------------------------------------------------
# model
# ---------------------------------------------------------------------------

class Address(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    address = db.Column(db.Text, nullable=False)
    name = db.Column(db.String(160), nullable=True)      # individual label on map
    tag = db.Column(db.String(160), nullable=True)       # group key for correlation
    color = db.Column(db.String(20), nullable=False, default="#ffffff")
    latitude = db.Column(db.Float, nullable=False)
    longitude = db.Column(db.Float, nullable=False)
    resolved_address = db.Column(db.Text, nullable=True)
    precision = db.Column(db.String(20), nullable=True)  # exact/street/neighborhood/city/manual

    def as_dict(self):
        return {
            "id": self.id,
            "address": self.address,
            "name": self.name or "",
            "tag": self.tag or "",
            "color": self.color,
            "lat": self.latitude,
            "lon": self.longitude,
            "resolved_address": self.resolved_address or "",
            "precision": self.precision or "",
        }

# ---------------------------------------------------------------------------
# geocoding: normalization + progressive fallback tuned for Brazilian data
# ---------------------------------------------------------------------------

HEX_RE = re.compile(r"^#(?:[0-9a-fA-F]{3}|[0-9a-fA-F]{6})$")

# Brazilian street-type abbreviations Nominatim often fails to parse.
BR_ABBREV = {
    "R": "Rua", "RUA": "Rua",
    "AV": "Avenida", "AVE": "Avenida", "AVN": "Avenida",
    "TV": "Travessa", "TRV": "Travessa", "TRAV": "Travessa",
    "AL": "Alameda", "ALM": "Alameda",
    "PC": "Praca", "PCA": "Praca", "PRC": "Praca",
    "LGO": "Largo",
    "ESTR": "Estrada", "EST": "Estrada",
    "ROD": "Rodovia",
    "PRQ": "Parque", "PQ": "Parque",
    "JD": "Jardim", "JDM": "Jardim",
    "VL": "Vila",
    "COND": "Condominio",
    "RES": "Residencial", "RESID": "Residencial",
    "CJ": "Conjunto", "CONJ": "Conjunto",
}

# unit / block fragments that confuse a building-level geocoder
UNIT_RE = re.compile(
    r"\b(BLOCO|BLC|BL|APTO|APT|AP|CASA|CS|FUNDOS|SALA|SL|LOTE|LT|QUADRA|QD)\.?\s*[\w-]*",
    re.IGNORECASE,
)


def expand_abbreviations(text):
    def repl(m):
        w = m.group(0)
        key = w.upper().rstrip(".")
        return BR_ABBREV.get(key, w)
    return re.sub(r"[A-Za-zÀ-ÿ]+\.?", repl, text)


def strip_units(text):
    cleaned = UNIT_RE.sub("", text)
    cleaned = re.sub(r"\s*,\s*(?:,\s*)+", ", ", cleaned)   # collapse empty segments
    cleaned = re.sub(r"\s{2,}", " ", cleaned).strip(" ,")
    return cleaned


def drop_leading_segment(text):
    parts = [p.strip() for p in text.split(",") if p.strip()]
    if len(parts) <= 1:
        return None
    return ", ".join(parts[1:])


def build_variants(raw):
    """Ordered (query, country_codes, precision) attempts, tightest first."""
    raw = raw.strip()
    expanded = expand_abbreviations(raw)
    no_unit = strip_units(expanded)

    variants = [
        (raw, None, "exact"),                       # as typed (also handles non-BR)
        (f"{raw}, Brazil", "br", "exact"),
        (f"{expanded}, Brazil", "br", "exact"),
        (f"{no_unit}, Brazil", "br", "street"),
    ]

    looser = no_unit
    for precision in ("neighborhood", "city"):
        dropped = drop_leading_segment(looser)
        if not dropped:
            break
        variants.append((f"{dropped}, Brazil", "br", precision))
        looser = dropped

    # de-duplicate while preserving order
    seen, ordered = set(), []
    for q, cc, pr in variants:
        if q in seen:
            continue
        seen.add(q)
        ordered.append((q, cc, pr))
    return ordered


def geocode_address(address):
    """Return (location, precision) or (None, None). Raises RuntimeError on service failure."""
    last_error = None
    for query, cc, precision in build_variants(address):
        try:
            location = geolocator.geocode(
                query,
                country_codes=cc,
                addressdetails=True,
                exactly_one=True,
                language="pt-BR",
            )
            time.sleep(1.0)  # respect Nominatim's ~1 req/sec policy
            if location:
                return location, precision
        except (GeocoderTimedOut, GeocoderServiceError) as exc:
            last_error = exc
            time.sleep(2)
    if last_error:
        raise RuntimeError(f"Geocoding service error: {last_error}")
    return None, None


def normalize_color(color, fallback="#ffffff"):
    color = (color or "").strip()
    return color if HEX_RE.match(color) else fallback

# ---------------------------------------------------------------------------
# palette used to auto-color bulk-uploaded tags
# ---------------------------------------------------------------------------

TAG_PALETTE = [
    "#8cff66", "#ffb000", "#6fb7ff", "#ff5f9e",
    "#c792ea", "#ff5555", "#5ff0d0", "#f5f56a",
    "#ff9f5f", "#7cffb0",
]


def color_for_tag(tag, _cache={}):
    if tag not in _cache:
        _cache[tag] = TAG_PALETTE[len(_cache) % len(TAG_PALETTE)]
    return _cache[tag]

# ---------------------------------------------------------------------------
# routes
# ---------------------------------------------------------------------------

@app.route("/")
def index():
    addresses = Address.query.order_by(Address.id.asc()).all()
    return render_template("index.html", addresses=[a.as_dict() for a in addresses])


@app.post("/add")
def add_address():
    address = request.form.get("address", "").strip()
    name = request.form.get("name", "").strip()
    tag = request.form.get("tag", "").strip()
    color = normalize_color(request.form.get("color"))
    lat_raw = request.form.get("lat", "").strip()
    lon_raw = request.form.get("lon", "").strip()

    if not address:
        flash("Address is required.", "error")
        return redirect(url_for("index"))

    # manual coordinates: type them by hand when geocoding can't resolve
    if lat_raw or lon_raw:
        try:
            lat, lon = float(lat_raw), float(lon_raw)
            if not (-90 <= lat <= 90 and -180 <= lon <= 180):
                raise ValueError
        except ValueError:
            flash("Manual coordinates must be valid lat, lon numbers.", "error")
            return redirect(url_for("index"))
        entry = Address(
            address=address, name=name, tag=tag, color=color,
            latitude=lat, longitude=lon,
            resolved_address="(manual coordinates)", precision="manual",
        )
        db.session.add(entry)
        db.session.commit()
        flash(f"Added at manual coordinates {lat:.5f}, {lon:.5f}", "ok")
        return redirect(url_for("index"))

    try:
        location, precision = geocode_address(address)
    except RuntimeError as exc:
        flash(str(exc), "error")
        return redirect(url_for("index"))

    if not location:
        flash(
            "Could not resolve this address, even after loosening street/unit "
            "details. Enter latitude/longitude manually below to place it anyway.",
            "error",
        )
        return redirect(url_for("index"))

    entry = Address(
        address=address, name=name, tag=tag, color=color,
        latitude=location.latitude, longitude=location.longitude,
        resolved_address=location.address, precision=precision,
    )
    db.session.add(entry)
    db.session.commit()
    flash(f"Resolved [{precision}]: {location.address}", "ok")
    return redirect(url_for("index"))


@app.post("/upload")
def upload_file():
    """
    Bulk-add from a .txt file, one entry per line:

        address;tag or color

    Rules:
      - second field that is a valid hex color -> marker color
      - any other second field                 -> tag (auto-colored per tag)
      - optional 3-field form: address;name;tag_or_color
      - blank lines, // lines, and bare # comment lines are skipped
    """
    file = request.files.get("file")
    if not file or not file.filename:
        flash("No file selected.", "error")
        return redirect(url_for("index"))

    try:
        raw = file.read().decode("utf-8", errors="replace")
    except Exception:
        flash("Could not read file.", "error")
        return redirect(url_for("index"))

    added, failed, skipped = 0, 0, 0
    for line in raw.splitlines():
        line = line.strip()
        if not line or line.startswith("//"):
            continue
        if line.startswith("#") and ";" not in line:  # comment, not a bare color
            continue

        parts = [p.strip() for p in line.split(";")]
        address = parts[0]
        name, tag, color = "", "", "#ffffff"

        if len(parts) == 2:
            second = parts[1]
            if HEX_RE.match(second):
                color = second
            else:
                tag = second
                color = color_for_tag(tag)
        elif len(parts) >= 3:
            name = parts[1]
            third = parts[2]
            if HEX_RE.match(third):
                color = third
            else:
                tag = third
                color = color_for_tag(tag)

        if not address:
            skipped += 1
            continue

        try:
            location, precision = geocode_address(address)
        except RuntimeError:
            failed += 1
            continue
        if not location:
            failed += 1
            continue

        db.session.add(Address(
            address=address, name=name, tag=tag, color=color,
            latitude=location.latitude, longitude=location.longitude,
            resolved_address=location.address, precision=precision,
        ))
        added += 1

    db.session.commit()
    flash(
        f"Upload complete: {added} added, {failed} unresolved, {skipped} skipped. "
        f"Unresolved lines can be added manually with coordinates.",
        "ok" if added else "error",
    )
    return redirect(url_for("index"))


@app.post("/delete/<int:address_id>")
def delete_address(address_id):
    entry = db.get_or_404(Address, address_id)
    db.session.delete(entry)
    db.session.commit()
    return redirect(url_for("index"))


@app.post("/clear")
def clear_all():
    Address.query.delete()
    db.session.commit()
    return redirect(url_for("index"))


@app.get("/api/addresses")
def api_addresses():
    return jsonify([a.as_dict() for a in Address.query.order_by(Address.id.asc()).all()])


with app.app_context():
    db.create_all()

if __name__ == "__main__":
    app.run(host="127.0.0.1", port=5000, debug=True)
