#!/usr/bin/env python3
"""
FinancialOS Kenya — County Fiscal Intelligence Platform
Batch 1: Core scaffold, models, auth, template filters, entry point.
"""

import os
import re
import io
import csv
import json
import uuid
import threading
from datetime import datetime
from functools import wraps

from flask import (Flask, render_template, redirect, url_for, abort,
                   request, flash, jsonify, send_file, session)
from flask_sqlalchemy import SQLAlchemy
from flask_login import (LoginManager, UserMixin, login_user, logout_user,
                         login_required, current_user)
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename

# ---------------------------------------------------------------------------
# Optional dependencies — degrade gracefully if not installed yet
# ---------------------------------------------------------------------------
try:
    import pdfplumber
    PDF_AVAILABLE = True
except ImportError:
    PDF_AVAILABLE = False

try:
    import anthropic
    AI_AVAILABLE = True
except ImportError:
    AI_AVAILABLE = False

try:
    import openpyxl          # noqa: F401
    EXCEL_AVAILABLE = True
except ImportError:
    EXCEL_AVAILABLE = False

# ---------------------------------------------------------------------------
# App configuration
# ---------------------------------------------------------------------------

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

app = Flask(__name__)
app.config.update(
    SECRET_KEY=os.environ.get("SECRET_KEY", "kenya-fiscal-intelligence-dev-2024"),
    SQLALCHEMY_DATABASE_URI=(
        f"sqlite:///{os.path.join(BASE_DIR, 'instance', 'fiscal.db')}"
    ),
    SQLALCHEMY_TRACK_MODIFICATIONS=False,
    UPLOAD_FOLDER=os.path.join(BASE_DIR, "uploads"),
    MAX_CONTENT_LENGTH=100 * 1024 * 1024,   # 100 MB
    ALLOWED_EXTENSIONS={"pdf"},
    ANTHROPIC_API_KEY=os.environ.get("ANTHROPIC_API_KEY", ""),
)

os.makedirs(app.config["UPLOAD_FOLDER"], exist_ok=True)
os.makedirs(os.path.join(BASE_DIR, "instance"), exist_ok=True)

db = SQLAlchemy(app)
login_manager = LoginManager(app)
login_manager.login_view = "login"
login_manager.login_message_category = "info"

# ---------------------------------------------------------------------------
# Kenya domain constants
# ---------------------------------------------------------------------------

KENYA_COUNTIES = [
    (1,  "Mombasa",          "Coast"),
    (2,  "Kwale",            "Coast"),
    (3,  "Kilifi",           "Coast"),
    (4,  "Tana River",       "Coast"),
    (5,  "Lamu",             "Coast"),
    (6,  "Taita Taveta",     "Coast"),
    (7,  "Garissa",          "North Eastern"),
    (8,  "Wajir",            "North Eastern"),
    (9,  "Mandera",          "North Eastern"),
    (10, "Marsabit",         "Eastern"),
    (11, "Isiolo",           "Eastern"),
    (12, "Meru",             "Eastern"),
    (13, "Tharaka Nithi",    "Eastern"),
    (14, "Embu",             "Eastern"),
    (15, "Kitui",            "Eastern"),
    (16, "Machakos",         "Eastern"),
    (17, "Makueni",          "Eastern"),
    (18, "Nyandarua",        "Central"),
    (19, "Nyeri",            "Central"),
    (20, "Kirinyaga",        "Central"),
    (21, "Murang'a",         "Central"),
    (22, "Kiambu",           "Central"),
    (23, "Turkana",          "Rift Valley"),
    (24, "West Pokot",       "Rift Valley"),
    (25, "Samburu",          "Rift Valley"),
    (26, "Trans Nzoia",      "Rift Valley"),
    (27, "Uasin Gishu",      "Rift Valley"),
    (28, "Elgeyo Marakwet",  "Rift Valley"),
    (29, "Nandi",            "Rift Valley"),
    (30, "Baringo",          "Rift Valley"),
    (31, "Laikipia",         "Rift Valley"),
    (32, "Nakuru",           "Rift Valley"),
    (33, "Narok",            "Rift Valley"),
    (34, "Kajiado",          "Rift Valley"),
    (35, "Kericho",          "Rift Valley"),
    (36, "Bomet",            "Rift Valley"),
    (37, "Kakamega",         "Western"),
    (38, "Vihiga",           "Western"),
    (39, "Bungoma",          "Western"),
    (40, "Busia",            "Western"),
    (41, "Siaya",            "Nyanza"),
    (42, "Kisumu",           "Nyanza"),
    (43, "Homa Bay",         "Nyanza"),
    (44, "Migori",           "Nyanza"),
    (45, "Kisii",            "Nyanza"),
    (46, "Nyamira",          "Nyanza"),
    (47, "Nairobi City",     "Nairobi"),
]

FISCAL_YEARS = ["2019/20", "2020/21", "2021/22", "2022/23", "2023/24"]

SOURCES = [
    ("CoB",   "Controller of Budget"),
    ("OAG",   "Office of the Auditor-General"),
    ("CRA",   "Commission for Revenue Allocation"),
    ("Other", "Other Source"),
]

REPORT_PERIODS = [
    ("annual", "Annual Report"),
    ("q1",     "Q1 (July – September)"),
    ("h1",     "Half-Year (July – December)"),
    ("q3",     "Q3 / Nine-Month (July – March)"),
]

DOCUMENT_TYPES = [
    "County Budget Implementation Review Report (CBIRR)",
    "Auditor-General Report – County Executive",
    "Auditor-General Report – County Assembly",
    "County Fiscal Strategy Paper",
    "Annual Development Plan",
    "Budget Estimates",
    "County Annual Progress Report",
    "Other Fiscal Document",
]

AUDIT_OPINIONS = ["unqualified", "qualified", "adverse", "disclaimer"]

# ---------------------------------------------------------------------------
# Database models
# ---------------------------------------------------------------------------

class User(UserMixin, db.Model):
    __tablename__ = "users"

    id            = db.Column(db.Integer, primary_key=True)
    username      = db.Column(db.String(80),  unique=True, nullable=False)
    email         = db.Column(db.String(120), unique=True, nullable=False)
    password_hash = db.Column(db.String(256))
    role          = db.Column(db.String(20), default="viewer")   # admin | analyst | viewer
    is_active     = db.Column(db.Boolean, default=True)
    created_at    = db.Column(db.DateTime, default=datetime.utcnow)
    last_login    = db.Column(db.DateTime)

    def set_password(self, password: str) -> None:
        self.password_hash = generate_password_hash(password)

    def check_password(self, password: str) -> bool:
        return check_password_hash(self.password_hash, password)

    def can_upload(self) -> bool:
        return self.role == "admin"

    def can_export(self) -> bool:
        return self.role in ("admin", "analyst")

    def __repr__(self) -> str:
        return f"<User {self.username} ({self.role})>"


class County(db.Model):
    __tablename__ = "counties"

    id         = db.Column(db.Integer, primary_key=True)
    code       = db.Column(db.Integer, unique=True, nullable=False)
    name       = db.Column(db.String(100), unique=True, nullable=False)
    region     = db.Column(db.String(50))
    population = db.Column(db.Integer)

    documents      = db.relationship("Document",     backref="county", lazy=True)
    metrics        = db.relationship("FiscalMetric", backref="county", lazy=True)
    audit_opinions = db.relationship("AuditOpinion", backref="county", lazy=True)

    def __repr__(self) -> str:
        return f"<County {self.code:02d} {self.name}>"


class Document(db.Model):
    __tablename__ = "documents"

    id               = db.Column(db.Integer, primary_key=True)
    uuid             = db.Column(db.String(36), unique=True, default=lambda: str(uuid.uuid4()))
    original_filename = db.Column(db.String(255))
    stored_filename  = db.Column(db.String(255))
    filepath         = db.Column(db.String(512))

    # User-provided metadata (captured at upload time)
    source          = db.Column(db.String(10))    # CoB | OAG | CRA | Other
    fiscal_year     = db.Column(db.String(20))    # e.g. "2022/23"
    county_id       = db.Column(db.Integer, db.ForeignKey("counties.id"))
    county_name     = db.Column(db.String(100))   # "All Counties" or specific name
    report_period   = db.Column(db.String(20))    # annual | q1 | h1 | q3
    document_type   = db.Column(db.String(200))
    notes           = db.Column(db.Text)

    # Auto-extracted by the PDF processing engine
    page_count      = db.Column(db.Integer)
    detected_title  = db.Column(db.String(500))
    file_size       = db.Column(db.Integer)       # bytes
    text_content    = db.Column(db.Text)          # full extracted text (searchable)

    # Processing lifecycle
    processing_status       = db.Column(db.String(20), default="pending")
    processing_error        = db.Column(db.Text)
    processing_completed_at = db.Column(db.DateTime)

    # Audit trail
    upload_date      = db.Column(db.DateTime, default=datetime.utcnow)
    uploaded_by_id   = db.Column(db.Integer, db.ForeignKey("users.id"))
    uploaded_by      = db.relationship("User", backref="uploads",
                                       foreign_keys=[uploaded_by_id])

    metrics        = db.relationship("FiscalMetric", backref="document", lazy=True)
    audit_opinions = db.relationship("AuditOpinion", backref="document", lazy=True)

    def to_dict(self) -> dict:
        return {
            "id":                self.id,
            "original_filename": self.original_filename,
            "source":            self.source,
            "fiscal_year":       self.fiscal_year,
            "county_name":       self.county_name,
            "report_period":     self.report_period,
            "document_type":     self.document_type,
            "page_count":        self.page_count,
            "file_size":         self.file_size,
            "upload_date":       self.upload_date.isoformat() if self.upload_date else None,
            "processing_status": self.processing_status,
        }

    def __repr__(self) -> str:
        return f"<Document {self.id} {self.original_filename}>"


class FiscalMetric(db.Model):
    __tablename__ = "fiscal_metrics"

    id              = db.Column(db.Integer, primary_key=True)
    document_id     = db.Column(db.Integer, db.ForeignKey("documents.id"))
    county_id       = db.Column(db.Integer, db.ForeignKey("counties.id"))
    fiscal_year     = db.Column(db.String(20))
    metric_name     = db.Column(db.String(100))   # total_revenue, own_source_revenue, …
    metric_value    = db.Column(db.Float)          # in KES millions
    currency        = db.Column(db.String(10), default="KES")
    unit            = db.Column(db.String(20),  default="millions")
    confidence_score = db.Column(db.Float,     default=0.80)
    source_text     = db.Column(db.String(500))   # snippet that triggered extraction
    created_at      = db.Column(db.DateTime, default=datetime.utcnow)

    def __repr__(self) -> str:
        return f"<FiscalMetric {self.metric_name}={self.metric_value} ({self.fiscal_year})>"


class AuditOpinion(db.Model):
    __tablename__ = "audit_opinions"

    id               = db.Column(db.Integer, primary_key=True)
    document_id      = db.Column(db.Integer, db.ForeignKey("documents.id"))
    county_id        = db.Column(db.Integer, db.ForeignKey("counties.id"))
    fiscal_year      = db.Column(db.String(20))
    opinion_type     = db.Column(db.String(50))   # unqualified | qualified | adverse | disclaimer
    material_issues  = db.Column(db.Integer, default=0)
    key_observations = db.Column(db.Text)         # JSON-encoded list of strings
    pending_bills    = db.Column(db.Float)        # KES millions
    created_at       = db.Column(db.DateTime, default=datetime.utcnow)

    def observations_list(self) -> list:
        if not self.key_observations:
            return []
        try:
            return json.loads(self.key_observations)
        except (json.JSONDecodeError, TypeError):
            return [self.key_observations]

    def __repr__(self) -> str:
        return f"<AuditOpinion {self.opinion_type} {self.fiscal_year}>"


# ---------------------------------------------------------------------------
# Auth helpers
# ---------------------------------------------------------------------------

@login_manager.user_loader
def load_user(user_id: str):
    return User.query.get(int(user_id))


def admin_required(f):
    """Restrict a route to admin users only."""
    @wraps(f)
    def decorated(*args, **kwargs):
        if not current_user.is_authenticated or current_user.role != "admin":
            abort(403)
        return f(*args, **kwargs)
    return decorated


def analyst_required(f):
    """Restrict a route to admin or analyst users."""
    @wraps(f)
    def decorated(*args, **kwargs):
        if not current_user.is_authenticated or current_user.role not in ("admin", "analyst"):
            abort(403)
        return f(*args, **kwargs)
    return decorated


# ---------------------------------------------------------------------------
# Template filters
# ---------------------------------------------------------------------------

@app.template_filter("fmt_millions")
def fmt_millions(value):
    """Format a KES-millions float for display."""
    if value is None:
        return "—"
    if value >= 1_000:
        return f"KES {value / 1_000:.1f}B"
    return f"KES {value:.1f}M"


@app.template_filter("fmt_number")
def fmt_number(value):
    if value is None:
        return "—"
    return f"{value:,.0f}"


@app.template_filter("opinion_class")
def opinion_class(opinion: str) -> str:
    return {
        "unqualified": "badge-success",
        "qualified":   "badge-warning",
        "adverse":     "badge-danger",
        "disclaimer":  "badge-critical",
    }.get(opinion or "", "badge-neutral")


@app.template_filter("opinion_label")
def opinion_label(opinion: str) -> str:
    return {
        "unqualified": "Clean",
        "qualified":   "Qualified",
        "adverse":     "Adverse",
        "disclaimer":  "Disclaimer",
    }.get(opinion or "", "Unknown")


@app.template_filter("filesize")
def filesize_filter(size_bytes) -> str:
    if not size_bytes:
        return "—"
    if size_bytes < 1_024:
        return f"{size_bytes} B"
    if size_bytes < 1_024 ** 2:
        return f"{size_bytes / 1_024:.1f} KB"
    return f"{size_bytes / 1_024 ** 2:.1f} MB"


@app.template_filter("status_class")
def status_class(status: str) -> str:
    return {
        "pending":    "status-pending",
        "processing": "status-processing",
        "completed":  "status-completed",
        "failed":     "status-failed",
    }.get(status or "", "status-neutral")


# ---------------------------------------------------------------------------
# Error handlers  (templates created in Batch 5)
# ---------------------------------------------------------------------------

@app.errorhandler(403)
def forbidden(e):
    return render_template("error.html", code=403, message="Access Denied"), 403


@app.errorhandler(404)
def not_found(e):
    return render_template("error.html", code=404, message="Page Not Found"), 404


@app.errorhandler(500)
def server_error(e):
    return render_template("error.html", code=500, message="Internal Server Error"), 500


# ---------------------------------------------------------------------------
# PDF processing engine
# ---------------------------------------------------------------------------

_COUNTY_NAMES = [name for _, name, _ in KENYA_COUNTIES]

_COUNTY_ALIASES = {
    "nairobi":       "Nairobi City",
    "nrb":           "Nairobi City",
    "mombasa":       "Mombasa",
    "msa":           "Mombasa",
    "kisumu":        "Kisumu",
    "nakuru":        "Nakuru",
    "eldoret":       "Uasin Gishu",
    "uasin gishu":   "Uasin Gishu",
    "kakamega":      "Kakamega",
    "kiambu":        "Kiambu",
    "machakos":      "Machakos",
    "meru":          "Meru",
    "kilifi":        "Kilifi",
    "bungoma":       "Bungoma",
    "homa bay":      "Homa Bay",
    "homabay":       "Homa Bay",
    "trans nzoia":   "Trans Nzoia",
    "transnzoia":    "Trans Nzoia",
    "tharaka nithi": "Tharaka Nithi",
    "tharaka-nithi": "Tharaka Nithi",
    "elgeyo marakwet": "Elgeyo Marakwet",
    "murang'a":      "Murang'a",
    "muranga":       "Murang'a",
}


def allowed_file(filename: str) -> bool:
    return (
        "." in filename
        and filename.rsplit(".", 1)[1].lower() in app.config["ALLOWED_EXTENSIONS"]
    )


def extract_pdf_metadata(filepath: str):
    """Return (page_count, detected_title, full_text) from a PDF file."""
    if not PDF_AVAILABLE or not filepath or not os.path.exists(filepath):
        return None, None, None
    try:
        with pdfplumber.open(filepath) as pdf:
            page_count = len(pdf.pages)
            # First 3 pages for title detection
            head_text = ""
            for page in pdf.pages[:3]:
                head_text += (page.extract_text() or "")
            title = _detect_title(head_text)
            # Full text capped at 120 pages for performance
            full_text = ""
            for page in pdf.pages[:120]:
                full_text += (page.extract_text() or "") + "\n"
            return page_count, title, full_text
    except Exception as exc:
        app.logger.error("PDF extraction failed for %s: %s", filepath, exc)
        return None, None, None


def _detect_title(text: str) -> str | None:
    if not text:
        return None
    keywords = ("report", "budget", "audit", "review", "annual", "county",
                 "fiscal", "implementation", "expenditure", "revenue")
    lines = [ln.strip() for ln in text.splitlines() if len(ln.strip()) > 15]
    for line in lines[:15]:
        if any(kw in line.lower() for kw in keywords):
            return line[:300]
    return lines[0][:300] if lines else None


def detect_county_from_text(text: str) -> str | None:
    if not text:
        return None
    tl = text.lower()
    # Aliases first (longer phrases before substrings)
    for alias in sorted(_COUNTY_ALIASES, key=len, reverse=True):
        if alias in tl:
            return _COUNTY_ALIASES[alias]
    for name in _COUNTY_NAMES:
        if name.lower() in tl:
            return name
    return None


def detect_fiscal_year(text: str) -> str | None:
    if not text:
        return None
    patterns = [
        r"financial\s+year\s+(20\d\d/\d\d)",
        r"fiscal\s+year\s+(20\d\d/\d\d)",
        r"(20\d\d/\d\d)\s+financial\s+year",
        r"year\s+ended\s+30\s+june\s+(20\d\d)",
        r"year\s+ended\s+june\s+30[,\s]+(20\d\d)",
        r"(20\d\d)[–\-](20\d\d)\s+financial",
    ]
    for pat in patterns:
        m = re.search(pat, text, re.IGNORECASE)
        if m:
            raw = m.group(1)
            if "/" not in raw:          # e.g. "2023" → "2023/24"
                raw = f"{raw}/{str(int(raw) + 1)[2:]}"
            return raw
    return None


def detect_source_from_text(text: str) -> str | None:
    if not text:
        return None
    tl = text.lower()
    if "controller of budget" in tl or "budget implementation" in tl:
        return "CoB"
    if "auditor-general" in tl or "auditor general" in tl or "office of the auditor" in tl:
        return "OAG"
    if "commission on revenue allocation" in tl:
        return "CRA"
    return "Other"


def _parse_amount(raw: str) -> float | None:
    """Parse a raw numeric string (with commas) into a KES-millions float."""
    if not raw:
        return None
    cleaned = re.sub(r"[,\s]", "", raw)
    try:
        value = float(cleaned)
        # CoB figures are typically already in millions; very large values are in KES units
        if value > 1_000_000_000:
            value /= 1_000_000
        elif value > 1_000_000:
            value /= 1_000
        return value if value > 0 else None
    except ValueError:
        return None


# --- Metric regex patterns ---------------------------------------------------

METRIC_PATTERNS: dict[str, list[str]] = {
    "total_revenue": [
        r"total\s+revenue[s]?\s*[:\-]?\s*([\d,]+(?:\.\d+)?)",
        r"total\s+receipts\s*[:\-]?\s*([\d,]+(?:\.\d+)?)",
        r"revenue\s+receipts\s*[:\-]?\s*([\d,]+(?:\.\d+)?)",
    ],
    "own_source_revenue": [
        r"own[-\s]source\s+revenue[s]?\s*[:\-]?\s*([\d,]+(?:\.\d+)?)",
        r"local(?:ly generated)?\s+revenue[s]?\s*[:\-]?\s*([\d,]+(?:\.\d+)?)",
        r"internally\s+generated\s+revenue[s]?\s*[:\-]?\s*([\d,]+(?:\.\d+)?)",
    ],
    "equitable_share": [
        r"equitable\s+share\s*[:\-]?\s*([\d,]+(?:\.\d+)?)",
        r"shareable\s+revenue\s*[:\-]?\s*([\d,]+(?:\.\d+)?)",
        r"national\s+government\s+transfer[s]?\s*[:\-]?\s*([\d,]+(?:\.\d+)?)",
    ],
    "total_expenditure": [
        r"total\s+expenditure[s]?\s*[:\-]?\s*([\d,]+(?:\.\d+)?)",
        r"total\s+spending\s*[:\-]?\s*([\d,]+(?:\.\d+)?)",
    ],
    "recurrent_expenditure": [
        r"recurrent\s+expenditure[s]?\s*[:\-]?\s*([\d,]+(?:\.\d+)?)",
        r"operation(?:al)?\s+expenditure[s]?\s*[:\-]?\s*([\d,]+(?:\.\d+)?)",
    ],
    "development_expenditure": [
        r"development\s+expenditure[s]?\s*[:\-]?\s*([\d,]+(?:\.\d+)?)",
        r"capital\s+expenditure[s]?\s*[:\-]?\s*([\d,]+(?:\.\d+)?)",
        r"capital\s+outlay\s*[:\-]?\s*([\d,]+(?:\.\d+)?)",
    ],
    "pending_bills": [
        r"pending\s+bills?\s*[:\-]?\s*([\d,]+(?:\.\d+)?)",
        r"outstanding\s+bills?\s*[:\-]?\s*([\d,]+(?:\.\d+)?)",
        r"accounts\s+payable\s*[:\-]?\s*([\d,]+(?:\.\d+)?)",
    ],
    "staff_costs": [
        r"staff\s+costs?\s*[:\-]?\s*([\d,]+(?:\.\d+)?)",
        r"personnel\s+(?:emoluments?|costs?)\s*[:\-]?\s*([\d,]+(?:\.\d+)?)",
        r"wages?\s+and\s+salaries\s*[:\-]?\s*([\d,]+(?:\.\d+)?)",
    ],
}

AUDIT_PATTERNS: dict[str, list[str]] = {
    "unqualified": [
        r"unqualified\s+opinion",
        r"clean\s+audit",
        r"true\s+and\s+fair\s+view",
        r"fairly\s+presents?\s+in\s+all\s+material\s+respects?",
    ],
    "disclaimer": [
        r"disclaimer\s+of\s+opinion",
        r"unable\s+to\s+express\s+an?\s+opinion",
        r"do\s+not\s+express\s+an?\s+opinion",
    ],
    "adverse": [
        r"adverse\s+opinion",
        r"do\s+not\s+present\s+fairly",
        r"materially\s+misstated",
    ],
    "qualified": [
        r"qualified\s+opinion",
        r"except\s+for\s+the\s+matters?\s+described",
        r"subject\s+to\s+the\s+following",
    ],
}

_RISK_KEYWORDS = (
    "misstatement", "irregularity", "non-compliance", "unauthorized",
    "unsupported", "lack of", "failure to", "not supported", "pending bills",
    "irregular", "fraudulent", "wasteful", "unvouched", "unexplained",
)


def extract_metric(text: str, patterns: list[str]) -> tuple:
    """Return (value_float, source_snippet) for the first matching pattern."""
    for pat in patterns:
        m = re.search(pat, text, re.IGNORECASE | re.MULTILINE)
        if m:
            value = _parse_amount(m.group(1))
            if value:
                return value, m.group(0)[:120]
    return None, None


def extract_audit_opinion(text: str) -> tuple:
    """Return (opinion_type_str, [observation_strings])."""
    if not text:
        return None, []
    tl = text.lower()
    opinion = None
    # Check in severity order so worst wins if multiple match
    for otype in ("disclaimer", "adverse", "qualified", "unqualified"):
        for pat in AUDIT_PATTERNS[otype]:
            if re.search(pat, tl):
                opinion = otype
                break
        if opinion:
            break
    observations = []
    for sentence in re.split(r"[.!?]", text):
        s = sentence.strip()
        if len(s) > 40 and any(kw in s.lower() for kw in _RISK_KEYWORDS):
            observations.append(s[:300])
            if len(observations) >= 5:
                break
    return opinion, observations


# ---------------------------------------------------------------------------
# Background document processing task
# ---------------------------------------------------------------------------

def process_document_task(doc_id: int) -> None:
    """Run after upload in a daemon thread: extract text, metrics, audit opinion."""
    with app.app_context():
        doc = Document.query.get(doc_id)
        if not doc:
            return
        try:
            doc.processing_status = "processing"
            db.session.commit()

            page_count, title, text = extract_pdf_metadata(doc.filepath)
            doc.page_count = page_count
            doc.detected_title = title
            doc.text_content = text

            if text:
                # Auto-fill county if not set
                if not doc.county_id:
                    name = detect_county_from_text(text)
                    if name:
                        county = County.query.filter_by(name=name).first()
                        if county:
                            doc.county_id = county.id
                            if not doc.county_name or doc.county_name == "All Counties":
                                doc.county_name = name

                # Auto-fill fiscal year if blank
                if not doc.fiscal_year:
                    doc.fiscal_year = detect_fiscal_year(text)

                # Auto-fill source if still Other
                if not doc.source or doc.source == "Other":
                    detected = detect_source_from_text(text)
                    if detected:
                        doc.source = detected

                db.session.flush()

                # Extract fiscal metrics
                if doc.county_id and doc.fiscal_year:
                    for metric_name, patterns in METRIC_PATTERNS.items():
                        value, snippet = extract_metric(text, patterns)
                        if value:
                            existing = FiscalMetric.query.filter_by(
                                document_id=doc.id, metric_name=metric_name
                            ).first()
                            if existing:
                                existing.metric_value = value
                                existing.source_text = snippet
                            else:
                                db.session.add(FiscalMetric(
                                    document_id=doc.id,
                                    county_id=doc.county_id,
                                    fiscal_year=doc.fiscal_year,
                                    metric_name=metric_name,
                                    metric_value=value,
                                    source_text=snippet,
                                    confidence_score=0.75,
                                ))

                    # Extract audit opinion for OAG documents
                    if doc.source == "OAG":
                        opinion_type, observations = extract_audit_opinion(text)
                        if opinion_type and not AuditOpinion.query.filter_by(document_id=doc.id).first():
                            db.session.add(AuditOpinion(
                                document_id=doc.id,
                                county_id=doc.county_id,
                                fiscal_year=doc.fiscal_year,
                                opinion_type=opinion_type,
                                material_issues=len(observations),
                                key_observations=json.dumps(observations),
                            ))

            doc.processing_status = "completed"
            doc.processing_completed_at = datetime.utcnow()
            db.session.commit()

        except Exception as exc:
            app.logger.error("Processing failed for doc %s: %s", doc_id, exc)
            try:
                doc.processing_status = "failed"
                doc.processing_error = str(exc)
                db.session.commit()
            except Exception:
                db.session.rollback()


# ---------------------------------------------------------------------------
# Routes — auth
# ---------------------------------------------------------------------------

@app.route("/login", methods=["GET", "POST"])
def login():
    if current_user.is_authenticated:
        return redirect(url_for("dashboard"))
    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "")
        remember = bool(request.form.get("remember"))
        user = User.query.filter_by(username=username).first()
        if user and user.is_active and user.check_password(password):
            login_user(user, remember=remember)
            user.last_login = datetime.utcnow()
            db.session.commit()
            return redirect(request.args.get("next") or url_for("dashboard"))
        flash("Invalid username or password.", "error")
    return render_template("login.html")


@app.route("/logout")
@login_required
def logout():
    logout_user()
    return redirect(url_for("login"))


# ---------------------------------------------------------------------------
# Routes — dashboard
# ---------------------------------------------------------------------------

@app.route("/")
@login_required
def index():
    return redirect(url_for("dashboard"))


@app.route("/dashboard")
@login_required
def dashboard():
    total_docs      = Document.query.count()
    counties_covered = (db.session.query(Document.county_id)
                        .filter(Document.county_id.isnot(None))
                        .distinct().count())
    years_tracked   = (db.session.query(Document.fiscal_year)
                        .filter(Document.fiscal_year.isnot(None))
                        .distinct().count())
    completed_docs  = Document.query.filter_by(processing_status="completed").count()

    latest_docs = (Document.query
                   .order_by(Document.upload_date.desc())
                   .limit(8).all())

    counties_ranked = (db.session.query(County,
                           db.func.count(Document.id).label("doc_count"))
                       .outerjoin(Document)
                       .group_by(County.id)
                       .order_by(db.desc("doc_count"))
                       .all())

    opinion_rows = (db.session.query(AuditOpinion.opinion_type,
                        db.func.count(AuditOpinion.id))
                    .group_by(AuditOpinion.opinion_type).all())
    opinion_counts = dict(opinion_rows)

    fiscal_years = sorted(
        {r[0] for r in db.session.query(Document.fiscal_year).all() if r[0]},
        reverse=True,
    )

    return render_template("dashboard.html",
        total_docs=total_docs,
        counties_covered=counties_covered,
        years_tracked=years_tracked,
        completed_docs=completed_docs,
        latest_docs=latest_docs,
        counties_ranked=counties_ranked,
        opinion_counts=opinion_counts,
        fiscal_years=fiscal_years,
    )


# ---------------------------------------------------------------------------
# Routes — counties list
# ---------------------------------------------------------------------------

@app.route("/counties")
@login_required
def counties():
    region_filter = request.args.get("region", "")
    regions = sorted({r for _, _, r in KENYA_COUNTIES})

    query = County.query
    if region_filter:
        query = query.filter_by(region=region_filter)
    all_counties = query.order_by(County.code).all()

    # Attach latest metric snapshot and audit opinion per county
    county_data = []
    for c in all_counties:
        latest_metric = (FiscalMetric.query
                         .filter_by(county_id=c.id, metric_name="total_revenue")
                         .order_by(FiscalMetric.fiscal_year.desc())
                         .first())
        latest_audit = (AuditOpinion.query
                        .filter_by(county_id=c.id)
                        .order_by(AuditOpinion.fiscal_year.desc())
                        .first())
        doc_count = Document.query.filter_by(county_id=c.id).count()
        county_data.append({
            "county":       c,
            "doc_count":    doc_count,
            "latest_rev":   latest_metric.metric_value if latest_metric else None,
            "latest_year":  latest_metric.fiscal_year  if latest_metric else None,
            "audit":        latest_audit.opinion_type  if latest_audit  else None,
            "audit_year":   latest_audit.fiscal_year   if latest_audit  else None,
        })

    return render_template("counties.html",
        county_data=county_data,
        regions=regions,
        active_region=region_filter,
    )


# ---------------------------------------------------------------------------
# Routes — county detail
# ---------------------------------------------------------------------------

@app.route("/county/<int:county_id>")
@login_required
def county_detail(county_id):
    county = County.query.get_or_404(county_id)

    documents = (Document.query
                 .filter_by(county_id=county_id)
                 .order_by(Document.fiscal_year.desc(), Document.upload_date.desc())
                 .all())

    metrics = (FiscalMetric.query
               .filter_by(county_id=county_id)
               .order_by(FiscalMetric.fiscal_year)
               .all())

    audit_opinions = (AuditOpinion.query
                      .filter_by(county_id=county_id)
                      .order_by(AuditOpinion.fiscal_year.desc())
                      .all())

    # Build year-keyed metric dict for templates and chart data
    metrics_by_year: dict = {}
    for m in metrics:
        metrics_by_year.setdefault(m.fiscal_year, {})[m.metric_name] = m.metric_value

    sorted_years = sorted(metrics_by_year)

    def _series(key):
        return [metrics_by_year.get(y, {}).get(key) for y in sorted_years]

    chart_data = {
        "years":                sorted_years,
        "total_revenue":        _series("total_revenue"),
        "total_expenditure":    _series("total_expenditure"),
        "own_source_revenue":   _series("own_source_revenue"),
        "development_expenditure": _series("development_expenditure"),
        "recurrent_expenditure":   _series("recurrent_expenditure"),
    }

    # Latest-year snapshot for KPI cards
    latest_year = sorted_years[-1] if sorted_years else None
    latest = metrics_by_year.get(latest_year, {})

    latest_audit = audit_opinions[0] if audit_opinions else None

    return render_template("county.html",
        county=county,
        documents=documents,
        metrics=metrics,
        audit_opinions=audit_opinions,
        metrics_by_year=metrics_by_year,
        chart_data=json.dumps(chart_data),
        latest=latest,
        latest_year=latest_year,
        latest_audit=latest_audit,
    )


# ---------------------------------------------------------------------------
# Routes — document library
# ---------------------------------------------------------------------------

@app.route("/library")
@login_required
def library():
    # Filter params
    county_id   = request.args.get("county_id",   "", type=str)
    source      = request.args.get("source",       "")
    fiscal_year = request.args.get("fiscal_year",  "")
    status      = request.args.get("status",       "")
    search      = request.args.get("search",       "").strip()
    page        = request.args.get("page", 1, type=int)

    query = Document.query
    if county_id:
        query = query.filter_by(county_id=int(county_id))
    if source:
        query = query.filter_by(source=source)
    if fiscal_year:
        query = query.filter_by(fiscal_year=fiscal_year)
    if status:
        query = query.filter_by(processing_status=status)
    if search:
        query = query.filter(db.or_(
            Document.original_filename.ilike(f"%{search}%"),
            Document.county_name.ilike(f"%{search}%"),
            Document.document_type.ilike(f"%{search}%"),
        ))

    pagination = query.order_by(Document.upload_date.desc()).paginate(
        page=page, per_page=25, error_out=False
    )

    all_counties  = County.query.order_by(County.name).all()
    fiscal_years  = sorted(
        {r[0] for r in db.session.query(Document.fiscal_year).all() if r[0]},
        reverse=True,
    )

    return render_template("library.html",
        pagination=pagination,
        documents=pagination.items,
        all_counties=all_counties,
        fiscal_years=fiscal_years,
        sources=SOURCES,
        filters=dict(county_id=county_id, source=source,
                     fiscal_year=fiscal_year, status=status, search=search),
    )


# ---------------------------------------------------------------------------
# Routes — county comparison
# ---------------------------------------------------------------------------

@app.route("/compare")
@login_required
def compare():
    all_counties = County.query.order_by(County.name).all()
    fiscal_years = sorted(
        {r[0] for r in db.session.query(Document.fiscal_year).all() if r[0]},
        reverse=True,
    )
    return render_template("compare.html",
        all_counties=all_counties,
        fiscal_years=fiscal_years,
    )


# ---------------------------------------------------------------------------
# Routes — document detail & download
# ---------------------------------------------------------------------------

@app.route("/document/<int:doc_id>")
@login_required
def document_detail(doc_id):
    doc           = Document.query.get_or_404(doc_id)
    metrics       = FiscalMetric.query.filter_by(document_id=doc_id).all()
    audit_opinions = AuditOpinion.query.filter_by(document_id=doc_id).all()
    return render_template("document.html",
        doc=doc,
        metrics=metrics,
        audit_opinions=audit_opinions,
    )


@app.route("/document/<int:doc_id>/download")
@login_required
def document_download(doc_id):
    doc = Document.query.get_or_404(doc_id)
    if not doc.filepath or not os.path.exists(doc.filepath):
        flash("File not found on disk.", "error")
        return redirect(url_for("document_detail", doc_id=doc_id))
    return send_file(
        doc.filepath,
        as_attachment=True,
        download_name=doc.original_filename,
        mimetype="application/pdf",
    )


# ---------------------------------------------------------------------------
# Routes — admin upload portal
# ---------------------------------------------------------------------------

@app.route("/admin/upload", methods=["GET", "POST"])
@login_required
@admin_required
def admin_upload():
    if request.method == "POST":
        files       = request.files.getlist("files")
        source      = request.form.get("source",       "Other")
        fiscal_year = request.form.get("fiscal_year",  "")
        county_name = request.form.get("county_name",  "All Counties")
        period      = request.form.get("report_period","annual")
        doc_type    = request.form.get("document_type","")
        notes       = request.form.get("notes",        "")

        county_id = None
        if county_name and county_name != "All Counties":
            c = County.query.filter_by(name=county_name).first()
            if c:
                county_id = c.id

        saved = 0
        for f in files:
            if not f or not f.filename or not allowed_file(f.filename):
                continue
            orig      = secure_filename(f.filename)
            stored    = f"{uuid.uuid4().hex}_{orig}"
            filepath  = os.path.join(app.config["UPLOAD_FOLDER"], stored)
            f.save(filepath)

            doc = Document(
                original_filename=orig,
                stored_filename=stored,
                filepath=filepath,
                file_size=os.path.getsize(filepath),
                source=source,
                fiscal_year=fiscal_year or None,
                county_id=county_id,
                county_name=county_name,
                report_period=period,
                document_type=doc_type,
                notes=notes,
                uploaded_by_id=current_user.id,
                processing_status="pending",
            )
            db.session.add(doc)
            db.session.flush()         # populate doc.id before thread starts

            t = threading.Thread(target=process_document_task, args=(doc.id,), daemon=True)
            t.start()
            saved += 1

        db.session.commit()
        if saved:
            flash(f"{saved} file(s) uploaded. Processing in background.", "success")
        else:
            flash("No valid PDF files found.", "error")
        return redirect(url_for("admin_upload"))

    recent = Document.query.order_by(Document.upload_date.desc()).limit(12).all()
    return render_template("upload.html",
        all_counties=County.query.order_by(County.name).all(),
        fiscal_years=FISCAL_YEARS,
        sources=SOURCES,
        report_periods=REPORT_PERIODS,
        document_types=DOCUMENT_TYPES,
        recent=recent,
    )


@app.route("/admin/delete/<int:doc_id>", methods=["POST"])
@login_required
@admin_required
def admin_delete(doc_id):
    doc = Document.query.get_or_404(doc_id)
    if doc.filepath and os.path.exists(doc.filepath):
        os.remove(doc.filepath)
    FiscalMetric.query.filter_by(document_id=doc_id).delete()
    AuditOpinion.query.filter_by(document_id=doc_id).delete()
    db.session.delete(doc)
    db.session.commit()
    flash("Document deleted.", "success")
    return redirect(url_for("library"))


@app.route("/admin/reprocess/<int:doc_id>", methods=["POST"])
@login_required
@admin_required
def admin_reprocess(doc_id):
    doc = Document.query.get_or_404(doc_id)
    FiscalMetric.query.filter_by(document_id=doc_id).delete()
    AuditOpinion.query.filter_by(document_id=doc_id).delete()
    doc.processing_status = "pending"
    doc.text_content = None
    db.session.commit()
    t = threading.Thread(target=process_document_task, args=(doc_id,), daemon=True)
    t.start()
    return jsonify({"status": "ok", "message": "Reprocessing started"})


# ---------------------------------------------------------------------------
# API — dashboard stats
# ---------------------------------------------------------------------------

@app.route("/api/dashboard/stats")
@login_required
def api_dashboard_stats():
    total_docs = Document.query.count()
    counties_covered = (db.session.query(Document.county_id)
                        .filter(Document.county_id.isnot(None))
                        .distinct().count())

    status_counts = dict(
        db.session.query(Document.processing_status,
                         db.func.count(Document.id))
        .group_by(Document.processing_status).all()
    )
    source_counts = dict(
        db.session.query(Document.source, db.func.count(Document.id))
        .filter(Document.source.isnot(None))
        .group_by(Document.source).all()
    )
    year_counts = dict(
        db.session.query(Document.fiscal_year, db.func.count(Document.id))
        .filter(Document.fiscal_year.isnot(None))
        .group_by(Document.fiscal_year).all()
    )
    opinion_counts = dict(
        db.session.query(AuditOpinion.opinion_type, db.func.count(AuditOpinion.id))
        .group_by(AuditOpinion.opinion_type).all()
    )

    return jsonify({
        "total_docs":       total_docs,
        "counties_covered": counties_covered,
        "status":           status_counts,
        "sources":          source_counts,
        "years":            year_counts,
        "opinions":         opinion_counts,
    })


# ---------------------------------------------------------------------------
# API — counties list (with optional fiscal year filter)
# ---------------------------------------------------------------------------

@app.route("/api/counties")
@login_required
def api_counties():
    fiscal_year = request.args.get("fiscal_year", "")
    counties = County.query.order_by(County.code).all()
    result = []

    for c in counties:
        mq = FiscalMetric.query.filter_by(county_id=c.id)
        if fiscal_year:
            mq = mq.filter_by(fiscal_year=fiscal_year)
        metrics = {m.metric_name: m.metric_value for m in mq.all()}

        latest_audit = (AuditOpinion.query
                        .filter_by(county_id=c.id)
                        .order_by(AuditOpinion.fiscal_year.desc())
                        .first())

        result.append({
            "id":          c.id,
            "code":        c.code,
            "name":        c.name,
            "region":      c.region,
            "doc_count":   Document.query.filter_by(county_id=c.id).count(),
            "metrics":     metrics,
            "audit":       latest_audit.opinion_type if latest_audit else None,
            "audit_year":  latest_audit.fiscal_year  if latest_audit else None,
        })

    return jsonify(result)


# ---------------------------------------------------------------------------
# API — single county metrics (all years)
# ---------------------------------------------------------------------------

@app.route("/api/county/<int:county_id>/metrics")
@login_required
def api_county_metrics(county_id):
    metrics = (FiscalMetric.query
               .filter_by(county_id=county_id)
               .order_by(FiscalMetric.fiscal_year)
               .all())

    result: dict = {}
    for m in metrics:
        result.setdefault(m.fiscal_year, {})[m.metric_name] = {
            "value":      m.metric_value,
            "confidence": m.confidence_score,
            "unit":       m.unit,
        }
    return jsonify(result)


# ---------------------------------------------------------------------------
# API — county AI analysis (rule-based; Claude upgrade in Batch 3)
# ---------------------------------------------------------------------------

@app.route("/api/county/<int:county_id>/analysis")
@login_required
def api_county_analysis(county_id):
    county = County.query.get_or_404(county_id)
    metrics = FiscalMetric.query.filter_by(county_id=county_id).all()
    opinions = AuditOpinion.query.filter_by(county_id=county_id).all()

    score = 60
    risks, audit_flags, rev_signals = [], [], []

    for op in opinions[-3:]:
        if op.opinion_type == "unqualified":
            score += 8
        elif op.opinion_type == "qualified":
            score -= 5
            audit_flags.append(f"Qualified opinion in {op.fiscal_year}")
        elif op.opinion_type == "adverse":
            score -= 18
            audit_flags.append(f"Adverse opinion in {op.fiscal_year} — serious concerns")
        elif op.opinion_type == "disclaimer":
            score -= 28
            audit_flags.append(f"Disclaimer of opinion in {op.fiscal_year} — critical issues")

    by_year: dict = {}
    for m in metrics:
        by_year.setdefault(m.fiscal_year, {})[m.metric_name] = m.metric_value

    for yr, ym in by_year.items():
        rev   = ym.get("total_revenue",          0) or 0
        osr   = ym.get("own_source_revenue",      0) or 0
        exp   = ym.get("total_expenditure",       0) or 0
        dev   = ym.get("development_expenditure", 0) or 0
        bills = ym.get("pending_bills",           0) or 0

        if rev > 0:
            osr_ratio = osr / rev
            if osr_ratio < 0.05:
                score -= 5
                rev_signals.append(f"Very low own-source revenue ({osr_ratio*100:.1f}%) in {yr}")
            elif osr_ratio > 0.15:
                score += 4
                rev_signals.append(f"Strong own-source revenue ({osr_ratio*100:.1f}%) in {yr}")

            if bills / rev > 0.10:
                score -= 8
                risks.append(f"Pending bills at {bills/rev*100:.0f}% of revenue in {yr}")

        if exp > 0 and dev / exp < 0.20:
            score -= 4
            risks.append(f"Development spending below 20% in {yr}")

    score = max(0, min(100, score))
    label = ("Strong" if score >= 70 else
             "Moderate" if score >= 50 else
             "Weak" if score >= 30 else "Critical")
    trend = "Improving" if score >= 65 else "Stable" if score >= 45 else "Deteriorating"

    return jsonify({
        "fiscal_health_score": score,
        "health_label":        label,
        "trend_assessment":    trend,
        "top_risks":           risks[:4]       or ["Insufficient data for risk assessment"],
        "revenue_signals":     rev_signals[:3] or ["Upload more CoB reports for revenue analysis"],
        "audit_flags":         audit_flags[:3] or ["No OAG reports uploaded yet"],
        "summary": (f"{county.name} County scores {score}/100 — {label} fiscal performance "
                    f"based on {len(metrics)} extracted metrics across {len(by_year)} fiscal year(s)."),
        "recommendations": [
            "Upload all available CoB CBIRRs to improve data completeness",
            "Monitor pending bills as a share of annual revenue",
            "Compare development expenditure ratios against the 30% constitutional benchmark",
        ],
    })


# ---------------------------------------------------------------------------
# API — county comparison
# ---------------------------------------------------------------------------

@app.route("/api/compare")
@login_required
def api_compare():
    ids_raw     = request.args.get("counties", "")
    fiscal_year = request.args.get("fiscal_year", "")
    result      = []

    for raw in ids_raw.split(","):
        try:
            cid = int(raw.strip())
        except ValueError:
            continue
        county = County.query.get(cid)
        if not county:
            continue

        mq = FiscalMetric.query.filter_by(county_id=cid)
        if fiscal_year:
            mq = mq.filter_by(fiscal_year=fiscal_year)
        metrics = {m.metric_name: m.metric_value for m in mq.all()}

        latest_audit = (AuditOpinion.query
                        .filter_by(county_id=cid)
                        .order_by(AuditOpinion.fiscal_year.desc())
                        .first())

        result.append({
            "county_id":   cid,
            "county_name": county.name,
            "region":      county.region,
            "metrics":     metrics,
            "audit":       latest_audit.opinion_type if latest_audit else None,
        })

    return jsonify(result)


# ---------------------------------------------------------------------------
# API — paginated document list
# ---------------------------------------------------------------------------

@app.route("/api/documents")
@login_required
def api_documents():
    county_id   = request.args.get("county_id",  type=int)
    source      = request.args.get("source",      "")
    fiscal_year = request.args.get("fiscal_year", "")
    status      = request.args.get("status",      "")
    search      = request.args.get("search",      "").strip()
    page        = request.args.get("page",    1,  type=int)
    per_page    = request.args.get("per_page", 20, type=int)

    q = Document.query
    if county_id:  q = q.filter_by(county_id=county_id)
    if source:     q = q.filter_by(source=source)
    if fiscal_year: q = q.filter_by(fiscal_year=fiscal_year)
    if status:     q = q.filter_by(processing_status=status)
    if search:
        q = q.filter(db.or_(
            Document.original_filename.ilike(f"%{search}%"),
            Document.county_name.ilike(f"%{search}%"),
            Document.document_type.ilike(f"%{search}%"),
        ))

    pag = q.order_by(Document.upload_date.desc()).paginate(
        page=page, per_page=per_page, error_out=False
    )
    return jsonify({
        "documents":    [d.to_dict() for d in pag.items],
        "total":        pag.total,
        "pages":        pag.pages,
        "current_page": page,
    })


# ---------------------------------------------------------------------------
# API — CSV export (analyst + admin only)
# ---------------------------------------------------------------------------

@app.route("/api/export/csv")
@login_required
def api_export_csv():
    if not current_user.can_export():
        abort(403)

    county_id   = request.args.get("county_id",  type=int)
    fiscal_year = request.args.get("fiscal_year", "")

    q = FiscalMetric.query.join(County)
    if county_id:    q = q.filter(FiscalMetric.county_id == county_id)
    if fiscal_year:  q = q.filter(FiscalMetric.fiscal_year == fiscal_year)

    buf = io.StringIO()
    w   = csv.writer(buf)
    w.writerow(["County", "Fiscal Year", "Metric", "Value (KES Millions)", "Confidence"])
    for m in q.order_by(County.name, FiscalMetric.fiscal_year).all():
        w.writerow([
            m.county.name if m.county else "",
            m.fiscal_year,
            m.metric_name,
            round(m.metric_value, 2) if m.metric_value else "",
            round(m.confidence_score, 2) if m.confidence_score else "",
        ])

    buf.seek(0)
    filename = f"kenya_fiscal_{datetime.now().strftime('%Y%m%d')}.csv"
    return send_file(
        io.BytesIO(buf.getvalue().encode()),
        mimetype="text/csv",
        as_attachment=True,
        download_name=filename,
    )


# ---------------------------------------------------------------------------
# API — document processing status (poll from upload page)
# ---------------------------------------------------------------------------

@app.route("/api/document/<int:doc_id>/status")
@login_required
def api_doc_status(doc_id):
    doc = Document.query.get_or_404(doc_id)
    return jsonify({
        "id":     doc.id,
        "status": doc.processing_status,
        "error":  doc.processing_error,
        "pages":  doc.page_count,
        "title":  doc.detected_title,
    })


# ---------------------------------------------------------------------------
# API — AI Chatbot  (/api/chat)
# ---------------------------------------------------------------------------

def _build_county_context(county_id) -> str:
    if not county_id:
        return ""
    county = County.query.get(county_id)
    if not county:
        return ""
    metrics  = (FiscalMetric.query.filter_by(county_id=county_id)
                .order_by(FiscalMetric.fiscal_year.desc()).all())
    opinions = (AuditOpinion.query.filter_by(county_id=county_id)
                .order_by(AuditOpinion.fiscal_year.desc()).all())
    doc_count = Document.query.filter_by(county_id=county_id).count()

    by_year: dict = {}
    for m in metrics:
        by_year.setdefault(m.fiscal_year, {})[m.metric_name] = m.metric_value

    lines = [
        f"ACTIVE COUNTY: {county.name} (Code {county.code:02d}, {county.region} Region)",
        f"Population: {county.population:,}" if county.population else "",
        f"Documents uploaded: {doc_count}", "",
    ]
    for yr in sorted(by_year, reverse=True)[:4]:
        ym = by_year[yr]
        lines.append(f"Fiscal Year {yr}:")
        for k, label in [
            ("total_revenue",           "  Total Revenue"),
            ("own_source_revenue",      "  Own-Source Revenue"),
            ("equitable_share",         "  Equitable Share"),
            ("total_expenditure",       "  Total Expenditure"),
            ("recurrent_expenditure",   "  Recurrent Expenditure"),
            ("development_expenditure", "  Development Expenditure"),
            ("pending_bills",           "  Pending Bills"),
            ("staff_costs",             "  Staff Costs"),
        ]:
            if k in ym:
                v = ym[k]
                lines.append(f"{label}: {'KES ' + str(round(v/1000,1)) + 'B' if v >= 1000 else 'KES ' + str(round(v,0)) + 'M'}")
    if opinions:
        lines += ["", "Audit History:"]
        for op in opinions[:4]:
            obs = op.observations_list()
            lines.append(f"  {op.fiscal_year}: {op.opinion_type.upper()} "
                         f"({op.material_issues} issues)"
                         f"{' — ' + obs[0][:80] if obs else ''}")
    return "\n".join(l for l in lines if l is not None)


def _build_dashboard_context() -> str:
    total_docs = Document.query.count()
    completed  = Document.query.filter_by(processing_status="completed").count()
    covered    = (db.session.query(Document.county_id)
                  .filter(Document.county_id.isnot(None)).distinct().count())
    op_counts  = dict(
        db.session.query(AuditOpinion.opinion_type, db.func.count(AuditOpinion.id))
        .group_by(AuditOpinion.opinion_type).all())
    top5 = (db.session.query(County.name,
                db.func.max(FiscalMetric.metric_value).label("rev"))
            .join(FiscalMetric, FiscalMetric.county_id == County.id)
            .filter(FiscalMetric.metric_name == "total_revenue")
            .group_by(County.id).order_by(db.desc("rev")).limit(5).all())
    lines = [
        "PLATFORM OVERVIEW:",
        f"Total documents: {total_docs} ({completed} processed)",
        f"Counties with data: {covered}/47",
        f"Audit opinions — Clean: {op_counts.get('unqualified',0)}, "
        f"Qualified: {op_counts.get('qualified',0)}, "
        f"Adverse: {op_counts.get('adverse',0)}, "
        f"Disclaimer: {op_counts.get('disclaimer',0)}", "",
        "Top 5 counties by revenue:",
    ]
    for name, rev in top5:
        fmt = f"KES {rev/1000:.1f}B" if rev and rev >= 1000 else f"KES {rev:.0f}M" if rev else "—"
        lines.append(f"  {name}: {fmt}")
    return "\n".join(lines)


def _build_system_prompt(page: str, county_id, mode: str) -> str:
    county_ctx    = _build_county_context(county_id)
    dashboard_ctx = _build_dashboard_context()
    prompt = f"""You are FiscalOS AI — the built-in fiscal intelligence assistant for FinancialOS Kenya, \
a platform used by banks, DFIs, investors, and analysts to analyse Kenyan county government finances.

You have three roles:
ROLE 1 — APP GUIDE: Explain every feature of FinancialOS Kenya. Tell users exactly where to click.
ROLE 2 — FISCAL ANALYST: Analyse the real county data in the platform. Reference specific KES figures, \
audit opinions, and trends. Think like a credit analyst or DFI investment officer.
ROLE 3 — KENYA EXPERT: Explain Kenya fiscal context — equitable share, Controller of Budget, OAG, \
IFMIS, CRA, the 30% development expenditure constitutional requirement, pending bills, own-source revenue.

CURRENT PAGE: {page}
USER ROLE: {getattr(current_user, 'role', 'viewer')}

{dashboard_ctx}

{county_ctx}

CHART DIRECTIVES — embed one per response on its own line when a visual would help:
[[CHART:revenue_trend]]         — revenue vs expenditure trend for the active county
[[CHART:osr_trend]]             — own-source revenue ratio trend for the active county
[[CHART:expenditure_breakdown]] — stacked recurrent vs development bar
[[CHART:audit_history]]         — audit opinion history for the active county
[[CHART:county_comparison]]     — top 10 counties by total revenue
[[CHART:pending_bills]]         — pending bills as % of revenue across counties

Rules: only use when county data is loaded · place on its own line · max one per response · \
after the directive highlight 2-3 specific insights · use county_comparison or pending_bills \
for platform-wide questions."""

    if mode == "simple":
        prompt += "\n\nSIMPLE MODE: Plain English. No jargon. Short sentences. End with 'Bottom line: [one sentence]'."
    else:
        prompt += "\n\nEXPERT MODE: User is analyst/DFI level. Precise fiscal terminology. Concise and data-driven."
    prompt += "\n\nAlways reference specific numbers. Never say 'I don't have access to' — you have full context."
    return prompt


@app.route("/api/chat", methods=["POST"])
@login_required
def api_chat():
    if not AI_AVAILABLE:
        return jsonify({"error": "AI engine not installed. Run: pip install anthropic"}), 503
    if not app.config["ANTHROPIC_API_KEY"]:
        return jsonify({"error": "ANTHROPIC_API_KEY not configured. Set it as an environment variable."}), 503

    body      = request.get_json(force=True)
    messages  = body.get("messages", [])
    page      = body.get("page", "Dashboard")
    county_id = body.get("county_id")
    mode      = body.get("mode", "simple")

    if not messages:
        return jsonify({"error": "No messages provided."}), 400

    try:
        client   = anthropic.Anthropic(api_key=app.config["ANTHROPIC_API_KEY"])
        response = client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=1200,
            system=_build_system_prompt(page, county_id, mode),
            messages=[{"role": m["role"], "content": m["content"]} for m in messages[-20:]],
        )
        return jsonify({"reply": response.content[0].text})
    except Exception as exc:
        app.logger.error("Chat API error: %s", exc)
        return jsonify({"error": str(exc)}), 500


# ---------------------------------------------------------------------------
# Routes — Document Review (3-panel: doc list | PDF viewer | chat)
# ---------------------------------------------------------------------------

@app.route("/review")
@login_required
def review():
    counties  = County.query.order_by(County.name).all()
    documents = (Document.query
                 .filter_by(processing_status="completed")
                 .order_by(Document.upload_date.desc())
                 .all())
    return render_template("review.html", counties=counties, documents=documents)


@app.route("/api/document/<int:doc_id>/file")
@login_required
def api_doc_file(doc_id):
    """Serve the raw PDF bytes for PDF.js to render in the browser."""
    doc = Document.query.get_or_404(doc_id)
    if not doc.filepath or not os.path.exists(doc.filepath):
        abort(404)
    return send_file(
        doc.filepath,
        mimetype="application/pdf",
        as_attachment=False,
        download_name=doc.original_filename,
    )


@app.route("/api/review/documents")
@login_required
def api_review_documents():
    """Return document list with metadata for the review panel selector."""
    county_id = request.args.get("county_id", type=int)
    q         = request.args.get("q", "").strip().lower()

    docs = Document.query.filter_by(processing_status="completed")
    if county_id:
        docs = docs.filter_by(county_id=county_id)
    docs = docs.order_by(Document.upload_date.desc()).all()

    results = []
    for d in docs:
        title = d.detected_title or d.original_filename
        if q and q not in title.lower() and q not in (d.original_filename or "").lower():
            continue
        results.append({
            "id":            d.id,
            "title":         title,
            "filename":      d.original_filename,
            "county_id":     d.county_id,
            "county_name":   d.county.name if d.county else "Unknown",
            "fiscal_year":   d.fiscal_year,
            "source":        d.source_type,
            "pages":         d.page_count,
            "upload_date":   d.upload_date.strftime("%d %b %Y") if d.upload_date else "",
        })
    return jsonify(results)


# ---------------------------------------------------------------------------
# Routes — health check
# ---------------------------------------------------------------------------

@app.route("/health")
def health():
    return jsonify({"status": "ok", "pdf_engine": PDF_AVAILABLE, "ai_engine": AI_AVAILABLE})


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def _bootstrap_db() -> None:
    """Create all tables and seed a default admin account on first run."""
    db.create_all()

    # Seed all 47 counties if the table is empty
    if County.query.count() == 0:
        for code, name, region in KENYA_COUNTIES:
            db.session.add(County(code=code, name=name, region=region))
        db.session.commit()
        print(f"  ✓ Seeded {len(KENYA_COUNTIES)} counties")

    # Create default admin account if none exists
    if not User.query.filter_by(username="admin").first():
        admin = User(username="admin", email="admin@fiscalos.ke", role="admin")
        admin.set_password("admin123")
        db.session.add(admin)
        db.session.commit()
        print("  ✓ Default admin created  →  admin / admin123")


if __name__ == "__main__":
    with app.app_context():
        _bootstrap_db()

    print("\n FinancialOS Kenya — County Fiscal Intelligence Platform")
    print(" Running at http://localhost:5000\n")
    app.run(debug=True, port=5000, host="0.0.0.0")
