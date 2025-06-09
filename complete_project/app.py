import pandas as pd
import json
import os
import asyncio
import logging
from fastapi import FastAPI, WebSocket, Request
from fastapi.templating import Jinja2Templates
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from workflow import run_workflow, VendorState, CSV_FILE, EMAIL_OUTPUT_FILE
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)
# Initialize FastAPI app
app = FastAPI()
templates = Jinja2Templates(directory="complete_project")

# Configuration
CSV_FILE = "/Users/sachinbeast/Desktop/Desktop - Sachin’s MacBook Air/system/hackathin/database/vendors_dataset.csv"
EMAIL_FILE = "/Users/sachinbeast/Desktop/Desktop - Sachin’s MacBook Air/system/hackathin/data/email.txt"
EMAIL_OUTPUT_FILE = "/Users/sachinbeast/Desktop/Desktop - Sachin’s MacBook Air/system/hackathin/data/emails_op.txt"
# Pydantic model for email submission

class EmailInput(BaseModel):
    email_content: str

# FastAPI endpoints
@app.get("/")
async def get_dashboard(request: Request):
    """Serve the dashboard template."""
    return templates.TemplateResponse("template.html", {"request": request})


# Pydantic model for email submission
class EmailInput(BaseModel):
    email_content: str

# FastAPI endpoints
@app.get("/")
async def get_dashboard(request: Request):
    """Serve the dashboard template."""
    logger.info("Serving dashboard")
    return templates.TemplateResponse("index.html", {"request": request})

@app.get("/get-csv")
async def get_csv():
    """Fetch and validate the vendors_dataset.csv data."""
    logger.info(f"Attempting to read CSV file: {CSV_FILE}")
    try:
        if not os.path.exists(CSV_FILE):
            logger.error(f"CSV file not found: {CSV_FILE}")
            return JSONResponse(content={"error": f"CSV file not found at {CSV_FILE}"}, status_code=404)

        df = pd.read_csv(CSV_FILE)
        logger.info("CSV file read successfully")

        if df.empty:
            logger.warning("CSV file is empty")
            return JSONResponse(content={"data": [], "message": "CSV file is empty"})

        expected_columns = ['Vendor_ID', 'Vendor_Name', 'Bank_Account', 'Address', 'Name', 'Email', 'Phone_Number']
        missing_columns = [col for col in expected_columns if col not in df.columns]
        if missing_columns:
            logger.error(f"Missing required columns: {missing_columns}")
            return JSONResponse(content={"error": f"Missing required columns: {', '.join(missing_columns)}"}, status_code=400)

        data = df.to_dict(orient="records")
        logger.info(f"Returning {len(data)} records from CSV")
        return JSONResponse(content={"data": data})

    except pd.errors.EmptyDataError:
        logger.error("CSV file is empty or malformed")
        return JSONResponse(content={"error": "CSV file is empty or malformed"}, status_code=400)
    except pd.errors.ParserError:
        logger.error("Error parsing CSV file")
        return JSONResponse(content={"error": "Error parsing CSV file"}, status_code=400)
    except Exception as e:
        logger.error(f"Unexpected error reading CSV: {str(e)}")
        return JSONResponse(content={"error": f"Unexpected error: {str(e)}"}, status_code=500)

@app.post("/submit-email")
async def submit_email(email_input: EmailInput):
    """Save email content to email.txt."""
    logger.info("Received email submission request")
    try:
        if not email_input.email_content.strip():
            logger.error("Email content is empty")
            return JSONResponse(content={"error": "Email content cannot be empty"}, status_code=400)
        with open(EMAIL_FILE, "w", encoding="utf-8") as f:
            f.write(email_input.email_content)
        logger.info(f"Email content saved to {EMAIL_FILE}")
        return JSONResponse(content={"message": "Email content saved successfully"})
    except Exception as e:
        logger.error(f"Error saving email: {str(e)}")
        return JSONResponse(content={"error": str(e)}, status_code=500)

@app.post("/run-workflow")
async def run_workflow_endpoint():
    """Run the vendor workflow and return relevant state data."""
    logger.info("Running workflow")
    try:
        result = run_workflow()
        logger.info("Workflow completed")
        return JSONResponse(content={"result": {
            "generated_emails": result.get("generated_emails", []),
            "update_status": result.get("update_status", ""),
            "update_status_dataset": result.get("update_status_dataset", "")
        }})
    except Exception as e:
        logger.error(f"Error running workflow: {str(e)}")
        return JSONResponse(content={"error": str(e)}, status_code=500)

@app.websocket("/ws/updates")
async def websocket_updates(websocket: WebSocket):
    """Push real-time CSV, status, and dataset status updates."""
    logger.info("WebSocket connection established")
    await websocket.accept()
    last_modified = 0
    last_status = ""
    last_status_dataset = ""
    try:
        while True:
            try:
                # Check for CSV file changes
                current_modified = os.path.getmtime(CSV_FILE)
                if current_modified > last_modified:
                    df = pd.read_csv(CSV_FILE)
                    last_modified = current_modified
                    logger.info("CSV file updated, sending data via WebSocket")
                    await websocket.send_json({"type": "csv", "data": df.to_dict(orient="records")})

                # Run workflow to get latest state
                state = run_workflow()
                current_status = state.get("update_status", "")
                current_status_dataset = state.get("update_status_dataset", "")

                # Send email status updates
                if current_status != last_status:
                    last_status = current_status
                    logger.info(f"Status updated: {current_status}")
                    await websocket.send_json({"type": "status", "data": current_status})

                # Send dataset status updates
                if current_status_dataset != last_status_dataset:
                    last_status_dataset = current_status_dataset
                    logger.info(f"Dataset status updated: {current_status_dataset}")
                    await websocket.send_json({"type": "status_dataset", "data": current_status_dataset})

                await asyncio.sleep(1)
            except Exception as e:
                logger.error(f"WebSocket error: {str(e)}")
                await websocket.send_json({"type": "error", "data": str(e)})
                await asyncio.sleep(1)
    except Exception as e:
        logger.error(f"WebSocket connection error: {str(e)}")
    finally:
        logger.info("WebSocket connection closed")
        await websocket.close()

if __name__ == "__main__":
    import uvicorn
    logger.info("Starting FastAPI server")
    uvicorn.run(app, host="0.0.0.0", port=8000)