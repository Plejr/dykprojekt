import os
import httpx
from flask import Flask, request, render_template_string
from openai import OpenAI

app = Flask(__name__)

# Inicializace klienta podle návodu Kurim AI (verify=False je klíčové)
client = OpenAI(
    api_key=os.environ.get("OPENAI_API_KEY", "tvuj-klic-bude-doplnen-serverem"),
    base_url=os.environ.get("OPENAI_BASE_URL", "https://kurim.ithope.eu/v1"),
    http_client=httpx.Client(verify=False)
)

# Vzhled stránky s automatickým přepínáním Dark/Light modu
HTML_TEMPLATE = """
<!DOCTYPE html>
<html lang="cs">
<head>
    <meta charset="UTF-8">
    <title>Kurim AI Asistent</title>
    <style>
        /* Společná nastavení */
        body { font-family: Arial, sans-serif; max-width: 600px; margin: 40px auto; padding: 20px; line-height: 1.5; }
        input[type="text"] { width: 75%; padding: 10px; font-size: 16px; border-radius: 4px; }
        button { padding: 10px 15px; font-size: 16px; border: none; border-radius: 4px; cursor: pointer; }
        .odpoved { margin-top: 20px; padding: 15px; border-radius: 4px; border-left: 5px solid; white-space: pre-wrap; }

        /* Nastavení pro LIGHT MODE (pokud nemáš nastavený dark mode v OS) */
        body { background-color: #ffffff; color: #333333; }
        input[type="text"] { border: 1px solid #cccccc; background-color: #ffffff; color: #333333; }
        button { background-color: #007bff; color: white; }
        button:hover { background-color: #0056b3; }
        .odpoved { background: #f8f9fa; border-left-color: #007bff; color: #333333; border: 1px solid #e1e1e1; }

        /* Nastavení pro DARK MODE (automaticky se aktivuje, pokud ho máš v OS) */
        @media (prefers-color-scheme: dark) {
            body { background-color: #1a1a1a; color: #e0e0e0; }
            input[type="text"] { border: 1px solid #444444; background-color: #2b2b2b; color: #e0e0e0; }
            button { background-color: #1e88e5; color: white; }
            button:hover { background-color: #1565c0; }
            .odpoved { background-color: #262626; border-left-color: #1e88e5; color: #e0e0e0; border: 1px solid #3d3d3d; }
            ::placeholder { color: #888888; }
        }
    </style>
</head>
<body>
    <h1>Můj Kurim AI Asistent 🤖🌑</h1>
    <form method="POST">
        <input type="text" name="dotaz" placeholder="Zeptej se na cokoliv..." required autofocus>
        <button type="submit">Odeslat</button>
    </form>
    {% if odpoved %}
        <div class="odpoved">{{ odpoved }}</div>
    {% endif %}
</body>
</html>
"""

@app.route("/", methods=["GET", "POST"])
def index():
    odpoved = ""
    if request.method == "POST":
        dotaz = request.form.get("dotaz")
        try:
            # Komunikace s Kurim AI modelem gemma3:27b
            ai_resp = client.chat.completions.create(
                model="gemma3:27b",
                messages=[{"role": "user", "content": dotaz}]
            )
            odpoved = ai_resp.choices[0].message.content
        except Exception as e:
            odpoved = f"Došlo k chybě při komunikaci s AI: {e}"
            
    return render_template_string(HTML_TEMPLATE, odpoved=odpoved)

if __name__ == "__main__":
    # Server Kurim AI vyžaduje, aby aplikace běžela na portu z proměnné prostředí PORT
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
