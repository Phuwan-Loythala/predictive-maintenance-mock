import os
import json
import time
import numpy as np
import pandas as pd
import gspread
from oauth2client.service_account import ServiceAccountCredentials
from sklearn.linear_model import LinearRegression

# --- 1. Secret Management ---
# On Render, you will create an Environment Variable named 'GOOGLE_JSON'
google_json_str = os.environ.get('GOOGLE_JSON')

if not google_json_str:
    raise ValueError("GOOGLE_JSON environment variable not found!")

# Parse the JSON string from the environment variable
creds_dict = json.loads(google_json_str)
SCOPE = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
CREDS = ServiceAccountCredentials.from_json_dict(creds_dict, SCOPE)
client = gspread.authorize(CREDS)

# Open your Google Sheet by name
SHEET_NAME = "Robot_Telemetry_Data" # Make sure this matches your sheet title exactly
sheet = client.open(SHEET_NAME).sheet1

# --- 2. PdM Logic (Sony Standards) ---
THRESHOLD_POSE_DRIFT = 0.05
UPDATE_INTERVAL = 5 # Seconds between updates (Higher helps avoid API rate limits)

def calculate_robot_metrics(history, mode):
    df = pd.DataFrame(history)
    if len(df) < 2:
        return {'Health': 100, 'Status': 'OPTIMAL'}

    current_rms = np.sqrt(np.mean(df['motor_current']**2))
    pose_variance = df['pose_drift'].std()
    
    health = 100 - (max(0, current_rms - 10) * 5) - (pose_variance * 200)
    health = max(0, min(100, health))
    
    status = 'OPTIMAL' if health > 85 else ('WARNING' if health > 50 else 'CRITICAL')
    return {'Health': int(health), 'Status': status}

def get_robot_reading(step, mode):
    timestamp = pd.Timestamp.now().strftime('%Y-%m-%d %H:%M:%S')
    if mode == 'NORMAL':
        current = np.random.normal(10, 0.4)
        drift = np.random.normal(0.01, 0.001)
    elif mode == 'FAILING':
        current = np.random.normal(12, 0.7) + (step * 0.35)
        drift = np.random.normal(0.02, 0.004) + (step * 0.0025)
    else: # COOLING/CALIBRATING
        current = max(8, 14 - (step * 1.5))
        drift = max(0.008, 0.045 - (step * 0.008))
    return {'timestamp': timestamp, 'motor_current': current, 'pose_drift': drift, 'mode': mode}

# --- 3. Main Loop ---
history = []
step, mode = 0, 'NORMAL'

print(f"Connected to {SHEET_NAME}. Starting Telemetry...")

while True:
    try:
        reading = get_robot_reading(step, mode)
        history.append(reading)
        if len(history) > 20: history.pop(0)

        metrics = calculate_robot_metrics(history, mode)
        
        # Prepare row for Google Sheets
        row = [
            reading['timestamp'], 
            round(reading['motor_current'], 2), 
            round(reading['pose_drift'], 4), 
            metrics['Health'], 
            metrics['Status'],
            mode
        ]
        
        # Append to the end of the sheet
        sheet.append_row(row)
        print(f"Synced @ {reading['timestamp']} | Health: {metrics['Health']}% | Mode: {mode}")

        # Simulation state logic
        if mode == 'COOLING':
            if reading['pose_drift'] < 0.012: mode, step = 'NORMAL', 0
            else: step += 1
        else:
            if mode == 'NORMAL':
                if step > 15: mode, step = 'FAILING', 0
                else: step += 1
            elif mode == 'FAILING':
                if reading['pose_drift'] >= THRESHOLD_POSE_DRIFT: mode, step = 'COOLING', 0
                else: step += 1
        
        time.sleep(UPDATE_INTERVAL)
        
    except Exception as e:
        print(f"Error encountered: {e}")
        time.sleep(10) # Wait and retry