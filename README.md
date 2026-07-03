# 📍 LOCATEPONDY

A full-stack Python (Flask) web app to discover, list, and rate every food shop across Puducherry (Pondicherry) — organized area by area, styled in a **"White Town"** color theme (whitewashed walls, mustard facades, bougainvillea pink, colonial blue shutters).

## What's new in this update

- **Renamed** from Pondyshopy → **LocatePondy** throughout the app, templates, and docs.
- **Separate admin account** with its own login (`/admin/login`), independent from regular users. Only the admin can edit, verify, reject, or delete shop listings — regular users can add a listing but not modify it afterward (contact the admin for corrections).
- **Shop name limited to 150 characters**, enforced both in the form (`maxlength`) and on the server.
- **Up to 5 photos per shop** (previously 1), with a max-5 limit enforced client-side and server-side.
- **Scrolling offer/promo banner** — an optional `offer_text` field shows as an animated marquee over the shop's photo on both the listing card and the detail page.
- **Photo carousel** on the shop detail page when a shop has multiple photos.
- **Listing verification workflow** — every new shop starts as `pending`. It is only shown publicly on the Home/Locate pages once the admin approves it from `/admin`. Owners can track status (pending / verified / rejected) on **My Shops**.
- **Security hardening**:
  - CSRF protection (Flask-WTF) on every form.
  - Rate limiting (Flask-Limiter) on login, registration, and admin login.
  - Account lockout after 5 failed login attempts (15-minute cooldown), for both users and admin.
  - Random, expiring (5-minute) OTPs instead of a hardcoded code, with a capped number of verification attempts.
  - Minimum password strength rule on registration (8+ chars, letter + number).
  - Secure session cookie flags (`HttpOnly`, `SameSite=Lax`, `Secure` when `FORCE_HTTPS=1`).
  - A startup warning if `SECRET_KEY` is still the default dev value.

## Features

- **Home page** — hero banner, live stats, newest & most-rated *verified* shops
- **About page** — mission and feature overview
- **Login page** — Phone number + OTP login, Email/password login, Google login (demo stub, ready for real OAuth)
- **Register page** — email/password account creation
- **Locate page** — the core page:
  - Every Pondicherry area listed (White Town, Heritage Town, Lawspet, Kalapet, Ariyankuppam, Villianur, Ozhukarai, Auroville & more)
  - Shops grouped area-wise, filterable by area/category, searchable by name
  - Logged-in users can **add a shop** with: up to 5 images, name, category, area, phone number, description, address, an optional scrolling offer, and a Google Maps link — submitted for admin verification
  - Each shop detail page shows: photo carousel, scrolling offer banner, name, category, phone (tap to call), description, **5-star rating system**, **feedback/review box**, and an **embedded Google Map link**
- **My Shops page** — track the verification status of shops you've submitted
- **Admin dashboard** (`/admin`) — approve, reject (with reason), edit, or delete any listing

## Tech Stack

- **Backend:** Python, Flask, Flask-SQLAlchemy, Flask-Login, Flask-WTF (CSRF), Flask-Limiter (rate limiting)
- **Database:** SQLite (file-based, zero setup) — swap `DATABASE_URL` for Postgres/MySQL in production
- **Frontend:** Jinja2 templates, vanilla CSS (White Town theme) + vanilla JS (photo carousel, offer marquee, no build step needed)
- **Auth:** Werkzeug password hashing, session-based OTP flow with expiry, Google OAuth stub, separate Admin login

## Getting Started

```bash
cd locatepondy
pip install -r requirements.txt
python app.py
```

Open **http://127.0.0.1:5000** in your browser. The SQLite database (`locatepondy.db`) and tables are created automatically on first run, and a default admin account is seeded.

### Default admin login

On first run, an admin account is created from environment variables (or these defaults if unset):

```
ADMIN_USERNAME=admin
ADMIN_PASSWORD=ChangeMe@123
```

**Set your own values before running in anything but local dev**, e.g.:

```bash
export ADMIN_USERNAME=your_admin_name
export ADMIN_PASSWORD='something-long-and-random'
python app.py
```

Log in at `/admin/login`. From the admin dashboard you can approve/reject pending listings and edit or delete any shop.

## Project Structure

```
locatepondy/
├── app.py                 # All routes, models, and app logic
├── config.py               # Configuration (secret key, DB URI, admin creds, OAuth keys)
├── requirements.txt
├── static/
│   ├── css/style.css       # White Town theme, offer marquee, carousel styles
│   ├── js/                 # (reserved for extra JS)
│   └── uploads/            # shop images uploaded by users
└── templates/
    ├── base.html            # navbar, flash messages, footer
    ├── home.html
    ├── about.html
    ├── login.html
    ├── register.html
    ├── locate.html          # area-wise shop directory (verified shops only)
    ├── add_shop.html        # name char-count, up to 5 photos, offer text
    ├── shop_detail.html     # carousel, offer marquee, ratings, feedback
    ├── my_shops.html        # status tracking, no edit/delete (admin-only)
    ├── _shop_card.html      # reusable shop card partial
    ├── admin/
    │   ├── login.html
    │   ├── dashboard.html   # approve / reject / edit / delete queue
    │   └── edit_shop.html   # full modify access (admin only)
    ├── 404.html / 403.html
```

## Connecting Real Services (Production Checklist)

The app ships with **demo-mode** stand-ins for two things that normally require paid third-party accounts. Swap these in for production:

### 1. Phone OTP (currently a random 6-digit code shown via flash message)
In `app.py`, inside the `login()` view, replace the `generate_otp()` call/flash with a call to a real SMS gateway, e.g. **Twilio Verify** or **MSG91**:
```python
# Example with Twilio
from twilio.rest import Client
client = Client(account_sid, auth_token)
client.verify.v2.services(service_sid).verifications.create(to=phone, channel="sms")
```

### 2. Google Sign-In (currently a demo auto-login)
1. `pip install authlib`
2. Create OAuth 2.0 credentials at the [Google Cloud Console](https://console.cloud.google.com/)
3. Add your `GOOGLE_CLIENT_ID` / `GOOGLE_CLIENT_SECRET` as environment variables
4. Register an Authlib `OAuth` client in `app.py` and replace the `/login/google` route with the real
   authorize-redirect + `/login/google/callback` handler that reads the verified email/sub from Google
   and creates/logs in the matching `User`.

### 3. Deployment
- Set a strong `SECRET_KEY` and `ADMIN_PASSWORD` via environment variables
- Set `FORCE_HTTPS=1` once served over HTTPS so session cookies are marked `Secure`
- Switch `SQLALCHEMY_DATABASE_URI` to Postgres/MySQL for concurrent users
- Configure a persistent Flask-Limiter storage backend (e.g. Redis) instead of the default in-memory store
- Serve behind Gunicorn/uWSGI + Nginx, not `app.run()`
- Store uploaded images in S3/Cloud Storage instead of the local filesystem for scalability

## Areas Covered

White Town, Heritage Town (Tamil Quarter), Muthialpet, Lawspet, Reddiarpalayam, Kalapet, Thattanchavady, Ariyankuppam, Ozhukarai, Villianur, Mudaliarpet, Uppalam, Nellithope, Auroville & Suburbs, Karuvadikuppam.

(Add or edit areas in the `PONDY_AREAS` list at the top of `app.py`.)

## Categories

South Indian, North Indian, French/Continental, Cafe & Bakery, Street Food, Sea Food, Fast Food, Ice Cream & Desserts, Juice & Beverages, Bar & Restaurant, Vegan/Healthy, Sweets & Snacks, Other.

(Edit the `SHOP_CATEGORIES` list in `app.py` to customize.)
