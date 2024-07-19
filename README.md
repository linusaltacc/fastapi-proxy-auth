## FastAPI Proxy with API Key Validation for Ollama or any API

This repository sets up a FastAPI application to securely authenticate and proxy requests. The application includes API key validation with keys stored in a configuration file.


## Requirements

- Python 3.7+
- FastAPI
- Uvicorn
- httpx
- openai ( optional )

## Setup

1. **Clone the Repository**

    ```bash
    git clone https://github.com/linusaltacc/fastapi-proxy-auth.git
    cd fastapi-proxy-auth
    ```

2. **Install Dependencies**

    ```bash
    pip install fastapi uvicorn httpx openai
    ```

3. **Configure API Keys**

    Create a `.env` file in the root directory and add your API keys in the following format:

    ```
    username_name1=api_key1
    username_name2=api_key2
    ```
    **Mention `username_` before the username to differentiate from `SERVER_IP` and `SERVER_PORT`**

4. **Set Environment Variables**

    Set the `SERVER_IP` and `SERVER_PORT` environment variables to the IP and port of the server to which the valid requests should be proxied.

    ```bash
    export SERVER_IP=your_server_ip
    export SERVER_PORT=your_server_port
    ```
    or mention in `.env` file.
    ```
    SERVER_IP=your_server_ip
    SERVER_PORT=your_server_port
    ```

## Running the Application

Run the FastAPI application using Uvicorn:

```bash
uvicorn main:app --host 0.0.0.0 --port 8081
```

The application will start on port 8081.

## Usage

### Proxying Requests

Send requests to any endpoint, and the application will validate the API key and proxy valid requests:

```bash
curl -i http://localhost:8081/your/endpoint -H "Authorization: Bearer your_api_key"
```

## Code Overview

### `main.py`

This is the main file containing the FastAPI application. It includes the following key functionalities:

- **Loading API Keys**: The `load_api_keys` function reads the API keys from the `.env` file.
- **Logging**: The application logs request details and API usage to log files.
- **API Key Validation**: The `/validate` endpoint validates the API keys.
- **Traffic Analysis Endpoint**: Access API traffic and usage analytics by navigating to `/api_usage`. 
- **Proxying Requests**: The root endpoint (`/{path:path}`) proxies valid requests to the configured server.
- **OpenAI Compatable for Ollama**: Example usage of the OpenAI API.

## OpenAI Compatable Example for ollama API

This repository also includes an example of using the OpenAI API. Ensure you have the `openai` package installed and set up correctly.

### Example Code

```python
from openai import OpenAI

client = OpenAI(
    base_url='http://localhost:8081/v1',
    api_key='sk-ollama-your-api-key',
)

response = client.chat.completions.create(
    model="model_name",
    messages=[
        {"role": "system", "content": "You are a helpful assistant."},
        {"role": "user", "content": "Who won the IPL in 2010?"}
    ]
)
print(response.choices[0].message.content)
```

## Generating a Secure API Key

To generate a secure API key, use the following command:

```bash
echo "your_prefix-$(openssl rand -hex 16)"
```

This will generate a key like `your_prefix-78834bcb4c76d97d35a0c1acd0d938c6`. Copy the generated key and add it to your `.env` file.

## Testing API Key Authentication

### Test with Incorrect API Key

Send a request with an incorrect API key. This should return a `401 Unauthorized` status:

```bash
curl -i http://localhost:8081 -H "Authorization: Bearer wrong_api_key"
```

### Test with Correct API Key

Send a request with the correct API key. This should return a `200 OK` status:

