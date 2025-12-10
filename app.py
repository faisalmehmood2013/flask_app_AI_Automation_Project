from flask import Flask, render_template
import gspread
from oauth2client.service_account import ServiceAccountCredentials
import os 
import sys # For clean exit on critical error

# Initialize the Flask application
app = Flask(__name__)

# --- Google Sheets Configuration ---

# 1. IMPORTANT: Replace this path if your credential file is located elsewhere.
SERVICE_ACCOUNT_FILE = 'credential.json' 

# 2. EXACT Spreadsheet Name from the screenshot title bar
SHEET_NAME = 'Nestle Water Distribution Original' 
# 3. EXACT Worksheet Tab Name from the screenshot bottom tabs
WORKSHEET_NAME = 'Stock Register' 

# Define API access scope for reading sheets
SCOPE = [
    'https://www.googleapis.com/auth/spreadsheets.readonly',
    'https://www.googleapis.com/auth/drive.readonly'
]

# --- Authentication ---
CLIENT = None 

# Check for credentials and attempt connection upon app startup
try:
    if not os.path.exists(SERVICE_ACCOUNT_FILE):
        # Exit if the critical file is missing
        print(f"CRITICAL ERROR: Credential file not found at: {SERVICE_ACCOUNT_FILE}")
        sys.exit(1) # Exit application immediately
        
    CREDS = ServiceAccountCredentials.from_json_keyfile_name(SERVICE_ACCOUNT_FILE, SCOPE)
    CLIENT = gspread.authorize(CREDS)
    print("Google Sheets API connection established successfully.")
    
except Exception as e:
    print(f"CRITICAL ERROR: Failed to authorize Google Sheets API. Check credentials or sharing permissions. Error: {e}")
    CLIENT = None # Ensure client is None if auth fails

# --- Routes ---

@app.route('/')
def index():
    """Renders the main home page template."""
    return render_template('index.html')

@app.route('/inventory')
def inventory():
    """Fetches live inventory data from the specific Google Sheet and Worksheet."""
    
    # Check for authentication failure
    if CLIENT is None:
        return render_template('inventory.html', sheet_data=None, error_message="Google Sheets connection failed at startup.")
    
    try:
        # 1. Open the spreadsheet by its name
        spreadsheet = CLIENT.open(SHEET_NAME)
        
        # 2. Select the specific worksheet by its name
        worksheet = spreadsheet.worksheet(WORKSHEET_NAME) 
        
        # 3. Fetch all data as a list of dictionaries (records)
        #    NOTE: Keys in 'data' will match the header names in Row 1 of your sheet (e.g., 'product_name', 'SIZE').
        data = worksheet.get_all_records() 
        
        # 4. Render the template and pass the fetched data
        return render_template('inventory.html', sheet_data=data, error_message=None)
        
    except gspread.exceptions.SpreadsheetNotFound:
        error_msg = f"ERROR: Spreadsheet '{SHEET_NAME}' not found. Check the sheet name and sharing permissions."
        print(error_msg)
        return render_template('inventory.html', sheet_data=None, error_message=error_msg)
        
    except gspread.exceptions.WorksheetNotFound:
        error_msg = f"ERROR: Worksheet '{WORKSHEET_NAME}' not found in the spreadsheet."
        print(error_msg)
        return render_template('inventory.html', sheet_data=None, error_message=error_msg)
        
    except Exception as e:
        error_msg = f"Sorry, could not fetch the inventory data right now. Unexpected Error: {e}"
        print(error_msg)
        return render_template('inventory.html', sheet_data=None, error_message=error_msg)

# --- Run the application ---
if __name__ == '__main__':
    # Running the app in debug mode
    app.run(debug=True)
