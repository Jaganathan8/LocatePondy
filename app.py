"""
LOCATEPONDY - Discover Food Shops Across Pondicherry
=====================================================
Full-stack Flask application (Python backend + Jinja2 frontend).

Run:
    pip install -r requirements.txt
    python app.py

Then open http://127.0.0.1:5000

On first run a default admin account is seeded from config (ADMIN_USERNAME /
ADMIN_PASSWORD, or the matching environment variables). Log in to it at
/admin/login and change the password immediately if you kept the default.
"""

import os
import random
import string
import uuid
from datetime import datetime, timedelta
from functools import wraps

from flask import (
    Flask, render_template, request, redirect, url_for,
    flash, session, abort
)
from flask_sqlalchemy import SQLAlchemy
from flask_login import (
    LoginManager, UserMixin, login_user, logout_user,
    login_required, current_user
)
from flask_wtf import CSRFProtect
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from werkzeug.security import generate_password_hash, check_password_hash
from sqlalchemy import func

from config import Config

# ----------------------------------------------------------------------
# App / Extensions setup
# ----------------------------------------------------------------------
app = Flask(__name__)
app.config.from_object(Config)

if app.config["SECRET_KEY"] == "locatepondy-dev-secret-change-in-production":
    print(
        "\n*** WARNING: SECRET_KEY is still the default dev value. "
        "Set a strong SECRET_KEY environment variable before deploying. ***\n"
    )

db = SQLAlchemy(app)
csrf = CSRFProtect(app)
limiter = Limiter(get_remote_address, app=app, default_limits=[])

login_manager = LoginManager(app)
login_manager.login_view = "login"
login_manager.login_message = "Please log in to add or manage shops."
login_manager.login_message_category = "info"

ALLOWED_EXTENSIONS = {"png", "jpg", "jpeg", "gif", "webp"}

PONDY_AREAS = [
    "White Town",
    "Heritage Town (Tamil Quarter)",
    "Muthialpet",
    "Lawspet",
    "Reddiarpalayam",
    "Kalapet",
    "Thattanchavady",
    "Ariyankuppam",
    "Ozhukarai",
    "Villianur",
    "Mudaliarpet",
    "Uppalam",
    "Nellithope",
    "Auroville & Suburbs",
    "Karuvadikuppam",
]

SHOP_CATEGORIES = [
    "South Indian",
    "North Indian",
    "French / Continental",
    "Cafe & Bakery",
    "Street Food",
    "Sea Food",
    "Fast Food",
    "Ice Cream & Desserts",
    "Juice & Beverages",
    "Bar & Restaurant",
    "Vegan / Healthy",
    "Sweets & Snacks",
    "Other",
]


# ----------------------------------------------------------------------
# Models
# ----------------------------------------------------------------------
class Admin(UserMixin, db.Model):
    """Separate admin account, kept in its own table so it can never be
    created or upgraded to from the public registration form."""
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    password_hash = db.Column(db.String(255), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    failed_login_attempts = db.Column(db.Integer, default=0)
    locked_until = db.Column(db.DateTime, nullable=True)

    is_admin = True  # class-level flag used in templates / decorators

    def get_id(self):
        return f"admin-{self.id}"

    def set_password(self, raw):
        self.password_hash = generate_password_hash(raw)

    def check_password(self, raw):
        return check_password_hash(self.password_hash, raw)


class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(120), nullable=False)
    phone = db.Column(db.String(20), unique=True, nullable=True)
    email = db.Column(db.String(150), unique=True, nullable=True)
    password_hash = db.Column(db.String(255), nullable=True)
    auth_provider = db.Column(db.String(20), default="phone")  # phone | email | google
    google_id = db.Column(db.String(150), unique=True, nullable=True)
    avatar_url = db.Column(db.String(300), nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    failed_login_attempts = db.Column(db.Integer, default=0)
    locked_until = db.Column(db.DateTime, nullable=True)

    is_admin = False  # class-level flag used in templates / decorators

    shops = db.relationship("Shop", backref="owner", lazy=True,
                             cascade="all, delete-orphan")
    ratings = db.relationship("Rating", backref="user", lazy=True,
                               cascade="all, delete-orphan")
    feedbacks = db.relationship("Feedback", backref="user", lazy=True,
                                 cascade="all, delete-orphan")

    def get_id(self):
        return f"user-{self.id}"

    def set_password(self, raw):
        self.password_hash = generate_password_hash(raw)

    def check_password(self, raw):
        if not self.password_hash:
            return False
        return check_password_hash(self.password_hash, raw)


class Shop(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    owner_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)

    name = db.Column(db.String(150), nullable=False)
    category = db.Column(db.String(80), nullable=False)
    area = db.Column(db.String(80), nullable=False)
    phone_number = db.Column(db.String(20), nullable=False)
    description = db.Column(db.Text, nullable=True)
    map_link = db.Column(db.String(500), nullable=True)
    address = db.Column(db.String(300), nullable=True)

    # Scrolling promotional text shown over the shop's photo(s)
    offer_text = db.Column(db.String(200), nullable=True)

    # Verification / moderation workflow — every listing must be approved
    # by the admin before it is publicly visible. Only the admin can
    # edit, approve, reject, or delete a listing after it is submitted.
    status = db.Column(db.String(20), default="pending")  # pending | approved | rejected
    rejection_reason = db.Column(db.String(300), nullable=True)
    reviewed_at = db.Column(db.DateTime, nullable=True)

    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    images = db.relationship("ShopImage", backref="shop", lazy=True,
                              cascade="all, delete-orphan",
                              order_by="ShopImage.position")
    ratings = db.relationship("Rating", backref="shop", lazy=True,
                               cascade="all, delete-orphan")
    feedbacks = db.relationship("Feedback", backref="shop", lazy=True,
                                 cascade="all, delete-orphan")

    @property
    def average_rating(self):
        if not self.ratings:
            return 0
        return round(sum(r.stars for r in self.ratings) / len(self.ratings), 1)

    @property
    def rating_count(self):
        return len(self.ratings)

    @property
    def is_verified(self):
        return self.status == "approved"

    @property
    def cover_image(self):
        return self.images[0].filename if self.images else None


class ShopImage(db.Model):
    """Up to MAX_PHOTOS_PER_SHOP rows per shop."""
    id = db.Column(db.Integer, primary_key=True)
    shop_id = db.Column(db.Integer, db.ForeignKey("shop.id"), nullable=False)
    filename = db.Column(db.String(300), nullable=False)
    position = db.Column(db.Integer, default=0)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)


class Rating(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    shop_id = db.Column(db.Integer, db.ForeignKey("shop.id"), nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)
    stars = db.Column(db.Integer, nullable=False)  # 1-5
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    __table_args__ = (db.UniqueConstraint("shop_id", "user_id",
                                           name="one_rating_per_user_per_shop"),)


class Feedback(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    shop_id = db.Column(db.Integer, db.ForeignKey("shop.id"), nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)
    message = db.Column(db.Text, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)


@login_manager.user_loader
def load_user(composite_id):
    """composite_id looks like 'admin-3' or 'user-17'."""
    try:
        kind, raw_id = composite_id.split("-", 1)
        raw_id = int(raw_id)
    except (ValueError, AttributeError):
        return None
    if kind == "admin":
        return Admin.query.get(raw_id)
    if kind == "user":
        return User.query.get(raw_id)
    return None


# ----------------------------------------------------------------------
# Security helpers
# ----------------------------------------------------------------------
def admin_required(view_func):
    @wraps(view_func)
    def wrapped(*args, **kwargs):
        if not current_user.is_authenticated or not getattr(current_user, "is_admin", False):
            abort(403)
        return view_func(*args, **kwargs)
    return wrapped


def is_locked(account):
    return bool(account.locked_until and account.locked_until > datetime.utcnow())


def register_failed_attempt(account):
    account.failed_login_attempts = (account.failed_login_attempts or 0) + 1
    if account.failed_login_attempts >= app.config["MAX_FAILED_LOGIN_ATTEMPTS"]:
        account.locked_until = datetime.utcnow() + timedelta(
            minutes=app.config["ACCOUNT_LOCKOUT_MINUTES"]
        )
    db.session.commit()


def reset_failed_attempts(account):
    account.failed_login_attempts = 0
    account.locked_until = None
    db.session.commit()


def password_is_strong(raw):
    """Minimum bar: 8+ characters with at least one letter and one digit."""
    if len(raw) < 8:
        return False
    has_letter = any(c.isalpha() for c in raw)
    has_digit = any(c.isdigit() for c in raw)
    return has_letter and has_digit


def generate_otp():
    return "".join(random.choices(string.digits, k=6))


# ----------------------------------------------------------------------
# Upload helpers
# ----------------------------------------------------------------------
def allowed_file(filename):
    return "." in filename and filename.rsplit(".", 1)[1].lower() in ALLOWED_EXTENSIONS


def save_shop_image(file_storage):
    if not file_storage or file_storage.filename == "":
        return None
    if not allowed_file(file_storage.filename):
        flash(f"'{file_storage.filename}': unsupported format. Use png, jpg, jpeg, gif or webp.", "danger")
        return None
    ext = file_storage.filename.rsplit(".", 1)[1].lower()
    filename = f"{uuid.uuid4().hex}.{ext}"
    path = os.path.join(app.config["UPLOAD_FOLDER"], filename)
    file_storage.save(path)
    return filename


def delete_shop_images(shop):
    for img in shop.images:
        path = os.path.join(app.config["UPLOAD_FOLDER"], img.filename)
        if os.path.exists(path):
            os.remove(path)


@app.context_processor
def inject_globals():
    return {
        "PONDY_AREAS": PONDY_AREAS,
        "SHOP_CATEGORIES": SHOP_CATEGORIES,
        "current_year": datetime.utcnow().year,
        "SHOP_NAME_MAX_LENGTH": app.config["SHOP_NAME_MAX_LENGTH"],
        "MAX_PHOTOS_PER_SHOP": app.config["MAX_PHOTOS_PER_SHOP"],
    }


# ----------------------------------------------------------------------
# Public pages
# ----------------------------------------------------------------------
@app.route("/")
def home():
    approved = Shop.query.filter_by(status="approved")
    total_shops = approved.count()
    total_areas_used = db.session.query(Shop.area).filter(Shop.status == "approved").distinct().count()
    top_shops = (
        approved.outerjoin(Rating)
        .group_by(Shop.id)
        .order_by(func.count(Rating.id).desc())
        .limit(6)
        .all()
    )
    recent_shops = approved.order_by(Shop.created_at.desc()).limit(6).all()
    return render_template(
        "home.html",
        total_shops=total_shops,
        total_areas_used=total_areas_used,
        top_shops=top_shops,
        recent_shops=recent_shops,
    )


@app.route("/about")
def about():
    return render_template("about.html")


# ----------------------------------------------------------------------
# Auth: phone (OTP) + email/password + Google OAuth stub
# ----------------------------------------------------------------------
@app.route("/login", methods=["GET", "POST"])
@limiter.limit("15 per hour")
def login():
    if current_user.is_authenticated:
        return redirect(url_for("locate"))

    if request.method == "POST":
        method = request.form.get("method", "phone")

        if method == "phone":
            phone = request.form.get("phone", "").strip()
            otp = request.form.get("otp", "").strip()

            if not phone:
                flash("Enter a valid phone number.", "danger")
                return redirect(url_for("login"))

            if "send_otp" in request.form:
                generated_otp = generate_otp()
                session["pending_phone"] = phone
                session["pending_otp"] = generated_otp
                session["pending_otp_expires"] = (
                    datetime.utcnow() + timedelta(seconds=app.config["OTP_EXPIRY_SECONDS"])
                ).isoformat()
                session["otp_attempts"] = 0
                # DEMO ONLY: flashing the OTP stands in for a real SMS gateway
                # (Twilio Verify / MSG91) — see README for how to wire one in.
                flash(f"Demo OTP sent: {generated_otp} (valid 5 minutes). Replace with a real SMS gateway in production.", "info")
                return render_template("login.html", otp_stage=True, phone=phone)

            if "verify_otp" in request.form:
                expires_raw = session.get("pending_otp_expires")
                expired = not expires_raw or datetime.fromisoformat(expires_raw) < datetime.utcnow()
                session["otp_attempts"] = session.get("otp_attempts", 0) + 1

                if session["otp_attempts"] > app.config["OTP_MAX_ATTEMPTS"]:
                    flash("Too many incorrect attempts. Request a new OTP.", "danger")
                    session.pop("pending_otp", None)
                    return render_template("login.html", otp_stage=False)

                if expired:
                    flash("OTP expired. Please request a new one.", "danger")
                    return render_template("login.html", otp_stage=False)

                if phone == session.get("pending_phone") and otp == session.get("pending_otp"):
                    user = User.query.filter_by(phone=phone).first()
                    if not user:
                        user = User(name=f"User {phone[-4:]}", phone=phone, auth_provider="phone")
                        db.session.add(user)
                        db.session.commit()
                    login_user(user)
                    session.pop("pending_otp", None)
                    session.pop("pending_phone", None)
                    session.pop("otp_attempts", None)
                    flash(f"Welcome, {user.name}!", "success")
                    return redirect(url_for("locate"))
                else:
                    flash("Incorrect OTP. Try again.", "danger")
                    return render_template("login.html", otp_stage=True, phone=phone)

        elif method == "email":
            email = request.form.get("email", "").strip().lower()
            password = request.form.get("password", "")
            user = User.query.filter_by(email=email).first()

            if user and is_locked(user):
                flash("Account temporarily locked due to repeated failed logins. Try again later.", "danger")
                return render_template("login.html", otp_stage=False)

            if user and user.check_password(password):
                reset_failed_attempts(user)
                login_user(user)
                flash(f"Welcome back, {user.name}!", "success")
                return redirect(url_for("locate"))

            if user:
                register_failed_attempt(user)
            flash("Invalid email or password.", "danger")

    return render_template("login.html", otp_stage=False)


@app.route("/register", methods=["GET", "POST"])
@limiter.limit("10 per hour")
def register():
    if request.method == "POST":
        name = request.form.get("name", "").strip()
        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")

        if not name or not email or not password:
            flash("All fields are required.", "danger")
            return redirect(url_for("register"))

        if not password_is_strong(password):
            flash("Password must be at least 8 characters and include a letter and a number.", "danger")
            return redirect(url_for("register"))

        if User.query.filter_by(email=email).first():
            flash("An account with this email already exists.", "danger")
            return redirect(url_for("register"))

        user = User(name=name, email=email, auth_provider="email")
        user.set_password(password)
        db.session.add(user)
        db.session.commit()
        login_user(user)
        flash("Account created successfully!", "success")
        return redirect(url_for("locate"))

    return render_template("register.html")


@app.route("/login/google")
def google_login():
    """
    Placeholder route for Google OAuth.
    To enable real Google Sign-In:
      1. pip install authlib
      2. Create OAuth credentials at https://console.cloud.google.com
      3. Set GOOGLE_CLIENT_ID / GOOGLE_CLIENT_SECRET in config.py or env vars
      4. Register the Authlib OAuth client and redirect here to the
         provider's consent screen, then handle the callback at
         /login/google/callback to create/log in the User by google_id.
    This demo simulates a successful Google login for local testing.
    """
    demo_email = "demo.googleuser@gmail.com"
    user = User.query.filter_by(email=demo_email).first()
    if not user:
        user = User(
            name="Google Demo User",
            email=demo_email,
            google_id="demo-google-id",
            auth_provider="google",
            avatar_url="https://ui-avatars.com/api/?name=G+User&background=E8B92E&color=fff",
        )
        db.session.add(user)
        db.session.commit()
    login_user(user)
    flash("Logged in with Google (demo mode). Configure real OAuth in config.py.", "info")
    return redirect(url_for("locate"))


@app.route("/logout")
@login_required
def logout():
    logout_user()
    flash("You have been logged out.", "info")
    return redirect(url_for("home"))


# ----------------------------------------------------------------------
# Locate page: browse by area, add shops, shop detail, ratings, feedback
# ----------------------------------------------------------------------
@app.route("/locate")
def locate():
    area_filter = request.args.get("area", "")
    category_filter = request.args.get("category", "")
    search_q = request.args.get("q", "")

    query = Shop.query.filter_by(status="approved")
    if area_filter:
        query = query.filter_by(area=area_filter)
    if category_filter:
        query = query.filter_by(category=category_filter)
    if search_q:
        like = f"%{search_q}%"
        query = query.filter(Shop.name.ilike(like))

    shops = query.order_by(Shop.area, Shop.name).all()

    shops_by_area = {}
    for area in PONDY_AREAS:
        shops_by_area[area] = [s for s in shops if s.area == area]

    return render_template(
        "locate.html",
        shops_by_area=shops_by_area,
        area_filter=area_filter,
        category_filter=category_filter,
        search_q=search_q,
    )


@app.route("/locate/add", methods=["GET", "POST"])
@login_required
def add_shop():
    if getattr(current_user, "is_admin", False):
        abort(403)  # admin manages listings from the admin dashboard, not this form

    max_photos = app.config["MAX_PHOTOS_PER_SHOP"]
    name_max = app.config["SHOP_NAME_MAX_LENGTH"]

    if request.method == "POST":
        name = request.form.get("name", "").strip()
        category = request.form.get("category", "")
        area = request.form.get("area", "")
        phone_number = request.form.get("phone_number", "").strip()
        description = request.form.get("description", "").strip()
        address = request.form.get("address", "").strip()
        map_link = request.form.get("map_link", "").strip()
        offer_text = request.form.get("offer_text", "").strip()
        image_files = [f for f in request.files.getlist("images") if f and f.filename]

        if not name or not category or not area or not phone_number:
            flash("Please fill all required fields.", "danger")
            return redirect(url_for("add_shop"))

        if len(name) > name_max:
            flash(f"Shop name must be {name_max} characters or fewer.", "danger")
            return redirect(url_for("add_shop"))

        if len(image_files) > max_photos:
            flash(f"You can upload a maximum of {max_photos} photos.", "danger")
            return redirect(url_for("add_shop"))

        shop = Shop(
            owner_id=current_user.id,
            name=name,
            category=category,
            area=area,
            phone_number=phone_number,
            description=description,
            address=address,
            map_link=map_link,
            offer_text=offer_text or None,
            status="pending",
        )
        db.session.add(shop)
        db.session.flush()  # get shop.id before committing images

        for position, file_storage in enumerate(image_files[:max_photos]):
            filename = save_shop_image(file_storage)
            if filename:
                db.session.add(ShopImage(shop_id=shop.id, filename=filename, position=position))

        db.session.commit()
        flash(
            f"'{shop.name}' has been submitted for review. It will appear on LocatePondy "
            f"once our admin verifies it.",
            "success",
        )
        return redirect(url_for("my_shops"))

    return render_template("add_shop.html", max_photos=max_photos, name_max=name_max)


@app.route("/shop/<int:shop_id>", methods=["GET"])
def shop_detail(shop_id):
    shop = Shop.query.get_or_404(shop_id)

    is_owner = current_user.is_authenticated and not getattr(current_user, "is_admin", False) \
        and shop.owner_id == current_user.id
    is_admin_viewer = current_user.is_authenticated and getattr(current_user, "is_admin", False)

    if shop.status != "approved" and not (is_owner or is_admin_viewer):
        abort(404)

    feedbacks = (
        Feedback.query.filter_by(shop_id=shop.id)
        .order_by(Feedback.created_at.desc())
        .all()
    )
    user_rating = None
    if current_user.is_authenticated and not getattr(current_user, "is_admin", False):
        r = Rating.query.filter_by(shop_id=shop.id, user_id=current_user.id).first()
        user_rating = r.stars if r else None

    return render_template(
        "shop_detail.html", shop=shop, feedbacks=feedbacks, user_rating=user_rating
    )


@app.route("/shop/<int:shop_id>/rate", methods=["POST"])
@login_required
def rate_shop(shop_id):
    if getattr(current_user, "is_admin", False):
        abort(403)
    shop = Shop.query.get_or_404(shop_id)
    if shop.status != "approved":
        abort(404)
    stars = int(request.form.get("stars", 0))
    if stars < 1 or stars > 5:
        flash("Invalid rating.", "danger")
        return redirect(url_for("shop_detail", shop_id=shop.id))

    existing = Rating.query.filter_by(shop_id=shop.id, user_id=current_user.id).first()
    if existing:
        existing.stars = stars
    else:
        db.session.add(Rating(shop_id=shop.id, user_id=current_user.id, stars=stars))
    db.session.commit()
    flash("Thanks for rating this shop!", "success")
    return redirect(url_for("shop_detail", shop_id=shop.id))


@app.route("/shop/<int:shop_id>/feedback", methods=["POST"])
@login_required
def add_feedback(shop_id):
    if getattr(current_user, "is_admin", False):
        abort(403)
    shop = Shop.query.get_or_404(shop_id)
    if shop.status != "approved":
        abort(404)
    message = request.form.get("message", "").strip()
    if message:
        db.session.add(Feedback(shop_id=shop.id, user_id=current_user.id, message=message))
        db.session.commit()
        flash("Feedback submitted!", "success")
    return redirect(url_for("shop_detail", shop_id=shop.id))


@app.route("/my-shops")
@login_required
def my_shops():
    if getattr(current_user, "is_admin", False):
        return redirect(url_for("admin_dashboard"))
    shops = Shop.query.filter_by(owner_id=current_user.id).order_by(Shop.created_at.desc()).all()
    return render_template("my_shops.html", shops=shops)


# ----------------------------------------------------------------------
# Admin: separate login + full edit/verify/delete access over all listings
# ----------------------------------------------------------------------
@app.route("/admin/login", methods=["GET", "POST"])
@limiter.limit("10 per hour")
def admin_login():
    if current_user.is_authenticated and getattr(current_user, "is_admin", False):
        return redirect(url_for("admin_dashboard"))

    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "")
        admin = Admin.query.filter_by(username=username).first()

        if admin and is_locked(admin):
            flash("Admin account temporarily locked due to repeated failed logins.", "danger")
            return render_template("admin/login.html")

        if admin and admin.check_password(password):
            reset_failed_attempts(admin)
            login_user(admin)
            flash("Welcome back, admin.", "success")
            return redirect(url_for("admin_dashboard"))

        if admin:
            register_failed_attempt(admin)
        flash("Invalid admin credentials.", "danger")

    return render_template("admin/login.html")


@app.route("/admin/logout")
@login_required
@admin_required
def admin_logout():
    logout_user()
    flash("Admin logged out.", "info")
    return redirect(url_for("home"))


@app.route("/admin")
@login_required
@admin_required
def admin_dashboard():
    status_filter = request.args.get("status", "pending")
    query = Shop.query
    if status_filter in ("pending", "approved", "rejected"):
        query = query.filter_by(status=status_filter)
    shops = query.order_by(Shop.created_at.desc()).all()
    counts = {
        "pending": Shop.query.filter_by(status="pending").count(),
        "approved": Shop.query.filter_by(status="approved").count(),
        "rejected": Shop.query.filter_by(status="rejected").count(),
    }
    return render_template("admin/dashboard.html", shops=shops, status_filter=status_filter, counts=counts)


@app.route("/admin/shop/<int:shop_id>/approve", methods=["POST"])
@login_required
@admin_required
def admin_approve_shop(shop_id):
    shop = Shop.query.get_or_404(shop_id)
    shop.status = "approved"
    shop.rejection_reason = None
    shop.reviewed_at = datetime.utcnow()
    db.session.commit()
    flash(f"'{shop.name}' verified and published.", "success")
    return redirect(url_for("admin_dashboard"))


@app.route("/admin/shop/<int:shop_id>/reject", methods=["POST"])
@login_required
@admin_required
def admin_reject_shop(shop_id):
    shop = Shop.query.get_or_404(shop_id)
    shop.status = "rejected"
    shop.rejection_reason = request.form.get("reason", "").strip() or "Did not meet listing guidelines."
    shop.reviewed_at = datetime.utcnow()
    db.session.commit()
    flash(f"'{shop.name}' rejected.", "info")
    return redirect(url_for("admin_dashboard"))


@app.route("/admin/shop/<int:shop_id>/edit", methods=["GET", "POST"])
@login_required
@admin_required
def admin_edit_shop(shop_id):
    shop = Shop.query.get_or_404(shop_id)
    max_photos = app.config["MAX_PHOTOS_PER_SHOP"]
    name_max = app.config["SHOP_NAME_MAX_LENGTH"]

    if request.method == "POST":
        name = request.form.get("name", "").strip()
        category = request.form.get("category", "")
        area = request.form.get("area", "")
        phone_number = request.form.get("phone_number", "").strip()
        description = request.form.get("description", "").strip()
        address = request.form.get("address", "").strip()
        map_link = request.form.get("map_link", "").strip()
        offer_text = request.form.get("offer_text", "").strip()
        new_files = [f for f in request.files.getlist("images") if f and f.filename]
        remove_ids = set(request.form.getlist("remove_image_ids"))

        if not name or not category or not area or not phone_number:
            flash("Please fill all required fields.", "danger")
            return redirect(url_for("admin_edit_shop", shop_id=shop.id))

        if len(name) > name_max:
            flash(f"Shop name must be {name_max} characters or fewer.", "danger")
            return redirect(url_for("admin_edit_shop", shop_id=shop.id))

        remaining = [img for img in shop.images if str(img.id) not in remove_ids]
        removed = [img for img in shop.images if str(img.id) in remove_ids]

        if len(remaining) + len(new_files) > max_photos:
            flash(f"A shop can have at most {max_photos} photos.", "danger")
            return redirect(url_for("admin_edit_shop", shop_id=shop.id))

        for img in removed:
            path = os.path.join(app.config["UPLOAD_FOLDER"], img.filename)
            if os.path.exists(path):
                os.remove(path)
            db.session.delete(img)

        next_position = len(remaining)
        for file_storage in new_files[: max_photos - len(remaining)]:
            filename = save_shop_image(file_storage)
            if filename:
                db.session.add(ShopImage(shop_id=shop.id, filename=filename, position=next_position))
                next_position += 1

        shop.name = name
        shop.category = category
        shop.area = area
        shop.phone_number = phone_number
        shop.description = description
        shop.address = address
        shop.map_link = map_link
        shop.offer_text = offer_text or None

        db.session.commit()
        flash(f"'{shop.name}' has been updated.", "success")
        return redirect(url_for("shop_detail", shop_id=shop.id))

    return render_template("admin/edit_shop.html", shop=shop, max_photos=max_photos, name_max=name_max)


@app.route("/admin/shop/<int:shop_id>/delete", methods=["POST"])
@login_required
@admin_required
def admin_delete_shop(shop_id):
    shop = Shop.query.get_or_404(shop_id)
    delete_shop_images(shop)
    db.session.delete(shop)
    db.session.commit()
    flash("Shop listing removed.", "info")
    return redirect(url_for("admin_dashboard"))


# ----------------------------------------------------------------------
# Error handlers
# ----------------------------------------------------------------------
@app.errorhandler(404)
def not_found(e):
    return render_template("404.html"), 404


@app.errorhandler(403)
def forbidden(e):
    return render_template("403.html"), 403


@app.errorhandler(429)
def rate_limited(e):
    flash("Too many attempts. Please wait a bit before trying again.", "danger")
    return render_template("403.html"), 429


# ----------------------------------------------------------------------
# CLI init / admin seeding
# ----------------------------------------------------------------------
def init_db():
    with app.app_context():
        db.create_all()
        seed_admin()
        print("Database initialized at:", app.config["SQLALCHEMY_DATABASE_URI"])


def seed_admin():
    """Create the default admin account on first run if none exists yet."""
    if Admin.query.count() > 0:
        return
    admin = Admin(username=app.config["ADMIN_USERNAME"])
    admin.set_password(app.config["ADMIN_PASSWORD"])
    db.session.add(admin)
    db.session.commit()
    print(
        f"\n*** Seeded admin account: username='{admin.username}'. "
        f"Log in at /admin/login and change the password if you used the default. ***\n"
    )


if __name__ == "__main__":
    os.makedirs(app.config["UPLOAD_FOLDER"], exist_ok=True)
    init_db()
    app.run(debug=True)
