# Campus Visitor Network Access Management (GatepassNet)

2nd Year IT Engineering — Data Communication mini-project.

A working Flask website where campus visitors register for temporary Wi-Fi
access, an admin approves or rejects each request, and the system issues a
unique access code + QR code that expires automatically after a set time.

---

## 1. How to run it

```bash
# 1. Create a virtual environment (recommended)
python -m venv venv
source venv/bin/activate        # Windows: venv\Scripts\activate

# 2. Install dependencies
pip install -r requirements.txt

# 3. Run the app
python app.py
```

Open **http://127.0.0.1:5000** in your browser.

- Visitor registration form: `/`
- Check status by mobile number: `/lookup`
  (edit `ADMIN_USERNAME` / `ADMIN_PASSWORD` at the top of `app.py`)

The database (`instance/visitors.db`) and QR code images
(`static/qrcodes/`) are created automatically the first time you run the app.

### Switching from SQLite to MySQL

The project ships with SQLite so it runs with zero setup for a demo/viva.
To use MySQL (as listed in the original tech stack):

```bash
pip install pymysql
```

Then in `app.py`, change:

```python
app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///" + os.path.join(BASE_DIR, "instance", "visitors.db")
```

to:

```python
app.config["SQLALCHEMY_DATABASE_URI"] = "mysql+pymysql://root:yourpassword@localhost/campus_visitor_db"
```

(Create the `campus_visitor_db` database in MySQL first — `CREATE DATABASE campus_visitor_db;`)
No other code needs to change, since Flask-SQLAlchemy handles both engines
identically.

---

## 2. How the system works (project flow)

1. **Registration** — a visitor fills in name, mobile number, purpose of
   visit, and optional host department. The request is stored with status
   `Pending`.
2. **Admin review** — the admin logs in, sees all pending requests on the
   dashboard, and either **approves** (choosing an access duration: 1/4/8/24
   hours) or **rejects** each one.
3. **Code + QR generation** — on approval, the server generates a random
   8-character access code and a QR code image encoding it, and stores an
   expiry timestamp (`approved_at + duration`).
4. **Visitor access** — the visitor's status page shows the access code and
   QR code and can be scanned/entered at a captive portal or gate device.
5. **Automatic expiry** — the app never needs a background job: every time a
   status is checked, `Visitor.current_status()` compares `expires_at` to the
   current time and reports `Active` or `Expired` accordingly. The optional
   `/verify/<code>` JSON endpoint lets a router, captive portal, or ESP32
   device check validity programmatically — this is the hook point for a
   real Wi-Fi router/RADIUS integration or IoT demo.
6. **Activity log** — every registration, approval, rejection, and manual
   revoke is written to an `ActivityLog` table and viewable at
   `/admin/logs`.

---

## 3. Tech stack used in this implementation

| Layer      | Technology |
|------------|------------|
| Frontend   | HTML5, CSS3 (custom, no framework), vanilla structure via Jinja2 templates |
| Backend    | Python 3, Flask, Flask-SQLAlchemy |
| Database   | SQLite by default (MySQL-compatible, see above) |
| QR codes   | `qrcode` + `Pillow` Python libraries |
| Auth       | Session-based admin login (Flask `session`) |

---

## 4. Project write-up (for your report/PPT)

**Objective:** To provide secure and temporary Wi-Fi/network access to
visitors on a college campus while ensuring that only authorized users can
use the network.

**Description:** A visitor registers with their name, mobile number, and
purpose of visit. The admin approves the request and the system generates a
temporary access code and QR code. The visitor gets internet access for a
limited time, after which access automatically expires.

**Features implemented:**
- Visitor registration form
- Admin login (session-based)
- Temporary Wi-Fi access code generation (random, unique, 8 characters)
- QR code generation per visitor for authentication
- Automatic access expiry after a configurable duration
- Visitor activity log (registration, approval, rejection, revoke events)
- Visitor self-service status lookup by mobile number
- `/verify/<code>` API endpoint for gateway/IoT integration

**Advantages:**
- Improves network security by avoiding shared/static Wi-Fi passwords
- Prevents unauthorized or indefinite access through automatic expiry
- Easy for front-desk/admin staff to manage visitor requests in one place
- Maintains a complete, timestamped visitor and access record

**Applications:** Colleges and universities, corporate/office campuses,
hospitals, hotels, and any gated facility that needs short-term guest
network access.

---

## 5. Database schema (ER overview)

**Visitor**
| Column | Type | Notes |
|---|---|---|
| id | Integer PK | |
| name | String | |
| mobile | String | |
| purpose | String | |
| host_department | String | optional |
| status | String | Pending / Approved / Rejected |
| access_code | String | unique, set on approval |
| qr_filename | String | set on approval |
| requested_at | DateTime | |
| approved_at | DateTime | nullable |
| expires_at | DateTime | nullable; drives Active/Expired |

**ActivityLog**
| Column | Type | Notes |
|---|---|---|
| id | Integer PK | |
| visitor_id | Integer FK → Visitor.id | nullable |
| visitor_name | String | denormalized for easy log reading |
| action | String | free-text description |
| timestamp | DateTime | |

`ActivityLog.visitor_id` is a foreign key to `Visitor.id` — a simple 1-to-many
relationship (one visitor can have many log entries).

---

## 6. Possible future extensions (good "future scope" slide content)

- **ESP32 / IoT demo:** point a captive-portal-style ESP32 sketch at the
  `/verify/<code>` endpoint over Wi-Fi to physically gate a relay/LED as a
  stand-in for real network access control.
- **RADIUS/router integration:** call `/verify/<code>` from a router's
  captive portal or a FreeRADIUS script to actually grant/deny network
  access, rather than just returning a JSON status.
- **SMS/email delivery** of the access code using an SMS gateway API instead
  of only showing it on-screen.
- **Admin accounts with hashed passwords** stored in the database instead of
  the single hardcoded demo login.
- **Analytics dashboard** — visits per day/department, average approval time,
  peak visiting hours.

---

## 7. File structure

```
campus_visitor_access/
├── app.py                  # Flask app: models, routes, QR + expiry logic
├── requirements.txt
├── instance/
│   └── visitors.db         # created automatically (SQLite)
├── static/
│   ├── css/style.css
│   └── qrcodes/             # generated QR code images
└── templates/
    ├── base.html
    ├── index.html           # visitor registration + hero
    ├── status.html          # visitor's access code / QR / status
    ├── lookup.html           # find request by mobile number
    ├── admin_login.html
    ├── admin_dashboard.html  # approve / reject / revoke
    └── admin_logs.html       # full activity log
```
