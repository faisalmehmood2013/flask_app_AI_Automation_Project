from flask import Flask, render_template
import gspread
from oauth2client.service_account import ServiceAccountCredentials
import os 
import sys # For clean exit on critical error
import json # REQUIRED: To parse JSON string from environment variable

# Initialize the Flask application
app = Flask(__name__)

# --- Google Sheets Configuration ---

# 1. Credentials File/Key Name Configuration
SERVICE_ACCOUNT_FILE = 'credential.json' 
GOOGLE_SHEETS_ENV_VAR = 'GOOGLE_SHEETS_CREDENTIALS' # Name of the Vercel Environment Variable

# 2. EXACT Spreadsheet Name
SHEET_NAME = 'Nestle Water Distribution Original' 
# 3. EXACT Worksheet Tab Name
WORKSHEET_NAME = 'Stock Register' 

# Define API access scope (read-only)
SCOPE = [
    'https://www.googleapis.com/auth/spreadsheets.readonly',
    'https://www.googleapis.com/auth/drive.readonly'
]

# --- Authentication ---
CLIENT = None 

# Check for credentials and attempt connection upon app startup
try:
    if os.environ.get(GOOGLE_SHEETS_ENV_VAR):
        # METHOD A (Vercel Production): Load from Environment Variable
        creds_json = json.loads(os.environ.get(GOOGLE_SHEETS_ENV_VAR))
        CREDS = ServiceAccountCredentials.from_json_keyfile_dict(creds_json, SCOPE)
        print("Google Sheets API connection established successfully via VERCEL ENV.")

    elif os.path.exists(SERVICE_ACCOUNT_FILE):
        # METHOD B (Local Development): Load from local file
        CREDS = ServiceAccountCredentials.from_json_keyfile_name(SERVICE_ACCOUNT_FILE, SCOPE)
        print("Google Sheets API connection established successfully via LOCAL FILE.")
    
    else:
        # Critical failure if neither found
        print(f"CRITICAL ERROR: Credentials not found. Neither {SERVICE_ACCOUNT_FILE} nor Vercel ENV var '{GOOGLE_SHEETS_ENV_VAR}' is set.")
        sys.exit(1)
        
    CLIENT = gspread.authorize(CREDS)
    
except Exception as e:
    print(f"CRITICAL ERROR: Failed to authorize Google Sheets API. Check credentials or sharing permissions. Error: {e}")
    CLIENT = None # Ensure client is None if auth fails
    # Do not sys.exit(1) here on Vercel, allow the app to run with an error state

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