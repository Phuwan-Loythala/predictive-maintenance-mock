import os
import json
import asyncio
import numpy as np
import pandas as pd
import gspread
from fastapi import FastAPI
from dotenv import load_dotenv
from oauth2client.service_account import ServiceAccountCredentials

# 1. Load environment variables from .env (for Codespaces/Local)
load_dotenv()

app = FastAPI()

# --- Configuration ---
# Get the path from .env; default to 'creds.json' if not set
CREDS_PATH = os.getenv("GOOGLE_JSON", "creds.json") 
SHEET_NAME = "Robot_Maintenance"
THRESHOLD_POSE_DRIFT = 0.05
UPDATE_INTERVAL = 10  # Seconds (Safe for Google API rate limits)

# Global state
telemetry_active = False
history = []

def get_gspread_client():
    """Connects to Google Sheets using the filepath provided in .env"""
    if not os.path.exists(CREDS_PATH):
        print(f"CRITICAL: Credentials file NOT FOUND at: {CREDS_PATH}")
        return None
    
    try:
        SCOPE = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
        # Use the path from your .env to load the file
        CREDS = ServiceAccountCredentials.from_json_keyfile_name(CREDS_PATH, SCOPE)
        return gspread.authorize(CREDS)
    except Exception as e:
        print(f"GSpread Auth Error: {e}")
        return None

# --- PdM Logic ---
def calculate_robot_metrics(history):
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
        current, drift = np.random.normal(10, 0.4), np.random.normal(0.01, 0.001)
    elif mode == 'FAILING':
        current, drift = np.random.normal(12, 0.7) + (step * 0.35), np.random.normal(0.02, 0.004) + (step * 0.0025)
    else: # COOLING
        current, drift = max(8, 14 - (step * 1.5)), max(0.008, 0.045 - (step * 0.008))
    return {'timestamp': timestamp, 'motor_current': current, 'pose_drift': drift, 'mode': mode}

# --- Background Process ---
async def telemetry_loop():
    global telemetry_active, history
    client = get_gspread_client()
    if not client:
        return

    try:
        sheet = client.open(SHEET_NAME).sheet1
        step, mode = 0, 'NORMAL'
        print(f"Connected to {SHEET_NAME}. Loop starting...")

        while telemetry_active:
            reading = get_robot_reading(step, mode)
            history.append(reading)
            if len(history) > 20: history.pop(0)

            metrics = calculate_robot_metrics(history)
            
            # Prepare row: Timestamp, Current, Drift, Health, Status, Mode
            row = [
                reading['timestamp'], 
                round(reading['motor_current'], 2), 
                round(reading['pose_drift'], 4), 
                metrics['Health'], 
                metrics['Status'], 
                mode
            ]
            
            sheet.append_row(row)
            print(f"Synced Health: {metrics['Health']}% | Status: {metrics['Status']}")

            # State Transitions
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
            
            await asyncio.sleep(UPDATE_INTERVAL)

    except Exception as e:
        print(f"Main Loop Error: {e}")

# --- API Endpoints ---
@app.get("/")
def health_check():
    return {"status": "Online", "creds_file_exists": os.path.exists(CREDS_PATH)}

@app.on_event("startup")
async def startup_event():
    global telemetry_active
    telemetry_active = True
    asyncio.create_task(telemetry_loop())

@app.on_event("shutdown")
def shutdown_event():
    global telemetry_active
    telemetry_active = False