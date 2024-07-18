from openai import OpenAI

client = OpenAI(
    base_url = 'http://localhost:8081/v1',
    api_key='123',
)

response = client.chat.completions.create(
  model="phi3",
  messages=[
    {"role": "system", "content": "You are a helpful assistant."},
    {"role": "user", "content": "Who won the world series in 2020?"},
    {"role": "assistant", "content": "The LA Dodgers won in 2020."},
    {"role": "user", "content": "Where was it played?"}
  ]
)
print(response.choices[0].message.content)