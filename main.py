from fastapi import FastAPI, Request, Response, HTTPException
from fastapi.responses import JSONResponse
import os
import csv
from datetime import datetime
from threading import Lock
import logging
import httpx

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    filename='service.log'
)

app = FastAPI()

# Lock for thread-safe writing to the log file
log_lock = Lock()

# Function to load API keys and server details from the .env file
def load_config(file_path):
    api_keys = {}
    server_ip = ""
    server_port = ""

    try:
        with open(file_path, "r") as file:
            for line in file:
                line = line.strip()
                if line:
                    key, value = line.split('=')
                    if key.startswith("username_"):
                        api_keys[key.split('username_')[1]] = value
                    elif key == "SERVER_IP":
                        server_ip = value
                    elif key == "SERVER_PORT":
                        server_port = value
    except Exception as e:
        logging.error(f"Error reading configuration from file '{file_path}': {e}")
    
    return api_keys, server_ip, server_port

# Load configuration from .env
API_KEYS_FILE_PATH = ".env"
VALID_API_KEYS, SERVER_IP, SERVER_PORT = load_config(API_KEYS_FILE_PATH)

# Define a middleware function to log requests
@app.middleware("http")
async def log_requests(request: Request, call_next):
    # Log the request details
    log_line = f"Time: {datetime.now()}, Method: {request.method}, Path: {request.url.path}\n"
    logging.info(log_line)
    
    # Proceed with the request
    response = await call_next(request)
    return response

# Function to log API usage
def log_api_usage(api_key, endpoint, request_headers="none", request_body="none"):
    log_file_path = "./api_usage.csv"
    # Find the username by the given API key
    username = next((user for user, key in VALID_API_KEYS.items() if key == api_key), None)
    with log_lock:
        try:
            with open(log_file_path, "a", newline='') as log_file:
                csv_writer = csv.writer(log_file)
                # Log the datetime, username, API key, and endpoint
                csv_writer.writerow([datetime.now(), username, api_key, endpoint, request_headers, request_body])
        except Exception as e:
            logging.error(f"Error writing to api_usage.csv: {e}")

# Function to log invalid API usage
def log_invalid_api_usage(api_key, endpoint, request_headers="none", request_body="none"):
    log_file_path = "./invalid_api_usage.csv"
    with log_lock:
        try:
            with open(log_file_path, "a", newline='') as log_file:
                csv_writer = csv.writer(log_file)
                csv_writer.writerow([datetime.now(), api_key, endpoint, request_headers, request_body])
        except Exception as e:
            logging.error(f"Error writing to invalid_api_usage.csv: {e}")

# Function to validate the API key
@app.api_route("/validate", methods=["GET", "POST"])
async def validate_api_key(request: Request):
    authorization: str = request.headers.get("Authorization", "")
    
    if not authorization.startswith("Bearer "):
        log_invalid_api_usage(api_key="no_api_key", endpoint="/validate")
        return Response("Invalid API Key format", status_code=400, headers={"Proxy-Status": "invalid_api_key_format"})

    api_key = authorization[7:]  # Remove the 'Bearer ' prefix
    
    if api_key in VALID_API_KEYS.values():
        log_api_usage(api_key, "/validate")
        return Response("API Key validation successful", status_code=200, headers={"Proxy-Status": "valid_api_key"})
    else:
        log_invalid_api_usage(api_key, "/validate")
        return Response("Invalid API Key", status_code=401, headers={"Proxy-Status": "invalid_api_key"})
    
# Function to get the API usage logs
@app.api_route("/api_usage", methods=["GET"])
async def get_api_usage(request: Request):
    authorization: str = request.headers.get("Authorization", "")
    if not authorization.startswith("Bearer "):
        log_invalid_api_usage(api_key="no_api_key", endpoint="/validate")
        return Response("Invalid API Key format", status_code=400, headers={"Proxy-Status": "invalid_api_key_format"})

    api_key = authorization[7:]  # Remove the 'Bearer ' prefix
    

    if api_key in VALID_API_KEYS.values():
        # Log API usage after successful validation
            log_file_path = "./api_usage.csv"
            try:
                with log_lock:
                    with open(log_file_path, mode="r", newline='') as csvfile:
                        reader = csv.reader(csvfile)
                        # Skipping header row, adjust if your CSV doesn't have one
                        next(reader, None)
                        entries = [{"timestamp": row[0], "username": row[1], "endpoint": row[3], "request_header": row[4], "request_body": row[5]} for row in reader]
                log_api_usage(api_key, "/api_usage")
                return JSONResponse({"data" : entries}, status_code=200) # Return usage data.
            except Exception as e:
                logging.error(f"Error reading from api_usage.csv: {e}")
                raise HTTPException(status_code=500, detail="Failed to read usage data")
    else:
        log_invalid_api_usage(api_key, "/api_usage")
        return Response("Invalid API Key", status_code=401, headers={"Proxy-Status": "invalid_api_key"})

@app.api_route("/ping", methods=["GET"])
async def ping(request: Request):
    return Response("Pong", status_code=200)

# Proxy endpoint
@app.api_route("/{path:path}", methods=["GET", "POST", "PUT", "DELETE"])
async def proxy(request: Request):
    authorization: str = request.headers.get("Authorization", "")
    request_headers = dict(request.headers)
    request_body = await request.body()

    if not authorization.startswith("Bearer "):
        log_invalid_api_usage(api_key="no_api_key", endpoint=request.url.path, request_headers=request_headers, request_body=request_body)
        return Response("Invalid API Key format", status_code=400, headers={"Proxy-Status": "invalid_api_key_format"})

    api_key = authorization[7:]  # Remove the 'Bearer ' prefix
    
    if api_key in VALID_API_KEYS.values():

        log_api_usage(api_key, request.url.path, request_headers=request_headers, request_body=request_body)

        # Forward the request to the actual server
        async with httpx.AsyncClient() as client:
            response = await client.request(
                method=request.method,
                url=f"http://{SERVER_IP}:{SERVER_PORT}{request.url.path}",
                headers=request.headers,
                content=await request.body()
            )
        
        return Response(content=response.content, status_code=response.status_code, headers=dict(response.headers))
    else:
        log_invalid_api_usage(api_key, request.url.path)
        return Response("Invalid API Key", status_code=401, headers={"Proxy-Status": "invalid_api_key"})
