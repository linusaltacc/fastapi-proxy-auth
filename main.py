from fastapi import FastAPI, Request, Response, HTTPException
from fastapi.responses import JSONResponse
import os
import csv
from datetime import datetime
from threading import Lock
import logging
import json
import httpx
from dotenv import load_dotenv
import openai
from functools import lru_cache


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
    # Load environment variables from .env file
    load_dotenv(file_path)

    api_keys = {}
    server_ip = os.getenv("SERVER_IP", False)
    server_port = os.getenv("SERVER_PORT", False)
    openai_endpoint = "https://api.openai.com"
    openai_api_key = os.getenv("OPENAI_API_KEY", False)

    # Extract API keys that start with "username_"
    for key in os.environ:
        if key.startswith("username_"):
            api_keys[key.split('username_')[1]] = os.getenv(key)

    return api_keys, server_ip, server_port, openai_endpoint, openai_api_key

@lru_cache(maxsize=128)
def get_openai_models():
    if OPENAI_API_KEY:
        with httpx.Client() as client:
            response = client.get(
                OPENAI_ENDPOINT+'/v1/models',
                headers={
                    "Authorization": f"Bearer {OPENAI_API_KEY}",
                    "Content-Type": "application/json"
                },
            )
        return json.loads(response.content).get("data", [])
    else:
        return []

@lru_cache(maxsize=128)
def get_ollama_models():
    if SERVER_IP and SERVER_PORT:
        with httpx.Client() as client:
            response = client.get(
                url=f"http://{SERVER_IP}:{SERVER_PORT}/api/tags",
            )
        return json.loads(response.content).get("models", [])
    else:
        return []
    
# Load configuration from .env
API_KEYS_FILE_PATH = ".env"
VALID_API_KEYS, SERVER_IP, SERVER_PORT, OPENAI_ENDPOINT, OPENAI_API_KEY = load_config(API_KEYS_FILE_PATH)
openai_key_provided, ollama_server_provided = bool(OPENAI_API_KEY), bool(SERVER_IP)
OPENAI_MODELS = [model['id'] for model in get_openai_models() if openai_key_provided] 
OLLAMA_MODELS = [model['name'] for model in get_ollama_models() if ollama_server_provided]

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

@app.api_route("/service_log", methods=["GET"])
async def get_service_log(request: Request):
    authorization: str = request.headers.get("Authorization", "")
    if not authorization:
        log_invalid_api_usage(api_key="no_api_key", endpoint="/service_log")
        return Response("Invalid API Key format", status_code=400, headers={"Proxy-Status": "invalid_api_key_format"})
    api_key = authorization[7:]

    if api_key in VALID_API_KEYS.values():
        log_api_usage(api_key, "/service_log")
        try:
            with open("service.log", "r") as log_file:
                log_data = log_file.read()
            return Response(log_data, status_code=200)
        except Exception as e:
            logging.error(f"Error reading service.log: {e}")
            raise HTTPException(status_code=500, detail="Failed to read service log")
    else:
        log_invalid_api_usage(api_key, "/service_log")
        return Response("Invalid API Key", status_code=401, headers={"Proxy-Status": "invalid_api"})

@app.api_route("/models", methods=["GET"])
async def get_models(request: Request):
    authorization: str = request.headers.get("Authorization", "")

    if not authorization:
        log_invalid_api_usage(api_key="no_api_key", endpoint="/models")
        return Response("Invalid API Key format", status_code=400, headers={"Proxy-Status": "invalid_api_key_format"})
    api_key = authorization[7:]  # Remove the 'Bearer ' prefix

    if api_key.replace('"', '') in VALID_API_KEYS.values():
        log_api_usage(api_key, "/models")
        return JSONResponse({"openai_models": OPENAI_MODELS, "ollama_models": OLLAMA_MODELS}, status_code=200)
    
    else:
        log_invalid_api_usage(api_key, "/models")
        return Response("Invalid API Key", status_code=401, headers={"Proxy-Status": "invalid_api"})
    
@app.api_route("/ping", methods=["GET"])
async def ping(request: Request):
    return Response("Pong", status_code=200)

@app.api_route("/", methods=["GET"])
async def index(request: Request):
    return Response('{"status": "OK"}', status_code=200)

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

    if request_body:
        model_name = json.loads(request_body).get("model", "")
    else:
        return Response("Access to this endpoint is restricted", status_code=400, headers={"Proxy-Status": "empty_request_body"})

    if api_key.replace('"', '') in VALID_API_KEYS.values():
        if model_name in OPENAI_MODELS:
            log_api_usage(api_key, request.url.path, request_headers=request_headers, request_body=request_body.decode())
            async with httpx.AsyncClient() as client:
                response = await client.post(
                    OPENAI_ENDPOINT+request.url.path,
                    headers={
                        "Content-Type": "application/json",
                        "Authorization": f"Bearer {OPENAI_API_KEY}"
                    },
                    data=request_body,
                    timeout=30.0 # default timeout in case of image/audio generation
                )
            return Response(content=response.content) # stream is not yet implemented
            
        elif model_name in OLLAMA_MODELS:
            log_api_usage(api_key, request.url.path, request_headers=request_headers, request_body=request_body.decode())

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
            return Response("Invalid Model Name. Check if the model exists with /models endpoints", status_code=400, headers={"Proxy-Status": "invalid_model"})

    else:
        log_invalid_api_usage(api_key, request.url.path)
        return Response("Invalid API Key", status_code=401, headers={"Proxy-Status": "invalid_api_key"})