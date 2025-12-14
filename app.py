from flask import Flask, render_template, request
import gspread
from oauth2client.service_account import ServiceAccountCredentials
import os 
import sys 
import json 
from collections import defaultdict

# ====================================================================
# 1. Initialize the Flask application
# ====================================================================
app = Flask(__name__)

# --- CUSTOM JINJA2 FILTER FOR CURRENCY FORMATTING ---
# Fixes Jinja2.exceptions.TemplateAssertionError
def format_currency_filter(value):
    """Formats an integer/float with thousands comma separators."""
    try:
        return "{:,}".format(int(value)) if value is not None else ""
    except (ValueError, TypeError):
        return str(value)

# Register the custom filter with Jinja environment
app.jinja_env.filters['format_currency'] = format_currency_filter
# -----------------------------------------------------


# ====================================================================
# 2. Google Sheets Configuration & Authentication
# ====================================================================

SERVICE_ACCOUNT_FILE = 'credential.json' 
GOOGLE_SHEETS_ENV_VAR = 'GOOGLE_SHEETS_CREDENTIALS' 

SHEET_NAME = 'Nestle Water Distribution Original' 
# Other required sheet names:
SHEET_PNL = 'P/L'
SHEET_STOCK = 'Stock Register'
SHEET_SALES = 'Sales Register'
SHEET_CUSTOMER_ORDER = 'Customer Order'

SCOPE = [
    'https://www.googleapis.com/auth/spreadsheets.readonly',
    'https://www.googleapis.com/auth/drive.readonly'
]

CLIENT = None 

# Check for credentials and attempt connection upon app startup
try:
    if os.environ.get(GOOGLE_SHEETS_ENV_VAR):
        creds_json = json.loads(os.environ.get(GOOGLE_SHEETS_ENV_VAR))
        CREDS = ServiceAccountCredentials.from_json_keyfile_dict(creds_json, SCOPE)
        print("Google Sheets API connection established successfully via VERCEL ENV.")
    elif os.path.exists(SERVICE_ACCOUNT_FILE):
        CREDS = ServiceAccountCredentials.from_json_keyfile_name(SERVICE_ACCOUNT_FILE, SCOPE)
        print("Google Sheets API connection established successfully via LOCAL FILE.")
    else:
        print(f"CRITICAL ERROR: Credentials not found. Neither {SERVICE_ACCOUNT_FILE} nor Vercel ENV var '{GOOGLE_SHEETS_ENV_VAR}' is set.")
        
    if 'CREDS' in locals():
        CLIENT = gspread.authorize(CREDS)
    
except Exception as e:
    print(f"CRITICAL ERROR: Failed to authorize Google Sheets API. Error: {e}")
    CLIENT = None 


# ====================================================================
# 3. Routes
# ====================================================================

@app.route('/orders')
def orders():
    return render_template('order.html')

@app.route('/inventory')
def inventory():
    # Inventory route logic (unchanged from previous version)
    if CLIENT is None:
        return render_template('inventory.html', sheet_data=None, error_message="Google Sheets connection failed at startup.")
    
    try:
        spreadsheet = CLIENT.open(SHEET_NAME)
        # Using WORKSHEET_NAME = 'Stock Register' from config
        worksheet = spreadsheet.worksheet(SHEET_STOCK) 
        data = worksheet.get_all_records() 
        return render_template('inventory.html', sheet_data=data, error_message=None)
        
    except Exception as e:
        error_msg = f"Sorry, could not fetch the inventory data right now. Error: {e}"
        print(error_msg)
        return render_template('inventory.html', sheet_data=None, error_message=error_msg)


@app.route('/dashboard')
def dashboard():
    """Fetches key performance metrics (Sales, Purchase, Expense, Profit, Stock) from multiple worksheets for the dashboard."""
    
    if CLIENT is None:
        return render_template('dashboard.html', error_message="Google Sheets connection failed at startup.")
    
    context = {
        'error_message': None,
        'pnl_metrics': {},
        'total_products': 0,
        'low_stock_count': 0,
        'total_sales_value': 0,
        'total_purchase_value': 0, # NEW: Total Purchase Value
        'total_expense': 0,        # NEW: Total Expense
        'total_customers': 0,
        'latest_update': 'N/A',
        'sales_sku_wise': [],
        'dispatch_status': {'Delivered': 0, 'Returned': 0, 'Pending': 0}
    }

    try:
        spreadsheet = CLIENT.open(SHEET_NAME)
        
        # --- A. P&L Metrics (for Net Profit and Total Expense) ---
        pnl_worksheet = spreadsheet.worksheet(SHEET_PNL)
        pnl_data_list = pnl_worksheet.get_all_records()
        context['pnl_metrics'] = pnl_data_list[0] if pnl_data_list else {}
        context['latest_update'] = context['pnl_metrics'].get('Date', 'N/A')
        
        # Fetch Total Expense from P&L Sheet
        context['total_expense'] = int(context['pnl_metrics'].get('Total Expense', 0))


        # --- B. Stock Overview, Sales, and Purchase Calculation ---
        stock_worksheet = spreadsheet.worksheet(SHEET_STOCK)
        all_stock_data = stock_worksheet.get_all_records()

        context['total_products'] = len(all_stock_data)
        
        sku_sales_units = []
        total_sales_price_calc = 0
        total_purchase_price_calc = 0 # NEW accumulator
        low_stock_count = 0

        for record in all_stock_data:
            product_name = record.get('product_name', 'Unknown')
            size = record.get('size', '')
            
            # --- Sales Calculation ---
            units_sold = int(record.get('sale_stock', 0))
            sale_price_per_unit = int(record.get('sale_price', 0))
            
            # ACCUMULATE: Total Sales Value (All SKUs)
            total_sales_price_calc += (units_sold * sale_price_per_unit)
            
            # --- Purchase Calculation ---
            # ACCUMULATE: Total Purchase Value (Using total_purchase column from Stock Register)
            total_purchase_price_calc += int(record.get('total_purchase', 0))
            
            # --- Stock Status ---
            if int(record.get('current_stock', 0)) < int(record.get('reorder_level', 0)):
                low_stock_count += 1
            
            # Prepare SKU-wise sales data
            if units_sold > 0:
                sku_sales_units.append({
                    'product': f"{product_name} - {size}",
                    'quantity': units_sold
                })
        
        context['low_stock_count'] = low_stock_count
        context['total_sales_value'] = total_sales_price_calc 
        context['total_purchase_value'] = total_purchase_price_calc # Set Total Purchase Value
        context['sales_sku_wise'] = sku_sales_units

        # --- C. Total Customers (from Customer Order sheet) ---
        customer_order_worksheet = spreadsheet.worksheet(SHEET_CUSTOMER_ORDER)
        all_customer_data = customer_order_worksheet.get_all_records()
        
        unique_customers = set(record.get('customer_name') for record in all_customer_data if record.get('customer_name'))
        context['total_customers'] = len(unique_customers)

        # --- D. Dispatch Status (from Dispatch sheet) ---
        dispatch_worksheet = spreadsheet.worksheet('Dispatch')
        all_dispatch_data = dispatch_worksheet.get_all_records()
        
        status_counts = defaultdict(int)
        for record in all_dispatch_data:
            status = record.get('current_status', 'Unknown') 
            status_counts[status] += 1
            
        context['dispatch_status'] = dict(status_counts) 

        return render_template('dashboard.html', **context)
        
    except gspread.exceptions.WorksheetNotFound as e:
        error_msg = f"ERROR: Required worksheet not found. Check sheet names: P/L, Stock Register, Customer Order, Dispatch. Error: {e}"
        return render_template('dashboard.html', error_message=error_msg)
    except Exception as e:
        error_msg = f"Sorry, could not fetch dashboard data. Unexpected Error: {e}"
        print(e)
        return render_template('dashboard.html', error_message=error_msg)
    
# app.py file (Add this new function)

@app.route('/contact', methods=['GET', 'POST'])
def contact():
    """Renders the contact form and handles form submission."""
    
    if request.method == 'POST':
        # Retrieve form data
        name = request.form.get('name')
        email = request.form.get('email')
        message = request.form.get('message')
        
        # --- Data Handling Logic (Where a Data Analyst would process the lead) ---
        
        # NOTE: In a production environment, you would save this data to:
        # 1. A Google Sheet (using gspread client)
        # 2. A database (SQL/NoSQL)
        # 3. Send it as an email notification
        
        # For now, we will just print the data to the console and show a success message.
        print(f"\n--- NEW CONTACT FORM SUBMISSION ---")
        print(f"Name: {name}")
        print(f"Email: {email}")
        print(f"Message: {message}")
        print(f"-----------------------------------\n")

        # Pass a success message back to the template
        success_message = "Thank you! Your message has been received. We will contact you shortly."
        
        # We render the template again with the message
        return render_template('contact.html', success_message=success_message)
        
    # GET Request: Just show the form
    return render_template('contact.html', success_message=None)


# ====================================================================
# 4. Run the application
# ====================================================================
if __name__ == '__main__':
    app.run(debug=True)


# from flask import Flask, render_template
# import gspread
# from oauth2client.service_account import ServiceAccountCredentials
# import os 
# import sys # For clean exit on critical error
# import json # REQUIRED: To parse JSON string from environment variable

# # Initialize the Flask application
# app = Flask(__name__)

# # --- Google Sheets Configuration ---

# # 1. Credentials File/Key Name Configuration
# SERVICE_ACCOUNT_FILE = 'credential.json' 
# GOOGLE_SHEETS_ENV_VAR = 'GOOGLE_SHEETS_CREDENTIALS' # Name of the Vercel Environment Variable

# # 2. EXACT Spreadsheet Name
# SHEET_NAME = 'Nestle Water Distribution Original' 
# # 3. EXACT Worksheet Tab Name
# WORKSHEET_NAME = 'Stock Register' 

# # Define API access scope (read-only)
# SCOPE = [
#     'https://www.googleapis.com/auth/spreadsheets.readonly',
#     'https://www.googleapis.com/auth/drive.readonly'
# ]

# # --- Authentication ---
# CLIENT = None 

# # Check for credentials and attempt connection upon app startup
# try:
#     if os.environ.get(GOOGLE_SHEETS_ENV_VAR):
#         # METHOD A (Vercel Production): Load from Environment Variable
#         creds_json = json.loads(os.environ.get(GOOGLE_SHEETS_ENV_VAR))
#         CREDS = ServiceAccountCredentials.from_json_keyfile_dict(creds_json, SCOPE)
#         print("Google Sheets API connection established successfully via VERCEL ENV.")

#     elif os.path.exists(SERVICE_ACCOUNT_FILE):
#         # METHOD B (Local Development): Load from local file
#         CREDS = ServiceAccountCredentials.from_json_keyfile_name(SERVICE_ACCOUNT_FILE, SCOPE)
#         print("Google Sheets API connection established successfully via LOCAL FILE.")
    
#     else:
#         # Critical failure if neither found
#         print(f"CRITICAL ERROR: Credentials not found. Neither {SERVICE_ACCOUNT_FILE} nor Vercel ENV var '{GOOGLE_SHEETS_ENV_VAR}' is set.")
#         sys.exit(1)
        
#     CLIENT = gspread.authorize(CREDS)
    
# except Exception as e:
#     print(f"CRITICAL ERROR: Failed to authorize Google Sheets API. Check credentials or sharing permissions. Error: {e}")
#     CLIENT = None # Ensure client is None if auth fails
#     # Do not sys.exit(1) here on Vercel, allow the app to run with an error state

# # --- Routes ---

# @app.route('/')
# def index():
#     """Renders the main home page template."""
#     return render_template('index.html')

# @app.route('/inventory')
# def inventory():
#     """Fetches live inventory data from the specific Google Sheet and Worksheet."""
    
#     # Check for authentication failure
#     if CLIENT is None:
#         return render_template('inventory.html', sheet_data=None, error_message="Google Sheets connection failed at startup.")
    
#     try:
#         # 1. Open the spreadsheet by its name
#         spreadsheet = CLIENT.open(SHEET_NAME)
        
#         # 2. Select the specific worksheet by its name
#         worksheet = spreadsheet.worksheet(WORKSHEET_NAME) 
        
#         # 3. Fetch all data as a list of dictionaries (records)
#         data = worksheet.get_all_records() 
        
#         # 4. Render the template and pass the fetched data
#         return render_template('inventory.html', sheet_data=data, error_message=None)
        
#     except gspread.exceptions.SpreadsheetNotFound:
#         error_msg = f"ERROR: Spreadsheet '{SHEET_NAME}' not found. Check the sheet name and sharing permissions."
#         print(error_msg)
#         return render_template('inventory.html', sheet_data=None, error_message=error_msg)
        
#     except gspread.exceptions.WorksheetNotFound:
#         error_msg = f"ERROR: Worksheet '{WORKSHEET_NAME}' not found in the spreadsheet."
#         print(error_msg)
#         return render_template('inventory.html', sheet_data=None, error_message=error_msg)
        
#     except Exception as e:
#         error_msg = f"Sorry, could not fetch the inventory data right now. Unexpected Error: {e}"
#         print(error_msg)
#         return render_template('inventory.html', sheet_data=None, error_message=error_msg)

# # --- Run the application ---
# if __name__ == '__main__':
#     # Running the app in debug mode
#     app.run(debug=True)