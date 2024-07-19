import pytest
from openai import OpenAI
from pathlib import Path

@pytest.fixture
def client():
    return OpenAI(
        base_url='http://localhost:8081/v1',
        api_key='sk-your-api-key',
    )

def test_openai_chat_completions(client):
    response = client.chat.completions.create(
        model="gpt-3.5-turbo",
        messages=[
            {"role": "system", "content": "You are a helpful assistant."},
            {"role": "user", "content": "Who won the IPL in 2010?"},
        ],
    )
    assert response.choices[0].message.content, "Model did not return any response"

def test_openai_images_generate(client):
    response = client.images.generate(
        model="dall-e-3",
        prompt="A cute baby sea otter",
        size="1024x1024",
        quality="standard",
        n=1,
    )
    assert response.data[0].url is not None, "Image URL is missing"

def test_openai_audio_speech(client):
    speech_file_path = Path(__file__).parent / "speech.mp3"
    response = client.audio.speech.create(
        model="tts-1",
        voice="nova",
        input="Today is a wonderful day to build something people love!"
    )
    response.stream_to_file(speech_file_path)
    assert speech_file_path.exists(), "Speech file was not created"
    speech_file_path.unlink()  # Cleanup after test

def test_ollama_chat_completions(client):
    response = client.chat.completions.create(
        model="llama3:latest", # replace with model you have on your server
        messages=[
            {"role": "system", "content": "You are a helpful assistant."},
            {"role": "user", "content": "Who won the IPL in 2010?"},
        ],
    )
    assert response.choices[0].message.content, "Model did not return any response"