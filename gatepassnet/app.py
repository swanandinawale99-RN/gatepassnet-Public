"""
Campus Visitor Network Access Management
------------------------------------------
2nd Year IT Engineering - Data Communication Project

A Flask web application that lets campus visitors register for temporary
Wi-Fi access, lets an admin approve/reject requests, generates a unique
time-limited access code + QR code per visitor, and automatically expires
access after a set duration. All actions are written to an activity log.

Run:
    pip install -r requirements.txt
    python app.py
Then open http://127.0.0.1:5000 in your browser.

Default admin login: admin / admin123  (change ADMIN_USERNAME / ADMIN_PASSWORD below)
"""

import os
import secrets
import string
from datetime import datetime, timedelta
from functools import wraps

import qrcode
from flask import (
    Flask, render_template, request, redirect,
    url_for, session, flash, jsonify
)
from flask_sqlalchemy import SQLAlchemy

# --------------------------------------------------------------------------
# App & Database Configuration
# --------------------------------------------------------------------------
BASE_DIR = os.path.abspath(os.path.dirname(__file__))

app = Flask(__name__)
app.config["SECRET_KEY"] = "campus-visitor-network-secret-key-change-me"
app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///" + os.path.join(BASE_DIR, "instance", "visitors.db")
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False

# NOTE: This project uses SQLite by default so it runs with zero extra setup
# (perfect for a college demo/viva). To use MySQL instead (as listed in the
# project's tech stack), install `mysqlclient` or `PyMySQL` and change the
# line above to something like:
#   "mysql+pymysql://<user>:<password>@localhost/campus_visitor_db"
# The rest of the code (models, routes) does not need to change at all
# because Flask-SQLAlchemy abstracts the database engine.

db = SQLAlchemy(app)

# Hardcoded admin credentials for the demo. In a production system these
# would live in the database, hashed with e.g. werkzeug.security.
ADMIN_USERNAME = "admin"
ADMIN_PASSWORD = "admin123"

# How long a generated access code stays valid, in hours (admin can also
# override this per-visitor from the approval form).
DEFAULT_ACCESS_HOURS = 4


# --------------------------------------------------------------------------
# Database Models
# --------------------------------------------------------------------------
class Visitor(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    mobile = db.Column(db.String(15), nullable=False)
    purpose = db.Column(db.String(255), nullable=False)
    host_department = db.Column(db.String(100), nullable=True)

    status = db.Column(db.String(20), nullable=False, default="Pending")
    # Pending -> Approved -> (Active / Expired)   or  Pending -> Rejected

    access_code = db.Column(db.String(12), unique=True, nullable=True)
    qr_filename = db.Column(db.String(120), nullable=True)

    requested_at = db.Column(db.DateTime, default=datetime.utcnow)
    approved_at = db.Column(db.DateTime, nullable=True)
    expires_at = db.Column(db.DateTime, nullable=True)

    def current_status(self):
        """Lazily compute whether an approved code has expired."""
        if self.status == "Approved" and self.expires_at:
            if datetime.utcnow() >= self.expires_at:
                return "Expired"
            return "Active"
        return self.status

    def time_remaining(self):
        if self.expires_at and self.current_status() == "Active":
            delta = self.expires_at - datetime.utcnow()
            total_minutes = int(delta.total_seconds() // 60)
            hrs, mins = divmod(total_minutes, 60)
            return f"{hrs}h {mins}m"
        return "-"


class ActivityLog(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    visitor_id = db.Column(db.Integer, db.ForeignKey("visitor.id"), nullable=True)
    visitor_name = db.Column(db.String(100), nullable=True)
    action = db.Column(db.String(255), nullable=False)
    timestamp = db.Column(db.DateTime, default=datetime.utcnow)


def log_activity(action, visitor=None):
    entry = ActivityLog(
        visitor_id=visitor.id if visitor else None,
        visitor_name=visitor.name if visitor else None,
        action=action,
    )
    db.session.add(entry)
    db.session.commit()


# --------------------------------------------------------------------------
# Helpers
# --------------------------------------------------------------------------
def generate_access_code(length=8):
    """Generate a random, easy-to-read alphanumeric access code."""
    alphabet = string.ascii_uppercase + string.digits
    # avoid ambiguous characters
    alphabet = alphabet.translate({ord(c): None for c in "0O1I"})
    while True:
        code = "".join(secrets.choice(alphabet) for _ in range(length))
        if not Visitor.query.filter_by(access_code=code).first():
            return code


def generate_qr_for_visitor(visitor):
    """Create a QR code image encoding the visitor's access code and save it
    under static/qrcodes/. Returns the filename."""
    payload = f"CAMPUS-WIFI-ACCESS|code={visitor.access_code}|visitor={visitor.id}"
    img = qrcode.make(payload)
    filename = f"visitor_{visitor.id}_{visitor.access_code}.png"
    path = os.path.join(BASE_DIR, "static", "qrcodes", filename)
    img.save(path)
    return filename


def admin_required(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        if not session.get("is_admin"):
            flash("Please log in as admin to continue.", "error")
            return redirect(url_for("admin_login"))
        return view(*args, **kwargs)
    return wrapped


# --------------------------------------------------------------------------
# Visitor-facing routes
# --------------------------------------------------------------------------
@app.route("/")
def home():
    return render_template("index.html")


@app.route("/register", methods=["POST"])
def register():
    name = request.form.get("name", "").strip()
    mobile = request.form.get("mobile", "").strip()
    purpose = request.form.get("purpose", "").strip()
    host_department = request.form.get("host_department", "").strip()

    if not name or not mobile or not purpose:
        flash("Name, mobile number, and purpose of visit are required.", "error")
        return redirect(url_for("home"))

    if not (mobile.isdigit() and 7 <= len(mobile) <= 15):
        flash("Please enter a valid mobile number.", "error")
        return redirect(url_for("home"))

    visitor = Visitor(
        name=name,
        mobile=mobile,
        purpose=purpose,
        host_department=host_department or None,
    )
    db.session.add(visitor)
    db.session.commit()
    log_activity("Visitor registered and awaiting admin approval", visitor)

    return redirect(url_for("status", visitor_id=visitor.id))


@app.route("/status/<int:visitor_id>")
def status(visitor_id):
    visitor = Visitor.query.get_or_404(visitor_id)
    return render_template("status.html", visitor=visitor)


@app.route("/lookup", methods=["GET", "POST"])
def lookup():
    """Let a returning visitor find their request status using their mobile number."""
    results = None
    if request.method == "POST":
        mobile = request.form.get("mobile", "").strip()
        results = Visitor.query.filter_by(mobile=mobile).order_by(Visitor.requested_at.desc()).all()
        if not results:
            flash("No visitor request found for that mobile number.", "error")
    return render_template("lookup.html", results=results)


@app.route("/verify/<code>")
def verify(code):
    """Public endpoint a gateway / router / ESP32 captive portal could call
    to check whether an access code is currently valid. Returns JSON."""
    visitor = Visitor.query.filter_by(access_code=code).first()
    if not visitor:
        return jsonify({"valid": False, "reason": "Code not found"}), 404

    current = visitor.current_status()
    valid = current == "Active"
    return jsonify({
        "valid": valid,
        "status": current,
        "visitor_name": visitor.name,
        "expires_at": visitor.expires_at.isoformat() if visitor.expires_at else None,
    })


# --------------------------------------------------------------------------
# Admin routes
# --------------------------------------------------------------------------
@app.route("/admin/login", methods=["GET", "POST"])
def admin_login():
    if request.method == "POST":
        username = request.form.get("username", "")
        password = request.form.get("password", "")
        if username == ADMIN_USERNAME and password == ADMIN_PASSWORD:
            session["is_admin"] = True
            flash("Logged in successfully.", "success")
            return redirect(url_for("admin_dashboard"))
        flash("Invalid admin credentials.", "error")
    return render_template("admin_login.html")


@app.route("/admin/logout")
def admin_logout():
    session.pop("is_admin", None)
    flash("Logged out.", "success")
    return redirect(url_for("admin_login"))


@app.route("/admin/dashboard")
@admin_required
def admin_dashboard():
    pending = Visitor.query.filter_by(status="Pending").order_by(Visitor.requested_at.desc()).all()
    approved = Visitor.query.filter_by(status="Approved").order_by(Visitor.approved_at.desc()).all()
    rejected = Visitor.query.filter_by(status="Rejected").order_by(Visitor.requested_at.desc()).all()
    return render_template(
        "admin_dashboard.html",
        pending=pending,
        approved=approved,
        rejected=rejected,
    )


@app.route("/admin/approve/<int:visitor_id>", methods=["POST"])
@admin_required
def approve(visitor_id):
    visitor = Visitor.query.get_or_404(visitor_id)
    try:
        hours = float(request.form.get("hours", DEFAULT_ACCESS_HOURS))
    except ValueError:
        hours = DEFAULT_ACCESS_HOURS

    visitor.status = "Approved"
    visitor.access_code = generate_access_code()
    visitor.approved_at = datetime.utcnow()
    visitor.expires_at = datetime.utcnow() + timedelta(hours=hours)
    db.session.commit()

    visitor.qr_filename = generate_qr_for_visitor(visitor)
    db.session.commit()

    log_activity(f"Access approved by admin for {hours}h (code {visitor.access_code})", visitor)
    flash(f"Approved {visitor.name} for {hours} hour(s) of access.", "success")
    return redirect(url_for("admin_dashboard"))


@app.route("/admin/reject/<int:visitor_id>", methods=["POST"])
@admin_required
def reject(visitor_id):
    visitor = Visitor.query.get_or_404(visitor_id)
    visitor.status = "Rejected"
    db.session.commit()
    log_activity("Access request rejected by admin", visitor)
    flash(f"Rejected request from {visitor.name}.", "success")
    return redirect(url_for("admin_dashboard"))


@app.route("/admin/revoke/<int:visitor_id>", methods=["POST"])
@admin_required
def revoke(visitor_id):
    """Manually expire a visitor's access immediately (e.g. visitor leaving early)."""
    visitor = Visitor.query.get_or_404(visitor_id)
    visitor.expires_at = datetime.utcnow()
    db.session.commit()
    log_activity("Access manually revoked by admin", visitor)
    flash(f"Revoked access for {visitor.name}.", "success")
    return redirect(url_for("admin_dashboard"))


@app.route("/admin/logs")
@admin_required
def admin_logs():
    logs = ActivityLog.query.order_by(ActivityLog.timestamp.desc()).all()
    return render_template("admin_logs.html", logs=logs)


# --------------------------------------------------------------------------
# Entry point
# --------------------------------------------------------------------------
def init_db():
    with app.app_context():
        db.create_all()


if __name__ == "__main__":
    init_db()
    app.run(debug=True)
