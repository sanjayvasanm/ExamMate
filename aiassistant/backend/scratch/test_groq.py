import os
from groq import Groq
from dotenv import load_dotenv

load_dotenv()

key = os.environ.get("GROQ_API_KEY")
print(f"Testing key: {key[:10]}...")

client = Groq(api_key=key)

try:
    chat_completion = client.chat.completions.create(
        messages=[
            {
                "role": "user",
                "content": "Say hello world",
            }
        ],
        model="llama-3.3-70b-versatile",
    )
    print("Groq Response:", chat_completion.choices[0].message.content)
except Exception as e:
    print("Groq Error:", e)
