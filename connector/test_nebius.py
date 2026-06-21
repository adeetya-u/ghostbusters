import urllib.request
import json
import os
import ssl

NEBIUS_API_KEY = os.environ.get("NEBIUS_API_KEY", "")

def _generate_blurb_nebius(chat_text: str) -> str:
    if not chat_text.strip():
        return "No message."
    url = "https://api.studio.nebius.ai/v1/chat/completions"
    headers = {
        "Authorization": f"Bearer {NEBIUS_API_KEY}",
        "Content-Type": "application/json"
    }
    data = {
        "model": "meta-llama/Meta-Llama-3.1-70B-Instruct",
        "messages": [
            {
                "role": "system",
                "content": "You are a helpful assistant that generates a very brief (1-line) suggested response for an iMessage. Return ONLY the suggested response text, with no quotes or extra formatting."
            },
            {
                "role": "user",
                "content": f"Here is the last message I received: {chat_text}"
            }
        ],
        "max_tokens": 50,
        "temperature": 0.5
    }
    
    req = urllib.request.Request(url, data=json.dumps(data).encode('utf-8'), headers=headers, method='POST')
    try:
        ctx = ssl.create_default_context()
        ctx.check_hostname = False
        ctx.verify_mode = ssl.CERT_NONE
        with urllib.request.urlopen(req, context=ctx) as response:
            result = json.loads(response.read().decode('utf-8'))
            return result['choices'][0]['message']['content'].strip()
    except Exception as e:
        return f"Error: {e}"

print(_generate_blurb_nebius("Hey, are we still on for dinner tomorrow?"))
