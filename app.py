import os
from flask import Flask, render_template, request, jsonify
from openai import OpenAI
import httpx

app = Flask(__name__)

# Nastavení klienta podle tvých podkladů
client = OpenAI(
    api_key=os.environ.get("OPENAI_API_KEY", "tvuj-fallback-klic"),
    base_url=os.environ.get("OPENAI_BASE_URL", "https://kurim.ithope.eu/v1"),
    http_client=httpx.Client(verify=False) # Ignoruje SSL certifikát podle návodu
)

@app.route("/")
def index():
    return """
    <html>
        <head><title>Kurim AI Sample</title></head>
        <body style="font-family: sans-serif; max-width: 600px; margin: 50px auto;">
            <h2>Kurim AI Chat</h2>
            <input type="text" id="user_input" style="width: 80%; padding: 10px;" placeholder="Zeptej se na něco...">
            <button onclick="askAI()" style="padding: 10px;">Odeslat</button>
            <div id="response" style="margin-top: 20px; white-space: pre-wrap; border-top: 1px solid #ccc; padding-top: 10px;"></div>

            <script>
                async function askAI() {
                    const input = document.getElementById('user_input').value;
                    const resDiv = document.getElementById('response');
                    resDiv.innerText = 'Přemýšlím...';
                    
                    const response = await fetch('/ask', {
                        method: 'POST',
                        headers: {'Content-Type': 'application/json'},
                        body: JSON.stringify({prompt: input})
                    });
                    const data = await response.json();
                    resDiv.innerText = data.answer;
                }
            </script>
        </body>
    </html>
    """

@app.route("/ask", methods=["POST"])
def ask():
    user_prompt = request.json.get("prompt")
    try:
        completion = client.chat.completions.create(
            model="gemma3:27b",
            messages=[{"role": "user", "content": user_prompt}]
        )
        answer = completion.choices[0].message.content
    except Exception as e:
        answer = f"Chyba: {str(e)}"
    
    return jsonify({"answer": answer})

if __name__ == "__main__":
    # Port z proměnné prostředí, jinak 5000
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)