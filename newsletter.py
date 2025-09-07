import csv, json, os, smtplib, ssl, calendar
from datetime import date
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
import requests

# ---- secrets from GitHub Actions ----
AMADEUS_KEY = os.environ["AMADEUS_KEY"]
AMADEUS_SECRET = os.environ["AMADEUS_SECRET"]
GMAIL_USER = os.environ["GMAIL_USER"]
GMAIL_APP_PASSWORD = os.environ["GMAIL_APP_PASSWORD"]

# ---- Amadeus endpoints (sandbox/free tier) ----
AMAD_AUTH_URL = "https://test.api.amadeus.com/v1/security/oauth2/token"
AMAD_SEARCH_URL = "https://test.api.amadeus.com/v2/shopping/flight-offers"

def get_token():
    data = {
        "grant_type": "client_credentials",
        "client_id": AMADEUS_KEY,
        "client_secret": AMADEUS_SECRET
    }
    r = requests.post(AMAD_AUTH_URL, data=data, timeout=30)
    r.raise_for_status()
    return r.json()["access_token"]

def month_dates(yyyymm: str):
    y, m = map(int, yyyymm.split("-"))
    _, days = calendar.monthrange(y, m)
    picks = {1, 8, 15, 22, min(29, days)}  # sample 5 days
    return [date(y, m, d).isoformat() for d in sorted(picks)]

def search_min_price(token, origin, dest, dep_date):
    params = {
        "originLocationCode": origin,
        "destinationLocationCode": dest,
        "departureDate": dep_date,
        "adults": 1,
        "currencyCode": "USD",
        "max": 5
    }
    h = {"Authorization": f"Bearer {token}"}
    r = requests.get(AMAD_SEARCH_URL, headers=h, params=params, timeout=30)
    if r.status_code == 400:
        return None
    r.raise_for_status()
    data = r.json()
    best = None
    for item in data.get("data", []):
        price = float(item["price"]["total"])
        if best is None or price < best:
            best = price
    return best

def google_flights_link(origin, dest, yyyymm):
    y, m = yyyymm.split("-")
    return f"https://www.google.com/travel/flights?hl=en#flt={origin}.{dest}.{y}-{m}-01*{dest}.{origin}.{y}-{m}-08"

def build_section(token, watch):
    dates = month_dates(watch["month"])
    rows = []
    for origin in watch["origins"]:
        for dest in watch["destinations"]:
            best = None
            for d in dates:
                p = search_min_price(token, origin, dest, d)
                if p is not None and (best is None or p < best):
                    best = p
            if best is not None:
                rows.append((origin, dest, best, google_flights_link(origin, dest, watch["month"])))
    rows.sort(key=lambda x: x[2])
    return rows[:6]

def load_subscribers():
    emails = []
    with open("subscribers.csv", newline="") as f:
        for row in csv.reader(f):
            if row and "@" in row[0]:
                emails.append(row[0].strip())
    return emails

def build_html(all_sections):
    parts = ["<h2>Weekly Flight Deals</h2>"]
    for title, rows in all_sections:
        parts.append(f"<h3>{title}</h3><ul>")
        if not rows:
            parts.append("<li>No results this week.</li>")
        for origin, dest, price, link in rows:
            parts.append(f'<li><strong>{origin} → {dest}</strong>: ${price:.0f} — <a href="{link}">View</a></li>')
        parts.append("</ul>")
    return "\n".join(parts)

def send_email(html_body):
    recipients = load_subscribers()
    if not recipients:
        print("No subscribers found.")
        return
    msg = MIMEMultipart("alternative")
    msg["Subject"] = "Weekly Flight Deals"
    msg["From"] = GMAIL_USER
    msg["To"] = ", ".join(recipients)
    msg.attach(MIMEText(html_body, "html"))
    ctx = ssl.create_default_context()
    with smtplib.SMTP_SSL("smtp.gmail.com", 465, context=ctx) as server:
        server.login(GMAIL_USER, GMAIL_APP_PASSWORD)
        server.sendmail(GMAIL_USER, recipients, msg.as_string())

def main():
    token = get_token()
    with open("routes.json") as f:
        watches = json.load(f)
    sections = [(w["title"], build_section(token, w)) for w in watches]
    html = build_html(sections)
    send_email(html)

if __name__ == "__main__":
    main()
