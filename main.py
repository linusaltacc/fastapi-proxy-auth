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
from typing import Dict, List, Optional


# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    filename='service.log'
)

app = FastAPI(docs_url=None, redoc_url=None)

# Lock for thread-safe writing to the log file
log_lock = Lock()

# Function to load API keys and server details from the .env file
def load_config(file_path):
    load_dotenv(file_path)

    api_keys = {}
    servers = {}
    
    # Extract API keys that start with "username_"
    for key, value in os.environ.items():
        if key.startswith("username_"):
            api_keys[key.split('username_')[1]] = value
        elif key.startswith("SERVER_"):
            server_name = key.split('SERVER_')[1].lower()
            server_config = value.split(',')
            servers[server_name] = {
                'url': server_config[0].strip(),
                'api_key': server_config[1].strip() if len(server_config) > 1 else None
            }

    # Ensure OpenAI is always present as the default server
    if 'openai' not in servers:
        servers['openai'] = {
            'url': "https://api.openai.com",
            'api_key': os.getenv("OPENAI_API_KEY")
        }

    return api_keys, servers

@lru_cache(maxsize=128)
def get_server_models(server_name: str) -> List[str]:
    server = SERVERS.get(server_name)
    if not server:
        return []

    with httpx.Client() as client:
        headers = {"Content-Type": "application/json"}
        if server['api_key']:
            headers["Authorization"] = f"Bearer {server['api_key']}"
        
        response = client.get(
            f"{server['url']}/v1/models",
            headers=headers,
        )
    
    if response.status_code == 200:
        return [model['id'] for model in response.json().get("data", [])]
    else:
        print(f"Error fetching models for {server_name}: {response.content}")
        return []

# Load configuration from .env
API_KEYS_FILE_PATH = ".env"
VALID_API_KEYS, SERVERS = load_config(API_KEYS_FILE_PATH)

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
    log_file_path = "./api_usage.json"
    username = next((user for user, key in VALID_API_KEYS.items() if key == api_key), None)
    with log_lock:
        try:
            # Read existing data
            try:
                with open(log_file_path, "r") as log_file:
                    log_data = json.load(log_file)
            except (FileNotFoundError, json.JSONDecodeError):
                log_data = []

            # Append new entry
            log_data.append({
                "timestamp": str(datetime.now()),
                "username": username,
                "api_key": api_key,
                "endpoint": endpoint,
                "request_headers": request_headers,
                "request_body": request_body
            })

            # Write updated data
            with open(log_file_path, "w") as log_file:
                json.dump(log_data, log_file, indent=2)
        except Exception as e:
            logging.error(f"Error writing to api_usage.json: {e}")

# Function to log invalid API usage
def log_invalid_api_usage(api_key, endpoint, request_headers="none", request_body="none"):
    log_file_path = "./invalid_api_usage.json"
    with log_lock:
        try:
            # Read existing data
            try:
                with open(log_file_path, "r") as log_file:
                    log_data = json.load(log_file)
            except (FileNotFoundError, json.JSONDecodeError):
                log_data = []

            # Append new entry
            log_data.append({
                "timestamp": str(datetime.now()),
                "api_key": api_key,
                "endpoint": endpoint,
                "request_headers": request_headers,
                "request_body": request_body
            })

            # Write updated data
            with open(log_file_path, "w") as log_file:
                json.dump(log_data, log_file, indent=2)
        except Exception as e:
            logging.error(f"Error writing to invalid_api_usage.json: {e}")

# Function to get the API usage logs
@app.api_route("/api_usage", methods=["GET"])
async def get_api_usage(request: Request):
    authorization: str = request.headers.get("Authorization", "")
    if not authorization.startswith("Bearer "):
        log_invalid_api_usage(api_key="no_api_key", endpoint="/validate")
        return Response("Invalid API Key format", status_code=400, headers={"Proxy-Status": "invalid_api_key_format"})

    api_key = authorization[7:]  # Remove the 'Bearer ' prefix
    
    if api_key in VALID_API_KEYS.values():
        log_file_path = "./api_usage.json"
        try:
            with log_lock:
                with open(log_file_path, "r") as log_file:
                    log_data = json.load(log_file)
            log_api_usage(api_key, "/api_usage")
            return JSONResponse({"data": log_data}, status_code=200)
        except Exception as e:
            logging.error(f"Error reading from api_usage.json: {e}")
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
        all_models = {server: get_server_models(server) for server in SERVERS}
        return JSONResponse(all_models, status_code=200)
    
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
    if not request_body:
        return Response("Access to this endpoint is restricted", status_code=400, headers={"Proxy-Status": "empty_request_body"})

    if api_key.replace('"', '') in VALID_API_KEYS.values():
        log_api_usage(api_key, request.url.path, request_headers=request_headers, request_body=request_body.decode())
        
        # Forward the request to all servers and return the first successful response
        for server_name, server in SERVERS.items():
            async with httpx.AsyncClient() as client:
                headers = {
                    "Content-Type": "application/json",
                }
                if server['api_key']:
                    headers["Authorization"] = f"Bearer {server['api_key']}"

                try:
                    response = await client.request(
                        method=request.method,
                        url=f"{server['url']}{request.url.path}",
                        headers=headers,
                        content=request_body,
                        timeout=30.0
                    )
                    if response.status_code == 200:
                        return Response(content=response.content.decode("utf-8"))
                except httpx.RequestError as e:
                    print(e)
                    return Response(status_code=500, content=f"Error: {e}")


        return Response("No server could process the request", status_code=500, headers={"Proxy-Status": "all_servers_failed"})

    else:
        log_invalid_api_usage(api_key, request.url.path)
        return Response("Invalid API Key", status_code=401, headers={"Proxy-Status": "invalid_api_key"})
