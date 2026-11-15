# Mobile Shop Management System

A Flask web application for a mobile phone and accessories shop. Customers can browse products, pay online (UPI / QR), place orders and give feedback. The shop admin manages products, customers, payments, and sends email / SMS updates from an admin panel.

## Features

### Customer side
- Browse mobiles and accessories (phones, chargers, power banks, cases, watches, earbuds, memory cards, wireless chargers and more)
- Search products
- Online payment page with UPI QR code and auto-filled order details
- View purchase history
- Submit and manage feedback

### Admin side
- Admin login and dashboard
- Add, edit and delete products (with image upload)
- Customer management: add customers, view order details, update order status
- View online payments and sales reports
- Send email to a customer (order confirmation or custom message) and keep email history
- Send SMS to a customer or in bulk (via Twilio)
- View customer feedback
- Settings page to store email / SMS credentials locally

## Tech Stack
- **Backend:** Python, Flask
- **Storage:** JSON files (customers, products, payments) and SQLite (feedback)
- **Frontend:** HTML, CSS, JavaScript, Jinja2 templates
- **Integrations:** Gmail SMTP (email), Twilio (SMS)

## Project Structure
```
mobile-shop-management/
├── app.py                       # All Flask routes and logic
├── products_catalog.json        # Product catalog (sample data)
├── local_config.example.json    # Template for email / SMS credentials
├── requirements.txt
├── static/
│   ├── css/
│   ├── images/                  # Product images
│   └── uploads/                 # Uploaded product images
└── templates/                   # HTML pages (user + admin)
```

## Getting Started

### Prerequisites
- Python 3.8+

### 1. Clone and install
```bash
git clone https://github.com/<your-username>/mobile-shop-management.git
cd mobile-shop-management
python -m venv venv
venv\Scripts\activate          # Linux/Mac: source venv/bin/activate
pip install -r requirements.txt
```

### 2. Run the app
```bash
python app.py
```
Open `http://127.0.0.1:5000`.

Customer and payment data files (`customers_data.json`, `online_payments.json`) and the feedback database are created automatically when you use the app.

### 3. Default logins (change these)
| Role | Username | Password |
|---|---|---|
| Admin | `admin` | `admin123` |
| User | `user` | `user123` |

Override the admin login with environment variables `ADMIN_USER` and `ADMIN_PASSWORD`.

## Configuration

Nothing secret is stored in the code. Set these as environment variables (or use the admin **Settings** page).

PowerShell example:
```
$env:SECRET_KEY="a_long_random_string"
$env:SHOP_PHONE="your_phone"
$env:SHOP_EMAIL="shop@yourmail.com"
$env:SHOP_UPI_ID="yourname@upi"
```

| Variable | Purpose |
|---|---|
| `SECRET_KEY` | Flask session key |
| `ADMIN_USER`, `ADMIN_PASSWORD` | Admin login |
| `SHOP_PHONE`, `SHOP_EMAIL`, `SHOP_UPI_ID` | Shop contact details shown to customers |
| `SENDER_EMAIL`, `SENDER_PASSWORD` | Gmail address and **app password** for sending email |
| `SMTP_SERVER`, `SMTP_PORT` | Defaults: `smtp.gmail.com`, `465` |
| `TWILIO_SID`, `TWILIO_TOKEN`, `TWILIO_FROM` | Twilio credentials for SMS |

Alternatively copy `local_config.example.json` to `local_config.json` and fill in your values. That file is in `.gitignore` and must never be committed.

## Future Improvements
- Store data in a real database instead of JSON files
- Hash passwords and add proper customer accounts
- Online payment gateway integration
- Stock tracking and low-stock alerts

## Author
**Priyanka M**
[LinkedIn](https://linkedin.com/in/priyanka-m-9358972a7)
