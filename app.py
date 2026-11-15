from flask import Flask, render_template, request, redirect, url_for, flash
import random
import json
import os
from datetime import datetime, timedelta
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
import re
import sqlite3
from werkzeug.utils import secure_filename

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "change_this_secret_key")

# Configure upload folder
UPLOAD_FOLDER = os.path.join(os.path.dirname(__file__), 'static', 'uploads')
if not os.path.exists(UPLOAD_FOLDER):
    os.makedirs(UPLOAD_FOLDER)
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024  # 16MB max file size

# Custom Jinja2 filter to remove HTML tags
@app.template_filter('regex_replace')
def regex_replace(s, find, replace):
    """Replace pattern in string using regex"""
    return re.sub(find, replace, str(s))

@app.template_filter('striptags')
def striptags(s):
    """Remove all HTML tags from string"""
    return re.sub('<[^>]+>', '', str(s)).strip()

# Local credentials file (admin can set via /admin/settings)
LOCAL_CONFIG_FILE = "local_config.json"

def load_local_config():
    if os.path.exists(LOCAL_CONFIG_FILE):
        try:
            with open(LOCAL_CONFIG_FILE, 'r') as f:
                return json.load(f)
        except Exception:
            return {}
    return {}

def save_local_config(cfg: dict):
    try:
        with open(LOCAL_CONFIG_FILE, 'w') as f:
            json.dump(cfg, f, indent=2)
        return True
    except Exception:
        return False

def get_smtp_credentials():
    # Prefer environment variables, fall back to local config file
    sender_email = os.environ.get('SENDER_EMAIL') or os.environ.get('SMTP_EMAIL')
    sender_password = os.environ.get('SENDER_PASSWORD') or os.environ.get('SMTP_PASSWORD')
    smtp_server = os.environ.get('SMTP_SERVER')
    smtp_port = os.environ.get('SMTP_PORT')
    if not (sender_email and sender_password):
        cfg = load_local_config()
        sender_email = sender_email or cfg.get('SENDER_EMAIL') or cfg.get('SMTP_EMAIL')
        sender_password = sender_password or cfg.get('SENDER_PASSWORD') or cfg.get('SMTP_PASSWORD')
        smtp_server = smtp_server or cfg.get('SMTP_SERVER')
        smtp_port = smtp_port or cfg.get('SMTP_PORT')
    return sender_email, sender_password, smtp_server, smtp_port

def get_twilio_credentials():
    sid = os.environ.get('TWILIO_SID')
    token = os.environ.get('TWILIO_TOKEN')
    from_no = os.environ.get('TWILIO_FROM')
    if not (sid and token and from_no):
        cfg = load_local_config()
        sid = sid or cfg.get('TWILIO_SID')
        token = token or cfg.get('TWILIO_TOKEN')
        from_no = from_no or cfg.get('TWILIO_FROM')
    return sid, token, from_no

# Customer data storage file
CUSTOMERS_FILE = "customers_data.json"

def load_customers():
    """Load customers from JSON file"""
    if os.path.exists(CUSTOMERS_FILE):
        with open(CUSTOMERS_FILE, 'r') as f:
            return json.load(f)
    return []

def save_customers(customers):
    """Save customers to JSON file"""
    with open(CUSTOMERS_FILE, 'w') as f:
        json.dump(customers, f, indent=2)

def log_email_to_customer(customer_id, subject, body, status="sent"):
    """Log an email to a customer's email history"""
    try:
        customers = load_customers()
        customer = next((c for c in customers if c["id"] == customer_id), None)
        
        if not customer:
            return False
        
        # Initialize email_history if it doesn't exist
        if "email_history" not in customer:
            customer["email_history"] = []
        
        # Add the email record
        email_record = {
            "timestamp": datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
            "subject": subject,
            "body": body[:500] if len(body) > 500 else body,  # Store first 500 chars of body
            "status": status
        }
        
        customer["email_history"].append(email_record)
        save_customers(customers)
        return True
    except Exception as e:
        print(f"Error logging email: {e}")
        return False

def send_email(email, name, subject_or_product, amount_or_message, order_id=None, from_email=None, customer_id=None):
    """Send email to customer - handles both order confirmation and custom messages
    from_email: optional specific sender address (uses same app password)"""
    try:
        # Email configuration (env vars preferred, then local config)
        sender_email, sender_password, smtp_server, smtp_port = get_smtp_credentials()
        smtp_server = smtp_server or 'smtp.gmail.com'
        try:
            smtp_port = int(smtp_port) if smtp_port else 465
        except Exception:
            smtp_port = 465

        # Use provided from_email or fall back to configured sender_email
        display_from_email = from_email or sender_email
        if isinstance(amount_or_message, str) and (len(amount_or_message) > 100 or '<' in amount_or_message):
            subject = subject_or_product
            body = f"""
            <html>
                <body style="font-family: Arial, sans-serif; line-height: 1.6; color: #333;">
                    <h2>Message from Mobile Shop</h2>
                    <p>Dear <strong>{name}</strong>,</p>
                    {amount_or_message}
                    <br><br>
                    <p>If you have any questions, feel free to contact us at:</p>
                    <p><strong>Email:</strong> {BUSINESS_CONFIG.get('email')}</p>
                    <p><strong>Phone:</strong> {BUSINESS_CONFIG.get('phone')}</p>
                    <br>
                    <p><strong>{BUSINESS_CONFIG.get('name')}</strong></p>
                </body>
            </html>
            """
        else:
            subject = f"Order Confirmation #{order_id}"
            body = f"""
            <html>
                <body style="font-family: Arial, sans-serif;">
                    <h2>Order Confirmation</h2>
                    <p>Dear <strong>{name}</strong>,</p>
                    <p>Thank you for your order!</p>
                    <h3>Order Details:</h3>
                    <ul>
                        <li><strong>Order ID:</strong> {order_id}</li>
                        <li><strong>Product:</strong> {subject_or_product}</li>
                        <li><strong>Amount:</strong> ₹{amount_or_message}</li>
                        <li><strong>Date:</strong> {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}</li>
                    </ul>
                    <p>We will process your order shortly and send you a tracking update.</p>
                    <p>If you have any questions, feel free to contact us at:</p>
                    <p><strong>Email:</strong> {BUSINESS_CONFIG.get('email')}</p>
                    <p><strong>Phone:</strong> {BUSINESS_CONFIG.get('phone')}</p>
                    <br>
                    <p>Thank you for choosing us!</p>
                    <p><strong>{BUSINESS_CONFIG.get('name')}</strong></p>
                </body>
            </html>
            """

        # Create email message
        msg = MIMEMultipart()
        msg['From'] = display_from_email if display_from_email else BUSINESS_CONFIG.get('email')
        msg['To'] = email
        msg['Subject'] = subject
        msg.attach(MIMEText(body, 'html'))

        # If credentials provided, attempt to send
        if sender_email and sender_password:
            try:
                server = smtplib.SMTP_SSL(smtp_server, smtp_port, timeout=10)
                server.login(sender_email, sender_password)
                server.send_message(msg)
                server.quit()
                print(f"Email sent to {email}: {subject}")
                # Log email to customer history if customer_id provided
                if customer_id:
                    log_email_to_customer(customer_id, subject, body, "sent")
                return True
            except Exception as e:
                print(f"SMTP send error: {e}")
                # Log the email locally instead of failing
                print(f"Email delivery failed, but customer notification logged for {email}")
                # Log failed email attempt
                if customer_id:
                    log_email_to_customer(customer_id, subject, body, "failed")
                return True  # Return True so customer operations continue
        else:
            # Credentials not configured; log and continue
            print(f"SMTP credentials not configured. Email notification for {email} not sent but customer record saved.")
            # Log as pending
            if customer_id:
                log_email_to_customer(customer_id, subject, body, "pending")
            return True  # Return True so customer operations continue
    except Exception as e:
        print(f"Email error: {e}")
        # Log error
        if customer_id:
            log_email_to_customer(customer_id, "Error", str(e), "error")
        return True  # Return True to allow operations to continue

def send_sms(phone_number, message):
    """Send SMS to customer via Twilio"""
    try:
        # Clean and validate phone number
        if not phone_number:
            print("ERROR: Phone number is empty")
            return False
        
        phone_number = str(phone_number).strip()
        
        # Get Twilio credentials
        tw_sid, tw_token, tw_from = get_twilio_credentials()
        
        if not (tw_sid and tw_token and tw_from):
            print("ERROR: Twilio credentials not configured")
            print(f"  SID: {tw_sid}")
            print(f"  Token: {tw_token}")
            print(f"  From: {tw_from}")
            return False
        
        # Remove all non-digit characters except leading +
        import re
        if phone_number.startswith('+'):
            # Keep the + and digits
            phone_digits = '+' + re.sub(r'[^\d]', '', phone_number)
        else:
            # Just digits
            phone_digits = re.sub(r'[^\d]', '', phone_number)
        
        # Normalize phone number
        print(f"DEBUG: Original phone: {phone_number}")
        print(f"DEBUG: Extracted digits: {phone_digits}")
        
        if phone_digits.startswith('+'):
            # Has country code already
            phone_normalized = phone_digits
        elif len(phone_digits) == 10:
            # 10 digits = Indian number without country code
            phone_normalized = '+91' + phone_digits
        elif len(phone_digits) == 12 and phone_digits.startswith('91'):
            # 12 digits starting with 91 (Indian with country code, no +)
            phone_normalized = '+' + phone_digits
        elif len(phone_digits) == 11 and phone_digits.startswith('91'):
            # 11 digits starting with 91 (might be wrong format)
            # Take last 10 digits and add +91
            phone_normalized = '+91' + phone_digits[-10:]
        elif len(phone_digits) == 12:
            # 12 digits - assume last 10 are the phone number
            phone_normalized = '+91' + phone_digits[-10:]
        elif len(phone_digits) > 12:
            # Too many digits - take last 10
            phone_normalized = '+91' + phone_digits[-10:]
        else:
            # Default: add +91
            phone_normalized = '+91' + phone_digits.lstrip('0')[-10:]
        
        print(f"DEBUG: Normalized phone: {phone_normalized}")
        print(f"DEBUG: From number: {tw_from}")
        print(f"DEBUG: Message: {message[:50]}...")
        
        try:
            from twilio.rest import Client
            client = Client(tw_sid, tw_token)
            
            # Clean the "from" number (Twilio expects digits or E.164 format)
            from_clean = re.sub(r'[^\d+]', '', str(tw_from))
            if not from_clean.startswith('+') and len(from_clean) == 10:
                from_clean = '+91' + from_clean
            elif not from_clean.startswith('+') and len(from_clean) > 10:
                from_clean = '+91' + from_clean[-10:]
            
            print(f"DEBUG: From number cleaned: {from_clean}")
            
            msg = client.messages.create(
                body=message,
                from_=from_clean,  # Use cleaned "from" number
                to=phone_normalized
            )
            print(f"✓ SMS SENT to {phone_normalized}, SID: {msg.sid}")
            return True
        except ImportError as ie:
            print(f"ERROR: Twilio library not installed. Run: pip install twilio")
            print(f"Details: {ie}")
            return False
        except Exception as e:
            error_str = str(e)
            print(f"ERROR: Twilio API error: {error_str}")
            print(f"  Phone: {phone_normalized}")
            print(f"  From: {from_clean if 'from_clean' in locals() else tw_from}")
            print(f"  Message length: {len(message)}")
            
            # If it's an invalid phone number error, try to fix it
            if '21614' in error_str or 'not a valid' in error_str.lower():
                print(f"  Trying alternate format...")
                # Try just the last 10 digits with +91
                try:
                    digits_only = re.sub(r'[^\d]', '', phone_number)
                    alt_phone = '+91' + digits_only[-10:]
                    print(f"  Retry with: {alt_phone}")
                    msg = client.messages.create(
                        body=message,
                        from_=from_clean if 'from_clean' in locals() else tw_from,
                        to=alt_phone
                    )
                    print(f"✓ SMS SENT (retry) to {alt_phone}, SID: {msg.sid}")
                    return True
                except Exception as retry_error:
                    print(f"  Retry failed: {retry_error}")
                    return False
            return False
    except Exception as e:
        print(f"ERROR: Unexpected error in send_sms: {str(e)}")
        import traceback
        traceback.print_exc()
        return False
        import traceback
        traceback.print_exc()
        return False

# ====================
# BUSINESS CONFIGURATION - UPDATE THESE WITH YOUR DETAILS
# ====================
# Replace the placeholder values below with your actual business information
# This information will be displayed as the payment recipient throughout the app
BUSINESS_CONFIG = {
    "name": "mobile sales and accessories", # 👈 UPDATE: Your actual business name
    "gst_number": "22AAAAA0000A1Z5",         # 👈 UPDATE: Your GST number (15 digits)
    "upi_id": os.environ.get("SHOP_UPI_ID", "yourname@upi"),   # 👈 UPDATE: Your UPI ID
    "phone": os.environ.get("SHOP_PHONE", "9876543210"),   # 👈 UPDATE: Your contact number
    "email": os.environ.get("SHOP_EMAIL", "shop@example.com"),   # 👈 UPDATE: Your email address
    "address": "karaikudi",                 # 👈 UPDATE: Your business address
    "tagline": "All payments received by Your Business"  # 👈 UPDATE: Custom tagline
}

# Dummy admin credentials
ADMIN_USERNAME = os.environ.get("ADMIN_USER", "admin")
ADMIN_PASSWORD = os.environ.get("ADMIN_PASSWORD", "admin123")

# Product data storage file
PRODUCTS_FILE = "products_catalog.json"

def load_products():
    """Load products from JSON file"""
    if os.path.exists(PRODUCTS_FILE):
        try:
            with open(PRODUCTS_FILE, 'r') as f:
                return json.load(f)
        except Exception:
            return []
    return []

def save_products(products):
    """Save products to JSON file"""
    try:
        with open(PRODUCTS_FILE, 'w') as f:
            json.dump(products, f, indent=2)
        return True
    except Exception:
        return False

# Dummy product list
products_data = []

# -----------------------
# Login Page - User Login
# -----------------------
@app.route("/", methods=["GET", "POST"])
def login_page():
    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "").strip()
        
        # Validate user credentials
        if username == "user" and password == "user123":
            return redirect(url_for("dashboard"))
        else:
            return render_template("/login.html", error="Invalid username or password", business=BUSINESS_CONFIG)
    return render_template("login.html", business=BUSINESS_CONFIG)

# -----------------------
# Admin Login Page
# -----------------------
@app.route("/admin/login", methods=["GET", "POST"])
def admin_login():
    if request.method == "POST":
        username = request.form.get("username")
        password = request.form.get("password")
        if username == ADMIN_USERNAME and password == ADMIN_PASSWORD:
            return redirect(url_for("admin_customers"))
        return render_template("admin_login.html", error="Invalid credentials", business=BUSINESS_CONFIG)
    return render_template("admin_login.html", business=BUSINESS_CONFIG)

# -----------------------
# Dashboard
# -----------------------
@app.route("/dashboard")
def dashboard():
    order_success = request.args.get("order_success", "false")
    payment_method = request.args.get("payment_method", "")
    return render_template("dashboard.html", 
                         total_products=len(products_data), 
                         order_success=order_success, 
                         payment_method=payment_method,
                         business=BUSINESS_CONFIG)

# -----------------------
# My Purchases (User View)
# -----------------------
@app.route("/my_purchases")
def my_purchases():
    """Display all purchases made by the user (customer)"""
    customers = load_customers()
    
    # Group purchases by order ID and display them
    purchases = []
    for customer in customers:
        purchases.append({
            "order_id": customer.get("id"),
            "name": customer.get("name"),
            "email": customer.get("email"),
            "mobile": customer.get("mobile"),
            "product": customer.get("product"),
            "amount": customer.get("amount"),
            "date": customer.get("date"),
            "status": customer.get("status"),
            "address": customer.get("address")
        })
    
    # Sort by date (newest first)
    purchases = sorted(purchases, key=lambda x: x.get("date", ""), reverse=True)
    
    return render_template("my_purchases.html", purchases=purchases, business=BUSINESS_CONFIG)

# -----------------------
# Add Mobile Page
# -----------------------
@app.route("/add_mobile", methods=["GET", "POST"])
def add_mobile():
    customers = load_customers()
    
    if request.method == "POST":
        new_product = {
            "id": len(products_data) + 1,
            "product_type": request.form.get("product_type"),
            "brand": request.form.get("brand"),
            "model": request.form.get("model"),
            "price": int(request.form.get("price", 0)),
            "quantity": int(request.form.get("quantity", 1)),
            "ram": request.form.get("ram"),
            "rom": request.form.get("rom"),
            "charger_hour": request.form.get("charger_hour"),
            "quality": request.form.get("quality"),
            "features": request.form.get("features"),
            "capacity": request.form.get("capacity"),
            "card_type": request.form.get("card_type"),
            "speed_class": request.form.get("speed_class"),
            "warranty": request.form.get("warranty")
        }
        products_data.append(new_product)
        if request.form.get("action") == "save":
            return redirect(url_for("reports"))
        elif request.form.get("action") == "buy":
            # Redirect to customer details page with selected product info
            return redirect(url_for("customer_details", product=new_product.get('model', ''), amount=new_product.get('price', 0)))


    # If redirected from "Pay Now"
    product_type = request.args.get("type", "")
    model = request.args.get("model", "")
    price = request.args.get("price", "")
    ram = request.args.get("ram", "")
    rom = request.args.get("rom", "")
    charger_hour = request.args.get("charger_hour", "")
    quality = request.args.get("quality", "")
    capacity = request.args.get("capacity", "")
    card_type = request.args.get("card_type", "")
    speed_class = request.args.get("speed_class", "")
    warranty = request.args.get("warranty", "")
    product = {"type": product_type, "model": model, "price": price, "ram": ram, "rom": rom, "charger_hour": charger_hour, "quality": quality, "capacity": capacity, "card_type": card_type, "speed_class": speed_class, "warranty": warranty}
    return render_template("add_mobile.html", product=product, customers=customers)

# -----------------------
# Sales/Update Product
# -----------------------
@app.route("/sales")
def sales():
    return render_template("sales.html", products=products_data)

# -----------------------
# -----------------------
# View Products
# -----------------------
@app.route("/view_mobiles")
def view_mobiles():
    return render_template("view_mobiles.html", products=products_data)

# -----------------------
# Delete Product
# -----------------------
@app.route("/delete_product/<int:product_id>", methods=["GET", "POST"])
def delete_product(product_id):
    product = next((p for p in products_data if p["id"] == product_id), None)
    if not product:
        return "Product not found", 404
    if request.method == "POST":
        products_data.remove(product)
        return redirect(url_for("view_mobiles"))
    return render_template("delete_product.html", product=product)

# -----------------------
# Customer Details
# -----------------------
@app.route("/customer_details", methods=["GET", "POST"])
def customer_details():
    if request.method == "POST":
        order_id = f"ORD{random.randint(10000, 99999)}"
        customer = {
            "id": order_id,
            "name": request.form.get("customer_name"),
            "mobile": request.form.get("mobile"),
            "email": request.form.get("email"),
            "address": request.form.get("address"),
            "product": request.form.get("product_name", ""),
            "amount": request.form.get("amount", "0"),
            "date": datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
            "status": "Pending"
        }
        
        # Save customer to file
        customers = load_customers()
        customers.append(customer)
        save_customers(customers)
        
        # Send email notification
        send_email(customer["email"], customer["name"], customer["product"], customer["amount"], order_id, customer_id=order_id)
        
        # Redirect to payment page
        return render_template("payment.html", customer=customer, business=BUSINESS_CONFIG)
    # If redirected with product info (from /add_mobile buy flow), prefill the form
    product_name = request.args.get('product') or request.args.get('product_name') or ''
    amount = request.args.get('amount') or request.args.get('price') or ''
    image = request.args.get('image', '')
    return render_template("userdetails.html", product_name=product_name, amount=amount, image=image)

# -----------------------
# Confirm Payment
# -----------------------
@app.route("/confirm_payment", methods=["POST"])
def confirm_payment():
    customer = {
        "name": request.form.get("name"),
        "email": request.form.get("email"),
        "phone": request.form.get("phone"),
        "address": request.form.get("address")
    }
    payment_method = request.form.get("payment_method")
    
    # Here you could process the payment and save order to database
    # For now, we'll redirect to dashboard with success message
    return redirect(url_for("dashboard", order_success="true", payment_method=payment_method))

# -----------------------
# Online Payment
# -----------------------
@app.route("/online_payment")
def online_payment():
    customer = {
        "name": request.args.get("name"),
        "email": request.args.get("email"),
        "phone": request.args.get("phone")
    }
    payment_method = request.args.get("payment_method")
    total_amount = request.args.get("total_amount", "1299")  # Default amount
    
    return render_template("online_payment.html", 
                         customer=customer, 
                         payment_method=payment_method,
                         total_amount=total_amount,
                         business=BUSINESS_CONFIG)

# -----------------------
# Payment Success
# -----------------------
@app.route("/payment_success")
def payment_success():
    payment_method = request.args.get("method", "Online")
    amount = request.args.get("amount", "1299")
    order_number = f"ORD{random.randint(1000, 9999)}"
    current_date = datetime.now().strftime("%B %d, %Y")
    transaction_id = f"TXN{random.randint(100000000, 999999999)}"
    
    # Store payment record to file
    try:
        payment_record = {
            "order_number": order_number,
            "payment_method": payment_method,
            "amount": amount,
            "transaction_id": transaction_id,
            "date": current_date,
            "timestamp": datetime.now().isoformat(),
            "status": "Completed"
        }
        
        # Load existing payments
        payments_file = "online_payments.json"
        if os.path.exists(payments_file):
            with open(payments_file, 'r') as f:
                payments = json.load(f)
        else:
            payments = []
        
        # Add new payment
        payments.append(payment_record)
        
        # Save updated payments
        with open(payments_file, 'w') as f:
            json.dump(payments, f, indent=2)
    except Exception as e:
        print(f"Error saving payment record: {e}")
    
    return render_template("payment_success.html",
                         payment_method=payment_method,
                         amount=amount,
                         order_number=order_number,
                         current_date=current_date,
                         transaction_id=transaction_id,
                         business=BUSINESS_CONFIG)

# -----------------------
# Logout
# -----------------------
@app.route("/logout")
def logout():
    return redirect(url_for("login_page"))

# -----------------------
# Admin - Customer Management
# -----------------------
@app.route("/admin/customers")
def admin_customers():
    customers = load_customers()
    return render_template("admin_customers.html", customers=customers, business=BUSINESS_CONFIG)

@app.route("/admin/online-payments")
def admin_online_payments():
    """Display all online payments"""
    try:
        payments_file = "online_payments.json"
        if os.path.exists(payments_file):
            with open(payments_file, 'r') as f:
                payments = json.load(f)
        else:
            payments = []
        
        # Sort by timestamp (newest first)
        payments.sort(key=lambda x: x.get('timestamp', ''), reverse=True)
        
        return render_template("admin_online_payments.html", 
                             payments=payments, 
                             business=BUSINESS_CONFIG)
    except Exception as e:
        print(f"Error loading payments: {e}")
        return render_template("admin_online_payments.html", 
                             payments=[], 
                             business=BUSINESS_CONFIG)

@app.route("/admin/sales")
def admin_sales():
    """Display all purchases/sales"""
    customers = load_customers()
    
    # Create sales list from all orders
    sales = []
    for customer in customers:
        sales.append({
            "order_id": customer["id"],
            "customer_name": customer["name"],
            "email": customer["email"],
            "phone": customer["mobile"],
            "product_name": customer["product"],
            "amount": customer["amount"],
            "status": customer["status"],
            "date": customer["date"],
            "address": customer.get("address", "")
        })
    
    # Sort by date (newest first)
    sales = sorted(sales, key=lambda x: x["date"], reverse=True)
    
    # Calculate sales statistics
    total_sales = len(sales)
    total_revenue = sum(int(s["amount"]) for s in sales if s["amount"])
    completed_sales = sum(1 for s in sales if s["status"] == "Completed")
    pending_sales = sum(1 for s in sales if s["status"] == "Pending")
    
    sales_data = {
        "total_sales": total_sales,
        "total_revenue": total_revenue,
        "completed_sales": completed_sales,
        "pending_sales": pending_sales,
        "sales": sales
    }
    
    return render_template("sales.html", sales=sales_data, business=BUSINESS_CONFIG)


@app.route("/admin/user-purchases")
def admin_user_purchases():
    """Display all user purchases"""
    customers = load_customers()
    
    # Create purchases list from all customer orders
    purchases = []
    for customer in customers:
        purchases.append({
            "username": customer["name"],
            "product_name": customer["product"],
            "price": customer["amount"],
            "quantity": 1,
            "purchase_date": customer["date"]
        })
    
    # Sort by date (newest first)
    purchases = sorted(purchases, key=lambda x: x["purchase_date"], reverse=True)
    
    return render_template("userss.html", purchases=purchases, business=BUSINESS_CONFIG)


@app.route("/admin/purchase-emails")
def admin_purchase_emails():
    """Display email list of all customers who made purchases"""
    customers = load_customers()
    
    # Extract email list from all customers who have made purchases
    email_list = []
    for customer in customers:
        if customer.get("email"):  # Only include customers with email
            email_list.append({
                "name": customer.get("name"),
                "email": customer.get("email"),
                "mobile": customer.get("mobile"),
                "product": customer.get("product"),
                "amount": customer.get("amount"),
                "purchase_date": customer.get("date"),
                "order_id": customer.get("id")
            })
    
    # Sort by purchase date (newest first)
    email_list = sorted(email_list, key=lambda x: x["purchase_date"], reverse=True)
    
    # Extract just emails for easy copying/export
    emails_only = [item["email"] for item in email_list]
    emails_comma_separated = ", ".join(emails_only)
    
    return render_template("purchase_emails.html", 
                         email_list=email_list, 
                         emails_comma_separated=emails_comma_separated,
                         total_emails=len(emails_only),
                         business=BUSINESS_CONFIG)


@app.route("/admin/reports", methods=["GET"])
@app.route("/reports", methods=["GET"])
def reports():
    """Display comprehensive email and sales reports"""
    customers = load_customers()
    
    # Initialize report data
    report = {
        "total_emails": 0,
        "sent_emails": 0,
        "pending_emails": 0,
        "failed_emails": 0,
        "error_emails": 0,
        "total_customers": len(customers),
        "total_revenue": 0,
        "completed_orders": 0,
        "pending_orders": 0,
        "cancelled_orders": 0,
        "email_stats_by_customer": []
    }
    
    # Calculate email statistics from customer email_history
    for customer in customers:
        email_history = customer.get("email_history", [])
        customer_stats = {
            "customer_id": customer["id"],
            "customer_name": customer["name"],
            "email": customer["email"],
            "total": len(email_history),
            "sent": 0,
            "pending": 0,
            "failed": 0,
            "error": 0
        }
        
        # Count email statuses
        for email_record in email_history:
            status = email_record.get("status", "pending")
            if status.lower() == "sent":
                customer_stats["sent"] += 1
                report["sent_emails"] += 1
            elif status.lower() == "pending":
                customer_stats["pending"] += 1
                report["pending_emails"] += 1
            elif status.lower() == "failed":
                customer_stats["failed"] += 1
                report["failed_emails"] += 1
            elif status.lower() == "error":
                customer_stats["error"] += 1
                report["error_emails"] += 1
            
            report["total_emails"] += 1
        
        if customer_stats["total"] > 0:
            report["email_stats_by_customer"].append(customer_stats)
        
        # Calculate order statistics
        amount = customer.get("amount", 0)
        try:
            report["total_revenue"] += int(amount)
        except:
            pass
        
        status = customer.get("status", "Pending")
        if status == "Completed":
            report["completed_orders"] += 1
        elif status == "Pending":
            report["pending_orders"] += 1
        elif status == "Cancelled":
            report["cancelled_orders"] += 1
    
    return render_template("reports.html", report=report, business=BUSINESS_CONFIG)


@app.route("/admin/send-reports", methods=["POST"])
def send_reports():
    """Send all reports data to admin email"""
    try:
        customers = load_customers()
        admin_email = BUSINESS_CONFIG.get("admin_email", "admin@example.com")
        
        # Generate comprehensive report data
        report = {
            "total_emails": 0,
            "sent_emails": 0,
            "pending_emails": 0,
            "failed_emails": 0,
            "error_emails": 0,
            "total_customers": len(customers),
            "total_revenue": 0,
            "completed_orders": 0,
            "pending_orders": 0,
            "cancelled_orders": 0,
            "email_stats_by_customer": []
        }
        
        # Calculate statistics
        for customer in customers:
            email_history = customer.get("email_history", [])
            
            for email_record in email_history:
                status = email_record.get("status", "pending")
                if status.lower() == "sent":
                    report["sent_emails"] += 1
                elif status.lower() == "pending":
                    report["pending_emails"] += 1
                elif status.lower() == "failed":
                    report["failed_emails"] += 1
                elif status.lower() == "error":
                    report["error_emails"] += 1
                report["total_emails"] += 1
            
            amount = customer.get("amount", 0)
            try:
                report["total_revenue"] += int(amount)
            except:
                pass
            
            status = customer.get("status", "Pending")
            if status == "Completed":
                report["completed_orders"] += 1
            elif status == "Pending":
                report["pending_orders"] += 1
            elif status == "Cancelled":
                report["cancelled_orders"] += 1
        
        # Create detailed email body with HTML
        email_body = f"""
        <html>
        <head>
            <style>
                body {{ font-family: Arial, sans-serif; color: #333; }}
                h1 {{ color: #2563eb; }}
                h2 {{ color: #666; border-bottom: 2px solid #ddd; padding-bottom: 10px; }}
                table {{ width: 100%; border-collapse: collapse; margin: 20px 0; }}
                th {{ background: #f5f5f5; padding: 10px; text-align: left; font-weight: bold; }}
                td {{ padding: 10px; border-bottom: 1px solid #eee; }}
                .stat-box {{ display: inline-block; margin: 10px; padding: 15px; background: #f9f9f9; border-radius: 5px; min-width: 150px; }}
                .stat-number {{ font-size: 24px; font-weight: bold; color: #2563eb; }}
                .stat-label {{ font-size: 12px; color: #666; }}
            </style>
        </head>
        <body>
            <h1>📊 Mobile Accessories Management - Email & Sales Reports</h1>
            <p>Generated on: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}</p>
            
            <h2>📧 Email Statistics</h2>
            <div class="stat-box">
                <div class="stat-number">{report['total_emails']}</div>
                <div class="stat-label">Total Emails</div>
            </div>
            <div class="stat-box">
                <div class="stat-number" style="color: #22c55e;">{report['sent_emails']}</div>
                <div class="stat-label">Emails Sent</div>
            </div>
            <div class="stat-box">
                <div class="stat-number" style="color: #f59e0b;">{report['pending_emails']}</div>
                <div class="stat-label">Pending</div>
            </div>
            <div class="stat-box">
                <div class="stat-number" style="color: #ef4444;">{report['failed_emails']}</div>
                <div class="stat-label">Failed</div>
            </div>
            <div class="stat-box">
                <div class="stat-number" style="color: #8b5cf6;">{report['error_emails']}</div>
                <div class="stat-label">Errors</div>
            </div>
            
            <h2>📦 Sales & Orders</h2>
            <div class="stat-box">
                <div class="stat-number">{report['total_customers']}</div>
                <div class="stat-label">Total Customers</div>
            </div>
            <div class="stat-box">
                <div class="stat-number" style="color: #06b6d4;">₹{report['total_revenue']:,.0f}</div>
                <div class="stat-label">Total Revenue</div>
            </div>
            <div class="stat-box">
                <div class="stat-number" style="color: #22c55e;">{report['completed_orders']}</div>
                <div class="stat-label">Completed Orders</div>
            </div>
            <div class="stat-box">
                <div class="stat-number" style="color: #f59e0b;">{report['pending_orders']}</div>
                <div class="stat-label">Pending Orders</div>
            </div>
            <div class="stat-box">
                <div class="stat-number" style="color: #ef4444;">{report['cancelled_orders']}</div>
                <div class="stat-label">Cancelled Orders</div>
            </div>
            
            <h2>👥 Customer Email History</h2>
            <table>
                <thead>
                    <tr>
                        <th>Customer Name</th>
                        <th>Email</th>
                        <th>Order ID</th>
                        <th>Total Emails</th>
                        <th>Sent ✓</th>
                        <th>Pending ⏳</th>
                        <th>Failed ✗</th>
                        <th>Error 🔴</th>
                    </tr>
                </thead>
                <tbody>
        """
        
        # Add customer statistics
        for stat in report["email_stats_by_customer"]:
            email_body += f"""
                    <tr>
                        <td><strong>{stat['customer_name']}</strong></td>
                        <td>{stat['email']}</td>
                        <td>{stat['customer_id']}</td>
                        <td>{stat['total']}</td>
                        <td style="color: #22c55e; font-weight: bold;">{stat['sent']}</td>
                        <td style="color: #f59e0b; font-weight: bold;">{stat['pending']}</td>
                        <td style="color: #ef4444; font-weight: bold;">{stat['failed']}</td>
                        <td style="color: #8b5cf6; font-weight: bold;">{stat['error']}</td>
                    </tr>
            """
        
        email_body += """
                </tbody>
            </table>
            
            <h2>📝 All Customer Orders</h2>
            <table>
                <thead>
                    <tr>
                        <th>Order ID</th>
                        <th>Customer Name</th>
                        <th>Email</th>
                        <th>Mobile</th>
                        <th>Product</th>
                        <th>Amount (₹)</th>
                        <th>Status</th>
                        <th>Date</th>
                    </tr>
                </thead>
                <tbody>
        """
        
        # Add all customer orders
        for customer in customers:
            email_body += f"""
                    <tr>
                        <td><strong>{customer['id']}</strong></td>
                        <td>{customer['name']}</td>
                        <td>{customer['email']}</td>
                        <td>{customer['mobile']}</td>
                        <td>{customer['product']}</td>
                        <td>₹{customer['amount']}</td>
                        <td><strong>{customer['status']}</strong></td>
                        <td>{customer['date']}</td>
                    </tr>
            """
        
        email_body += """
                </tbody>
            </table>
            
            <hr style="margin: 30px 0;">
            <p style="color: #999; font-size: 12px;">
                This is an automated report from Mobile Accessories Management System.
                Generated on: """ + datetime.now().strftime('%Y-%m-%d %H:%M:%S') + """
            </p>
        </body>
        </html>
        """
        
        # Send email to admin
        success = send_email(
            admin_email,
            "Admin",
            "📊 Mobile Accessories Reports - All Emails & Sales",
            email_body
        )
        
        if success:
            return render_template("reports.html", 
                                 report=report, 
                                 success="✅ Reports sent successfully to admin email!",
                                 business=BUSINESS_CONFIG)
        else:
            return render_template("reports.html", 
                                 report=report, 
                                 error="❌ Failed to send reports. Check email configuration.",
                                 business=BUSINESS_CONFIG)
    except Exception as e:
        print(f"Error sending reports: {e}")
        return render_template("reports.html", 
                             report={},
                             error=f"❌ Error: {str(e)}",
                             business=BUSINESS_CONFIG)


@app.route("/admin/customer/<customer_id>", methods=["GET", "POST"])
def admin_customer_detail(customer_id):
    customers = load_customers()
    customer = next((c for c in customers if c["id"] == customer_id), None)
    
    if not customer:
        return "Customer not found", 404
    
    if request.method == "POST":
        customer["name"] = request.form.get("name")
        customer["mobile"] = request.form.get("mobile")
        customer["email"] = request.form.get("email")
        customer["address"] = request.form.get("address")
        customer["product"] = request.form.get("product")
        customer["amount"] = request.form.get("amount")
        customer["status"] = request.form.get("status")
        
        save_customers(customers)
        return redirect(url_for("admin_customers"))
    
    # Allow status messages from redirects (e.g., from send-message)
    success = request.args.get('success')
    error = request.args.get('error')
    return render_template("admin_customer_detail.html", customer=customer, business=BUSINESS_CONFIG, success=success, error=error)

@app.route("/admin/customer/delete/<customer_id>", methods=["POST"])
def admin_delete_customer(customer_id):
    customers = load_customers()
    customers = [c for c in customers if c["id"] != customer_id]
    save_customers(customers)
    return redirect(url_for("admin_customers"))

# -----------------------
# Send Message to Customer
# -----------------------
@app.route("/admin/send-message/<customer_id>", methods=["GET", "POST"])
def admin_send_message(customer_id):
    customers = load_customers()
    customer = next((c for c in customers if c["id"] == customer_id), None)
    
    if not customer:
        return "Customer not found", 404
    
    if request.method == "POST":
        message_type = request.form.get("message_type")  # email, sms, or whatsapp
        message_subject = request.form.get("subject", "Order Update")
        message_body = request.form.get("message")
        
        if message_type == "email":
            # Send email
            success = send_email(
                customer["email"],
                customer["name"],
                message_subject,
                message_body,
                customer_id=customer_id
            )
            if success:
                return render_template("admin_customer_detail.html", customer=customer, 
                                     success="Email sent successfully!", business=BUSINESS_CONFIG)
            else:
                return render_template("admin_customer_detail.html", customer=customer,
                                     error="Failed to send email", business=BUSINESS_CONFIG)
        
        elif message_type in ["sms", "whatsapp"]:
            # SMS or WhatsApp sending via Twilio (if configured)
            sms_to = customer.get('mobile')
            sms_body = message_body

            # Normalize phone: if no leading +, assume Indian +91 (adjust as needed)
            if sms_to and not sms_to.startswith('+'):
                sms_to_normalized = '+91' + sms_to.lstrip('0')
            else:
                sms_to_normalized = sms_to

            # Attempt to send via Twilio if available; otherwise fall back to email
            try:
                from twilio.rest import Client
                twilio_available = True
            except Exception:
                twilio_available = False

            tw_sid, tw_token, tw_from = get_twilio_credentials()

            if twilio_available and tw_sid and tw_token and tw_from:
                try:
                    client = Client(tw_sid, tw_token)
                    if message_type == "whatsapp":
                        # Send WhatsApp message
                        msg = client.messages.create(
                            body=sms_body,
                            from_=f'whatsapp:{tw_from}',
                            to=f'whatsapp:{sms_to_normalized}'
                        )
                        print(f"WhatsApp sent to {sms_to_normalized}, SID: {msg.sid}")
                        return render_template("admin_customer_detail.html", customer=customer,
                                             success="WhatsApp message sent successfully!", business=BUSINESS_CONFIG)
                    else:
                        # Send SMS message
                        msg = client.messages.create(body=sms_body, from_=tw_from, to=sms_to_normalized)
                        print(f"SMS sent to {sms_to_normalized}, SID: {msg.sid}")
                        return render_template("admin_customer_detail.html", customer=customer,
                                             success="SMS sent successfully!", business=BUSINESS_CONFIG)
                except Exception as e:
                    print(f"{message_type.upper()} send error: {e}")
                    # Attempt email fallback
                    email_sent = send_email(customer.get('email'), customer.get('name', ''), "Message fallback", sms_body)
                    if email_sent:
                        return redirect(url_for('admin_customer_detail', customer_id=customer_id, success=f'{message_type.upper()} failed but message sent via email.'))
                    else:
                        return redirect(url_for('admin_customer_detail', customer_id=customer_id, error=f'Failed to send {message_type}: {e} and email fallback failed.'))
            else:
                # Twilio not available or credentials missing — try email fallback and inform admin
                email_sent = send_email(customer.get('email'), customer.get('name', ''), "Message fallback", sms_body)
                if email_sent:
                    info_msg = f"Twilio not configured; message delivered via email instead."
                    print(info_msg)
                    return redirect(url_for('admin_customer_detail', customer_id=customer_id, success=info_msg))
                else:
                    # Neither Twilio nor SMTP available - show actionable error
                    return redirect(url_for('admin_customer_detail', customer_id=customer_id, error=f'Twilio not configured and email fallback failed. Install `twilio` or set SMTP env vars (SENDER_EMAIL/SENDER_PASSWORD).'))
    
    return render_template("admin_send_message.html", customer=customer, business=BUSINESS_CONFIG)

@app.route("/admin/customer/<customer_id>/email-history", methods=["GET"])
def admin_email_history(customer_id):
    """Display email history for a customer"""
    customers = load_customers()
    customer = next((c for c in customers if c["id"] == customer_id), None)
    
    if not customer:
        return "Customer not found", 404
    
    # Get email history, default to empty list if not present
    email_history = customer.get("email_history", [])
    
    return render_template("admin_email_history.html", customer=customer, email_history=email_history, business=BUSINESS_CONFIG)

@app.route("/admin/customer/add", methods=["GET", "POST"])
def admin_add_customer():
    if request.method == "POST":
        order_id = f"ORD{random.randint(10000, 99999)}"
        customer = {
            "id": order_id,
            "name": request.form.get("name"),
            "mobile": request.form.get("mobile"),
            "email": request.form.get("email"),
            "address": request.form.get("address"),
            "product": request.form.get("product"),
            "amount": request.form.get("amount"),
            "date": datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
            "status": "Pending"
        }
        
        customers = load_customers()
        customers.append(customer)
        save_customers(customers)
        
        return redirect(url_for("admin_customers"))
    
    return render_template("admin_add_customer.html", business=BUSINESS_CONFIG)


@app.route('/admin/settings', methods=['GET', 'POST'])
def admin_settings():
    # Simple admin settings page to store local SMTP/Twilio creds
    cfg = load_local_config()
    if request.method == 'POST':
        action = request.form.get('action', 'save')
        # Collect values
        write_cfg = {
            'SENDER_EMAIL': request.form.get('SENDER_EMAIL') or None,
            'SENDER_PASSWORD': request.form.get('SENDER_PASSWORD') or None,
            'SMTP_SERVER': request.form.get('SMTP_SERVER') or None,
            'SMTP_PORT': request.form.get('SMTP_PORT') or None,
            'TWILIO_SID': request.form.get('TWILIO_SID') or None,
            'TWILIO_TOKEN': request.form.get('TWILIO_TOKEN') or None,
            'TWILIO_FROM': request.form.get('TWILIO_FROM') or None,
            'TEST_EMAIL_TO': request.form.get('TEST_EMAIL_TO') or None,
            'TEST_SMS_TO': request.form.get('TEST_SMS_TO') or None
        }
        # Remove None values
        write_cfg = {k: v for k, v in write_cfg.items() if v}

        # Save settings first (so tests can use them)
        ok = save_local_config(write_cfg)
        if not ok:
            return render_template('admin_settings.html', error='Failed to save settings.', cfg=cfg, business=BUSINESS_CONFIG)

        # Handle clear stored secrets
        if action == 'clear':
            try:
                if os.path.exists(LOCAL_CONFIG_FILE):
                    os.remove(LOCAL_CONFIG_FILE)
            except Exception:
                pass
            return render_template('admin_settings.html', success='Stored secrets cleared.', cfg={}, business=BUSINESS_CONFIG)

        # Handle actions: save | test_email | test_sms
        if action == 'save':
            return render_template('admin_settings.html', success='Settings saved locally.', cfg=write_cfg, business=BUSINESS_CONFIG)

        if action == 'test_email':
            to_addr = write_cfg.get('TEST_EMAIL_TO') or write_cfg.get('SENDER_EMAIL') or BUSINESS_CONFIG.get('email')
            if not to_addr:
                return render_template('admin_settings.html', error='No test email recipient available.', cfg=write_cfg, business=BUSINESS_CONFIG)
            sent = send_email(to_addr, 'Admin', 'Test Email', 'This is a test email from Mobile Shop.')
            if sent:
                return render_template('admin_settings.html', success=f'Test email sent to {to_addr}.', cfg=write_cfg, business=BUSINESS_CONFIG)
            else:
                return render_template('admin_settings.html', error=f'Failed to send test email to {to_addr}. Check SMTP settings.', cfg=write_cfg, business=BUSINESS_CONFIG)

        if action == 'test_sms':
            sms_to = write_cfg.get('TEST_SMS_TO')
            if not sms_to:
                return render_template('admin_settings.html', error='No test SMS recipient provided.', cfg=write_cfg, business=BUSINESS_CONFIG)
            # Normalize phone
            sms_to_norm = sms_to if sms_to.startswith('+') else ('+91' + sms_to.lstrip('0'))
            sms_body = 'This is a test SMS from Mobile Shop.'
            try:
                from twilio.rest import Client
                twilio_av = True
            except Exception:
                twilio_av = False
            sid, token, from_no = get_twilio_credentials()
            if twilio_av and sid and token and from_no:
                try:
                    client = Client(sid, token)
                    msg = client.messages.create(body=sms_body, from_=from_no, to=sms_to_norm)
                    return render_template('admin_settings.html', success=f'Test SMS sent to {sms_to_norm} (SID: {msg.sid}).', cfg=write_cfg, business=BUSINESS_CONFIG)
                except Exception as e:
                    # Try email fallback
                    email_sent = send_email(write_cfg.get('SENDER_EMAIL') or BUSINESS_CONFIG.get('email'), 'Admin', 'SMS Fallback', sms_body)
                    if email_sent:
                        return render_template('admin_settings.html', success=f'Twilio send failed but message sent via email fallback.', cfg=write_cfg, business=BUSINESS_CONFIG)
                    return render_template('admin_settings.html', error=f'Failed to send test SMS: {e}', cfg=write_cfg, business=BUSINESS_CONFIG)
            else:
                return render_template('admin_settings.html', error='Twilio not available or credentials missing. Install `twilio` and set TWILIO_* or configure here.', cfg=write_cfg, business=BUSINESS_CONFIG)
    return render_template('admin_settings.html', cfg=cfg, business=BUSINESS_CONFIG)

# -----------------------
# Product Management
# -----------------------

@app.route("/admin/products", methods=["GET"])
def admin_products():
    """List all products in catalog"""
    products = load_products()
    return render_template("admin_products.html", products=products, business=BUSINESS_CONFIG)

@app.route("/admin/product/add", methods=["GET", "POST"])
def admin_add_product():
    """Add a new product to catalog"""
    if request.method == "POST":
        product_id = f"PRD{random.randint(10000, 99999)}"
        product = {
            "id": product_id,
            "name": request.form.get("product_name"),
            "category": request.form.get("category"),
            "price": request.form.get("price"),
            "description": request.form.get("description"),
            "sku": request.form.get("sku", ""),
            "stock": request.form.get("stock", "0"),
            "date_added": datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        }
        
        products = load_products()
        products.append(product)
        
        if save_products(products):
            return redirect(url_for("admin_products"))
        else:
            return render_template("admin_add_product.html", error="Failed to save product", business=BUSINESS_CONFIG)
    
    return render_template("admin_add_product.html", business=BUSINESS_CONFIG)

@app.route("/admin/product/<product_id>/edit", methods=["GET", "POST"])
def admin_edit_product(product_id):
    """Edit an existing product"""
    products = load_products()
    product = next((p for p in products if p["id"] == product_id), None)
    
    if not product:
        return "Product not found", 404
    
    if request.method == "POST":
        product["name"] = request.form.get("product_name")
        product["category"] = request.form.get("category")
        product["price"] = request.form.get("price")
        product["description"] = request.form.get("description")
        product["sku"] = request.form.get("sku")
        product["stock"] = request.form.get("stock")
        
        if save_products(products):
            return redirect(url_for("admin_products"))
        else:
            return render_template("admin_edit_product.html", product=product, error="Failed to save product", business=BUSINESS_CONFIG)
    
    return render_template("admin_edit_product.html", product=product, business=BUSINESS_CONFIG)

@app.route("/admin/product/<product_id>/delete", methods=["POST"])
def admin_delete_product(product_id):
    """Delete a product from catalog"""
    products = load_products()
    products = [p for p in products if p["id"] != product_id]
    save_products(products)
    return redirect(url_for("admin_products"))

@app.route("/api/products", methods=["GET"])
def api_get_products():
    """API endpoint to get all products (for autofill)"""
    products = load_products()
    return {"products": products}

@app.route("/api/product/<product_id>", methods=["GET"])
def api_get_product(product_id):
    """API endpoint to get a single product (for autofill)"""
    products = load_products()
    product = next((p for p in products if p["id"] == product_id), None)
    if product:
        return {"product": product}
    return {"error": "Product not found"}, 404

@app.route("/api/customers", methods=["GET"])
def api_get_customers():
    """API endpoint to get all customers (for bulk operations)"""
    customers = load_customers()
    return {"customers": customers}

@app.route("/admin/send-product-email/<product_id>", methods=["GET", "POST"])
def admin_send_product_email(product_id):
    """Send email to customers about a specific product"""
    products = load_products()
    product = next((p for p in products if p["id"] == product_id), None)
    
    if not product:
        return "Product not found", 404
    
    if request.method == "POST":
        # Get form data
        email_subject = request.form.get("subject", f"Check out our new product: {product['name']}")
        email_body = request.form.get("body", f"<p>We have a new product available: <strong>{product['name']}</strong></p><p>Price: ₹{product['price']}</p>")
        recipient_filter = request.form.get("recipient_filter", "all")  # all, recent, custom
        custom_emails = request.form.get("custom_emails", "").strip()
        
        # Determine recipients
        customers = load_customers()
        recipients = []
        
        if recipient_filter == "all":
            # Send to all customers
            recipients = [c for c in customers if c.get("email")]
        elif recipient_filter == "recent":
            # Send to customers from last 30 days
            cutoff_date = datetime.now() - timedelta(days=30)
            recipients = [c for c in customers if c.get("email") and 
                         datetime.strptime(c.get("date", ""), '%Y-%m-%d %H:%M:%S') > cutoff_date]
        elif recipient_filter == "custom" and custom_emails:
            # Send to custom email list
            email_list = [e.strip() for e in custom_emails.split(',') if e.strip()]
            recipients = [c for c in customers if c.get("email") in email_list]
        
        # Send emails
        sent_count = 0
        failed_count = 0
        
        for customer in recipients:
            try:
                success = send_email(
                    customer["email"],
                    customer["name"],
                    email_subject,
                    email_body,
                    customer_id=customer["id"]
                )
                if success:
                    sent_count += 1
                else:
                    failed_count += 1
            except Exception as e:
                print(f"Error sending email to {customer['email']}: {e}")
                failed_count += 1
        
        return render_template("admin_send_product_email.html", 
                             product=product,
                             success=f"✓ Emails sent successfully! Sent: {sent_count}, Failed: {failed_count}",
                             business=BUSINESS_CONFIG)
    
    return render_template("admin_send_product_email.html", product=product, business=BUSINESS_CONFIG)

# -----------------------
# Misc Pages
# -----------------------

@app.route('/phonep')
def phonep():
    return render_template('phonep.html')

@app.route('/watches')
def watches():
    return render_template('watches.html')

@app.route('/powerbank')
def powerbank():
    return render_template('powerbank.html')

@app.route('/case')
def case():
    return render_template('case.html')

@app.route('/feedback')
def feedback():
    order_id = request.args.get('order_id', '')
    return render_template('feedback.html', order_id=order_id)

@app.route('/charger')
def charger():
    return render_template('charger.html')

# =====================
# BULK SMS SENDING ROUTE
# =====================
@app.route('/admin/send-bulk-sms', methods=['GET', 'POST'])
def send_bulk_sms():
    """Send SMS to multiple customers at once"""
    if request.method == 'POST':
        customers = load_customers()
        phone_numbers = request.form.get('phone_numbers', '').strip().split('\n')
        message = request.form.get('message', '').strip()
        
        if not message:
            return render_template('admin_bulk_sms.html', error='Message cannot be empty', business=BUSINESS_CONFIG)
        
        if not phone_numbers or (len(phone_numbers) == 1 and not phone_numbers[0].strip()):
            return render_template('admin_bulk_sms.html', error='Please enter at least one phone number', business=BUSINESS_CONFIG)
        
        sent_count = 0
        failed_count = 0
        results = []
        
        print("\n" + "="*60)
        print(f"STARTING BULK SMS SEND - {len(phone_numbers)} numbers")
        print("="*60)
        
        for idx, phone in enumerate(phone_numbers, 1):
            phone = phone.strip()
            if not phone:
                continue
            
            print(f"\n[{idx}] Processing: {phone}")
            success = send_sms(phone, message)
            if success:
                sent_count += 1
                results.append({'phone': phone, 'status': 'Sent ✓', 'icon': '✓'})
                print(f"[{idx}] ✓ SUCCESS")
            else:
                failed_count += 1
                results.append({'phone': phone, 'status': 'Failed ✗', 'icon': '✗'})
                print(f"[{idx}] ✗ FAILED")
        
        print("\n" + "="*60)
        print(f"BULK SMS COMPLETE - Sent: {sent_count}, Failed: {failed_count}")
        print("="*60 + "\n")
        
        return render_template('admin_bulk_sms.html', 
                             results=results,
                             sent_count=sent_count,
                             failed_count=failed_count,
                             success=f"SMS processing complete! Sent: {sent_count} ✓ | Failed: {failed_count} ✗",
                             business=BUSINESS_CONFIG)
    
    # GET request - show form with customer list
    customers = load_customers()
    return render_template('admin_bulk_sms.html', customers=customers, business=BUSINESS_CONFIG)


# Single SMS to specific number route (for quick SMS sending)
@app.route('/admin/send-sms', methods=['POST'])
def send_sms_route():
    """Quick SMS sending endpoint"""
    try:
        phone = request.form.get('phone', '').strip()
        message = request.form.get('message', '').strip()
        
        if not phone:
            return {'success': False, 'message': 'Phone number is required'}, 400
        if not message:
            return {'success': False, 'message': 'Message is required'}, 400
        
        print(f"\nDirect SMS Request: {phone}")
        success = send_sms(phone, message)
        
        if success:
            return {'success': True, 'message': 'SMS sent successfully!'}
        else:
            return {'success': False, 'message': 'Failed to send SMS. Check console logs for details.'}, 500
    except Exception as e:
        print(f"ERROR in send_sms_route: {str(e)}")
        import traceback
        traceback.print_exc()
        return {'success': False, 'message': f'Error: {str(e)}'}, 500

# -----------------------
# PRODUCT CATEGORY ROUTES
# -----------------------

@app.route('/memorycard')
def memorycard():
    return render_template('memorycard.html')

@app.route('/wirelesse')
def wirelesse():
    return render_template('wirelesse.html')

@app.route('/tempor')
def tempor():
    return render_template('tempor.html')

@app.route('/viewmail')
def viewmail():
    return render_template('viewmail.html')

@app.route("/feedback_success")
def feedback_success():
    return render_template("feedback_success.html")

@app.route('/view_feedback')
def view_feedback():
    try:
        order_id = request.args.get('order_id', '')
        conn = sqlite3.connect("feedback.db")
        cursor = conn.cursor()

        # Create table if not exists (base schema)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS feedbacks (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT,
                feedback TEXT,
                rating INTEGER DEFAULT 5,
                comment TEXT,
                images TEXT,
                date TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)

        # Ensure optional column `order_id` exists (migrate older DBs)
        try:
            cursor.execute("PRAGMA table_info(feedbacks)")
            cols = [r[1] for r in cursor.fetchall()]
            if 'order_id' not in cols:
                cursor.execute("ALTER TABLE feedbacks ADD COLUMN order_id TEXT")
                conn.commit()
        except Exception:
            # ignore migration errors
            pass
        
        # Fetch feedbacks for specific order or all
        if order_id:
            cursor.execute("SELECT id, order_id, name, feedback, rating, comment, date FROM feedbacks WHERE order_id = ? ORDER BY date DESC", (order_id,))
        else:
            cursor.execute("SELECT id, order_id, name, feedback, rating, comment, date FROM feedbacks ORDER BY date DESC")
        
        feedbacks = cursor.fetchall()
        conn.close()
        
        # Convert to list of dictionaries
        feedback_list = []
        for fb in feedbacks:
            feedback_list.append({
                'id': fb[0],
                'order_id': fb[1],
                'name': fb[2],
                'feedback': fb[3],
                'rating': fb[4] if fb[4] else 5,
                'comment': fb[5] if fb[5] else fb[3],
                'date': fb[6] if fb[6] else 'Unknown'
            })
        
        return render_template('view_feedback.html', feedbacks=feedback_list, order_id=order_id)
    except Exception as e:
        print(f"Error fetching feedback: {e}")
        return render_template('view_feedback.html', feedbacks=[], order_id='')


@app.route('/submit_feedback', methods=['POST'])
def submit_feedback():
    try:
        order_id = request.form.get('order_id', '')
        name = request.form.get('name', '') or 'Anonymous'
        rating = request.form.get('rating', '5')
        comment = request.form.get('comment', '')
        
        # Connect to SQLite database
        conn = sqlite3.connect("feedback.db")
        cursor = conn.cursor()
        
        # Create table if not exists with order_id
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS feedbacks (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                order_id TEXT,
                name TEXT NOT NULL,
                feedback TEXT,
                rating INTEGER DEFAULT 5,
                comment TEXT,
                date TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        
        # Insert feedback
        cursor.execute("""
            INSERT INTO feedbacks (order_id, name, feedback, rating, comment) 
            VALUES (?, ?, ?, ?, ?)
        """, (order_id, name, comment, int(rating), comment))
        
        conn.commit()
        conn.close()
        
        return redirect(f"/feedback_success?order_id={order_id}")
    except Exception as e:
        print(f"Error submitting feedback: {e}")
        return redirect("/feedback")


@app.route('/edit_feedback', methods=['GET','POST'])
def edit_feedback():
    try:
        if request.method == 'POST':
            fid = request.form.get('id')
            name = request.form.get('name','Anonymous')
            rating = int(request.form.get('rating') or 5)
            comment = request.form.get('comment','')
            order_id = request.form.get('order_id','')
            conn = sqlite3.connect("feedback.db")
            c = conn.cursor()
            c.execute("UPDATE feedbacks SET name=?, rating=?, comment=?, order_id=? WHERE id=?", (name, rating, comment, order_id, fid))
            conn.commit()
            conn.close()
            return redirect(request.referrer or url_for('view_feedback'))
        else:
            fid = request.args.get('id')
            conn = sqlite3.connect("feedback.db")
            c = conn.cursor()
            c.execute("SELECT id, order_id, name, feedback, rating, comment, images, date FROM feedbacks WHERE id=?", (fid,))
            row = c.fetchone()
            conn.close()
            if not row:
                return redirect(url_for('view_feedback'))
            fb = {'id':row[0],'order_id':row[1],'name':row[2],'feedback':row[3],'rating':row[4],'comment':row[5],'images':row[6],'date':row[7]}
            return render_template('edit_feedback.html', fb=fb)
    except Exception as e:
        print(f"Edit feedback error: {e}")
        return redirect(url_for('view_feedback'))

@app.route('/delete_feedback', methods=['POST'])
def delete_feedback():
    try:
        fid = request.form.get('id')
        conn = sqlite3.connect("feedback.db")
        c = conn.cursor()
        c.execute("DELETE FROM feedbacks WHERE id=?", (fid,))
        conn.commit()
        conn.close()
        return redirect(request.referrer or url_for('view_feedback'))
    except Exception as e:
        print(f"Delete feedback error: {e}")
        return redirect(url_for('view_feedback'))


@app.route("/userdetails")
def userdetails():
    # Accept optional product details passed as query parameters
    product_name = request.args.get('product', '')
    amount = request.args.get('amount', '')
    image = request.args.get('image', '')
    return render_template("userdetails.html", product_name=product_name, amount=amount, image=image)

# -----------------------
# SIMPLE SMS INTERFACE
# -----------------------
@app.route('/simple-sms', methods=['GET'])
def simple_sms():
    """Simple SMS sender interface"""
    tw_sid, tw_token, tw_from = get_twilio_credentials()
    from_number = tw_from or "(Configure Twilio)"
    return render_template('simple_sms.html', from_number=from_number, business=BUSINESS_CONFIG)

@app.route('/api/send-simple-sms', methods=['POST'])
def api_send_simple_sms():
    """API endpoint for simple SMS sending"""
    try:
        to_phone = request.form.get('to_phone', '').strip()
        message = request.form.get('message', '').strip()
        
        # Validate
        if not to_phone:
            return {'success': False, 'message': 'Phone number is required'}, 400
        
        if not message:
            return {'success': False, 'message': 'Message is required'}, 400
        
        if len(message) > 160:
            return {'success': False, 'message': 'Message too long (max 160 characters)'}, 400
        
        # Send SMS
        print(f"\n🔵 SIMPLE SMS REQUEST")
        print(f"  To: {to_phone}")
        print(f"  Message: {message}")
        
        success = send_sms(to_phone, message)
        
        if success:
            print(f"  ✓ SENT SUCCESSFULLY\n")
            return {'success': True, 'message': 'SMS sent successfully'}
        else:
            print(f"  ✗ FAILED\n")
            return {'success': False, 'message': 'Failed to send SMS. Check configuration.'}, 500
            
    except Exception as e:
        print(f"  ✗ ERROR: {str(e)}\n")
        return {'success': False, 'message': str(e)}, 500

# -----------------------
# TEST ROUTES
# -----------------------
@app.route('/test-autofill')
def test_autofill():
    """Test page for product autofill functionality"""
    with open('test_autofill.html', 'r') as f:
        return f.read()

# -----------------------
# ERROR HANDLERS
# -----------------------
@app.errorhandler(404)
def page_not_found(e):
    return render_template('404.html'), 404

@app.errorhandler(500)
def internal_server_error(e):
    return render_template('500.html', error=str(e)), 500


# JSON-backed feedback helpers (Legacy - now using SQLite)
FEEDBACK_FILE = "feedbacks.json"

def load_feedbacks():
    if os.path.exists(FEEDBACK_FILE):
        try:
            with open(FEEDBACK_FILE, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception:
            return []
    return []

def save_feedbacks(items):
    try:
        with open(FEEDBACK_FILE, 'w', encoding='utf-8') as f:
            json.dump(items, f, indent=2, ensure_ascii=False)
        return True
    except Exception:
        return False

# Order confirmed (autofill)
@app.route("/order_confirmed")
def order_confirmed():
    order_id = request.args.get('order_id') or request.args.get('order', '')
    product = request.args.get('product') or request.args.get('product_name') or ''
    amount = request.args.get('amount') or request.args.get('amount_paid') or ''
    image = request.args.get('image', '')
    status = request.args.get('status', 'Ordered')
    return render_template('order_confirmed.html',
                           order_id=order_id,
                           product=product,
                           amount=amount,
                           image=image,
                           status=status,
                           business=BUSINESS_CONFIG)



# Admin view for feedback (reads feedbacks.json)
@app.route("/admin/feedback")
def admin_view_feedback():
    try:
        conn = sqlite3.connect("feedback.db")
        cursor = conn.cursor()

        # Ensure base table exists and optional columns are present
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS feedbacks (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                order_id TEXT,
                name TEXT,
                feedback TEXT,
                rating INTEGER DEFAULT 5,
                comment TEXT,
                images TEXT,
                date TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        cursor.execute("PRAGMA table_info(feedbacks)")
        cols = [r[1] for r in cursor.fetchall()]
        if 'order_id' not in cols:
            try:
                cursor.execute("ALTER TABLE feedbacks ADD COLUMN order_id TEXT")
                conn.commit()
            except Exception:
                pass

        cursor.execute("SELECT id, order_id, name, feedback, rating, comment, images, date FROM feedbacks ORDER BY date DESC")
        rows = cursor.fetchall()
        conn.close()

        feedback_list = []
        for r in rows:
            images_text = r[6] or ''
            images = [i.strip() for i in images_text.split(',') if i.strip()] if images_text else []
            feedback_list.append({
                'id': r[0],
                'order_id': r[1],
                'name': r[2] or 'Anonymous',
                'feedback': r[3],
                'rating': int(r[4]) if r[4] is not None else 5,
                'comment': r[5] or (r[3] or ''),
                'images': images,
                'date': r[7] or ''
            })

        return render_template('admin_feedback.html', feedbacks=feedback_list, business=BUSINESS_CONFIG)
    except Exception as e:
        print(f"Error loading admin feedbacks: {e}")
        return render_template('admin_feedback.html', feedbacks=[], business=BUSINESS_CONFIG)

# Admin: update order status (Ordered / Packed / Shipped / Delivered)
@app.route("/admin/update-order-status/<customer_id>", methods=["POST"])
def admin_update_order_status(customer_id):
    new_status = request.form.get('status')
    if not new_status:
        return redirect(url_for('admin_customer_detail', customer_id=customer_id, error='Missing status'))

    customers = load_customers()
    updated = False
    for c in customers:
        if c.get('id') == customer_id:
            c['status'] = new_status
            c['status_updated_at'] = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            updated = True
            break

    if updated:
        save_customers(customers)
        return redirect(url_for('admin_customer_detail', customer_id=customer_id, success=f'Status updated to {new_status}'))
    return redirect(url_for('admin_customers', error='Order not found'))


if __name__ == "__main__":
    app.run(debug=True)
