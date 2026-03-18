import os
import json
import asyncio
import numpy as np
import pandas as pd
import gspread
import pytz
from datetime import datetime
from fastapi import FastAPI
from dotenv import load_dotenv
from oauth2client.service_account import ServiceAccountCredentials

# 1. Load environment variables
load_dotenv()

app = FastAPI()

# --- Configuration ---
CREDS_PATH = os.getenv("GOOGLE_JSON", "creds.json") 
SHEET_NAME = "Robot_Maintenance"
THRESHOLD_POSE_DRIFT = 0.05
UPDATE_INTERVAL = 15  # Increased slightly to avoid Google API rate limits
BKK_TZ = pytz.timezone('Asia/Bangkok')

# Global state
telemetry_active = False
history = []

def get_gspread_client():
    if not os.path.exists(CREDS_PATH):
        print(f"CRITICAL: Credentials file NOT FOUND at: {CREDS_PATH}")
        return None
    
    try:
        SCOPE = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
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
    # LOCALIZED TIME: Get current time in Bangkok
    now_bkk = datetime.now(BKK_TZ)
    timestamp = now_bkk.strftime('%Y-%m-%d %H:%M:%S')
    
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
        # Open sheet once to keep connection alive
        sheet = client.open(SHEET_NAME).sheet1
        step, mode = 0, 'NORMAL'
        print(f"Connected to {SHEET_NAME}. BKK Telemetry starting...")

        while telemetry_active:
            reading = get_robot_reading(step, mode)
            history.append(reading)
            if len(history) > 20: history.pop(0)

            metrics = calculate_robot_metrics(history)
            
            row = [
                reading['timestamp'], 
                round(reading['motor_current'], 2), 
                round(reading['pose_drift'], 4), 
                metrics['Health'], 
                metrics['Status'], 
                mode
            ]
            
            # SAFE SYNC: Catching API errors specifically
            try:
                sheet.append_row(row, value_input_option='USER_ENTERED')
                print(f"✅ Synced BKK Time: {reading['timestamp']} | Health: {metrics['Health']}%")
            except Exception as sync_err:
                print(f"⚠️ Sync skipped (likely API Quota): {sync_err}")
                await asyncio.sleep(20) # Wait longer if Google is busy

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
        print(f"❌ Connection Fatal Error: {e}")

# --- API Endpoints ---
@app.get("/")
def health_check():
    return {
        "status": "Online", 
        "timezone": "Asia/Bangkok",
        "creds_file_exists": os.path.exists(CREDS_PATH)
    }

@app.on_event("startup")
async def startup_event():
    global telemetry_active
    telemetry_active = True
    asyncio.create_task(telemetry_loop())

@app.on_event("shutdown")
def shutdown_event():
    global telemetry_active
    telemetry_active = False