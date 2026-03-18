# Predictive Maintenance Mock (Streamlit)

## Overview
This project simulates a 6-axis robot's operational data and demonstrates a predictive maintenance workflow using a Streamlit dashboard. It features real-time analytics, Google Sheets integration, and secure secret management.

## Features
- Simulates robot telemetry (motor current, pose drift) in NORMAL, FAILING, and CALIBRATING modes
- Real-time health scoring, Remaining Useful Life (RUL) estimation, and resonant frequency monitoring
- Interactive Streamlit dashboard for simulation control and visualization
- Persistent storage of telemetry and failure events in Google Sheets
- Secret management using environment variables and `.env` file

## Secret Management
- The Google Service Account JSON key is required to access Google Sheets.
- **Do NOT commit your actual service account key to version control.**
- Place your key file (e.g., `service_account.json`) in the project directory (or a secure location).
- Copy `.env.example` to `.env` and set the path to your key:
  ```
  GOOGLE_SERVICE_ACCOUNT_JSON=service_account.json
  ```
- The app will load this path from the environment variable for authentication.

## Setup Instructions
1. **Clone the repository**
2. **Install dependencies** (in your Python environment):
   ```bash
   pip install -r requirements.txt
   ```
3. **Set up your Google Service Account**
   - Follow the instructions in the app or comments in `app.py` to create and download your service account JSON key.
   - Share your target Google Sheet(s) with the service account email.
4. **Configure secrets**
   - Copy `.env.example` to `.env` and set the correct path to your key file.
5. **Run the app**
   ```bash
   streamlit run app.py
   ```

## .gitignore
- The `.gitignore` file is set to ignore `.env` and `service_account.json` for security.

## Requirements
- Python 3.8+
- Google Cloud account for Sheets API access

## Security Note
- Never share or commit your service account key or `.env` file to public repositories.
- For production, consider using a dedicated secret manager service.
