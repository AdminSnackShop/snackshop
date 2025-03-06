from flask import Flask, render_template, request, redirect, url_for, session
import os
import datetime
from googleapiclient.discovery import build
from oauth2client.service_account import ServiceAccountCredentials
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import io
import base64

app = Flask(__name__)
app.secret_key = 'supersuperndhs-secret-key-ndhs'  # Replace with your own unique string

# Snack data with "Poptarts" renamed
snacks = {
    'Chips': 1.50, 'Soda': 1.50, 'Poptarts': 2.00,  # Changed from PopTarts
    'Cookies': 1.50, 'Candy': 1.50, 'Water': 1.00
}

# Google Sheets setup
SPREADSHEET_ID = '1rwTYlHWIzttck_WOZH2mSYhHWAe2cL8tuUPNP-3w4wM'  # Replace with your ID
SHEET_NAME = 'SalesData'
SCOPES = ['https://www.googleapis.com/auth/spreadsheets']
CREDENTIALS_FILE = os.path.join(os.path.dirname(__file__), 'snackshopapp-65fc5bb44f8d.json')

# User credentials with locations
USERS = {
    'Schettini': {'password': 'w101', 'location': 'W101'},
    'Mejia': {'password': 's306', 'location': 'S306'},
    'Aziz': {'password': 'w115', 'location': 'W115'}
}

def get_sheets_service():
    creds = ServiceAccountCredentials.from_json_keyfile_name(CREDENTIALS_FILE, SCOPES)
    return build('sheets', 'v4', credentials=creds)

def initialize_google_sheet():
    service = get_sheets_service()
    sheet = service.spreadsheets()
    result = sheet.values().get(spreadsheetId=SPREADSHEET_ID, range=f"{SHEET_NAME}!A1:F1").execute()
    values = result.get('values', [])
    if not values:
        headers = ["Timestamp", "Items Purchased", "Total", "Amount Given", "Change", "Origin"]
        body = {'values': [headers]}
        sheet.values().append(spreadsheetId=SPREADSHEET_ID, range=f"{SHEET_NAME}!A1",
                              valueInputOption="RAW", body=body).execute()

def log_sale_to_google_sheets(total, items, payment, change, origin):
    service = get_sheets_service()
    sheet = service.spreadsheets()
    now = datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    sale_data = [now, ", ".join(items), f"${total:.2f}", f"${payment:.2f}", f"${change:.2f}", origin]
    body = {'values': [sale_data]}
    sheet.values().append(spreadsheetId=SPREADSHEET_ID, range=f"{SHEET_NAME}!A:F",
                          valueInputOption="RAW", body=body).execute()

def calculate_change(change):
    denominations = [
        (20.00, "20 Dollar Bill"), (10.00, "10 Dollar Bill"), (5.00, "5 Dollar Bill"),
        (1.00, "1 Dollar Bill"), (0.25, "Quarter"), (0.10, "Dime"), (0.05, "Nickel"), (0.01, "Penny")
    ]
    change_breakdown = {}
    remaining_change = round(change * 100)
    for value, name in denominations:
        value_cents = int(value * 100)
        count = remaining_change // value_cents
        if count > 0:
            change_breakdown[name] = count
            remaining_change %= value_cents
    return change_breakdown

@app.route('/', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        if username in USERS and USERS[username]['password'] == password:
            session['user'] = username
            session['items'] = []
            session['payment'] = 0.0
            return redirect(url_for('shop'))
        return render_template('login.html', error="Invalid username or password")
    return render_template('login.html', error=None)

@app.route('/shop', methods=['GET', 'POST'])
def shop():
    if 'user' not in session:
        return redirect(url_for('login'))

    if 'items' not in session:
        session['items'] = []
    if 'payment' not in session:
        session['payment'] = 0.0

    total = sum(snacks[item] for item in session['items'])
    change = session['payment'] - total if session['payment'] >= total else 0.0
    change_breakdown = calculate_change(change) if change > 0 else {}

    service = get_sheets_service()
    sheet = service.spreadsheets()
    result = sheet.values().get(spreadsheetId=SPREADSHEET_ID, range=f"{SHEET_NAME}!A2:F").execute()
    transactions = [f"{row[0]} | {row[1]} | {row[2]} | {row[5]}" for row in reversed(result.get('values', [])[-10:]) if len(row) >= 6]

    if request.method == 'POST':
        action = request.form.get('action')
        
        if action == 'add_snack':
            snack = request.form['snack']
            session['items'].append(snack)
            session.modified = True
        elif action == 'remove_last':
            if session['items']:
                session['items'].pop()
                session.modified = True
        elif action == 'add_cash':
            amount = float(request.form['amount'])
            session['payment'] += amount
            session.modified = True
        elif action == 'process':
            if session['payment'] < total:
                return render_template('shop.html', error="Insufficient funds", snacks=snacks, items=session['items'],
                                       total=total, payment=session['payment'], change=change, change_breakdown=change_breakdown,
                                       transactions=transactions)
            origin = USERS[session['user']]['location']
            log_sale_to_google_sheets(total, session['items'], session['payment'], change, origin)
            session['items'] = []
            session['payment'] = 0.0
            session.modified = True
            return render_template('shop.html', success="Sale processed!", snacks=snacks, items=session['items'],
                                   total=0, payment=0.0, change=0, change_breakdown={}, transactions=transactions)
        elif action == 'reset':
            session['items'] = []
            session['payment'] = 0.0
            session.modified = True

        total = sum(snacks[item] for item in session['items'])
        change = session['payment'] - total if session['payment'] >= total else 0.0
        change_breakdown = calculate_change(change) if change > 0 else {}

    return render_template('shop.html', snacks=snacks, items=session['items'], total=total, payment=session['payment'],
                          change=change, change_breakdown=change_breakdown, transactions=transactions)

@app.route('/analysis')
def analysis():
    if 'user' not in session:
        return redirect(url_for('login'))
    
    service = get_sheets_service()
    sheet = service.spreadsheets()
    result = sheet.values().get(spreadsheetId=SPREADSHEET_ID, range=f"{SHEET_NAME}!A2:F").execute()
    sales_data = result.get('values', [])
    
    snack_counts = {snack: 0 for snack in snacks}
    total_sales = 0
    for row in sales_data:
        if len(row) >= 3:
            items = row[1].split(", ")
            for item in items:
                if item in snack_counts:
                    snack_counts[item] += 1
            total_sales += float(row[2].replace("$", ""))
    most_popular = max(snack_counts.items(), key=lambda x: x[1])

    origin_sales = {'W101': 0, 'S306': 0, 'W115': 0}
    origin_snack_counts = {origin: {snack: 0 for snack in snacks} for origin in origin_sales}
    for row in sales_data:
        if len(row) >= 6:
            items = row[1].split(", ")
            total = float(row[2].replace("$", ""))
            origin = row[5]
            if origin in origin_sales:
                origin_sales[origin] += total
                for item in items:
                    if item in origin_snack_counts[origin]:
                        origin_snack_counts[origin][item] += 1
    origin_most_popular = {origin: max(counts.items(), key=lambda x: x[1]) for origin, counts in origin_snack_counts.items()}

    def plot_to_base64(fig):
        buf = io.BytesIO()
        fig.savefig(buf, format='png')
        buf.seek(0)
        return base64.b64encode(buf.getvalue()).decode('utf-8')

    fig1, ax1 = plt.subplots(figsize=(8, 4))
    ax1.bar(snack_counts.keys(), snack_counts.values(), color='#2ecc71')
    ax1.set_title("Snacks Sold (Overall)")
    ax1.set_xlabel("Snacks")
    ax1.set_ylabel("Quantity Sold")
    plt.xticks(rotation=45)
    plt.tight_layout()
    overall_chart = plot_to_base64(fig1)
    plt.close(fig1)

    fig2, ax2 = plt.subplots(figsize=(8, 4))
    ax2.bar(origin_sales.keys(), origin_sales.values(), color='#3498db')
    ax2.set_title("Total Sales by Origin")
    ax2.set_xlabel("Origin")
    ax2.set_ylabel("Total Sales ($)")
    plt.tight_layout()
    origin_chart = plot_to_base64(fig2)
    plt.close(fig2)

    return render_template('analysis.html', total_sales=total_sales, most_popular=most_popular,
                          origin_sales=origin_sales, origin_most_popular=origin_most_popular,
                          overall_chart=overall_chart, origin_chart=origin_chart)

if __name__ == "__main__":
    initialize_google_sheet()
    app.run(host='0.0.0.0', port=5000, debug=True)