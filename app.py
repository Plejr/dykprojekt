import os
import sqlite3
import requests
from flask import Flask, request, jsonify, render_template_string
import httpx
from openai import OpenAI
from dotenv import load_dotenv

# Načtení proměnných prostředí (lokálně z .env, na serveru automaticky)
load_dotenv()

app = Flask(__name__)

# Nastavení AI přesně podle tvého zadání
api_key = os.environ.get("OPENAI_API_KEY")
base_url = os.environ.get("OPENAI_BASE_URL", "https://kurim.ithope.eu/v1")

client = OpenAI(
    api_key=api_key,
    base_url=base_url,
    http_client=httpx.Client(verify=False)
)

# Inicializace SQLite databáze
def init_db():
    conn = sqlite3.connect('knihovna.db')
    c = conn.cursor()
    # Tabulka pro uložené manhwy a jejich skóre (1-10)
    c.execute('''CREATE TABLE IF NOT EXISTS manhwa
                 (id INTEGER PRIMARY KEY AUTOINCREMENT, title TEXT, score INTEGER)''')
    conn.commit()
    conn.close()

init_db()

# Jednoduchý HTML vzhled (abys to mohl rovnou zkoušet v prohlížeči)
HTML_TEMPLATE = """
<!DOCTYPE html>
<html lang="cs">
<head>
    <meta charset="UTF-8">
    <title>Moje Manhwa AI Knihovna</title>
    <style>
        body { font-family: Arial, sans-serif; margin: 40px; max-width: 800px; }
        .box { border: 1px solid #ccc; padding: 20px; margin-bottom: 20px; border-radius: 8px; }
        button { padding: 10px 15px; background: #007bff; color: white; border: none; border-radius: 4px; cursor: pointer; }
        button:hover { background: #0056b3; }
        input { padding: 8px; margin-right: 10px; }
    </style>
</head>
<body>
    <h1>📚 Moje Manhwa Knihovna</h1>
    
    <div class="box">
        <h3>Přidat přečtenou Manhwu</h3>
        <form action="/add" method="POST">
            <input type="text" name="title" placeholder="Název (např. Solo Leveling)" required>
            <input type="number" name="score" min="1" max="10" placeholder="Skóre (1-10)" required>
            <button type="submit">Přidat do knihovny</button>
        </form>
    </div>

    <div class="box">
        <h3>Získat AI doporučení</h3>
        <p>AI se podívá na tvé oblíbené manhwy a vybere ti z reálné databáze něco nového.</p>
        <form action="/recommend" method="GET">
            <button type="submit">Doporuč mi další Manhwu!</button>
        </form>
    </div>
</body>
</html>
"""

@app.route('/')
def index():
    return render_template_string(HTML_TEMPLATE)

@app.route('/add', methods=['POST'])
def add_manhwa():
    title = request.form.get('title')
    score = request.form.get('score')
    
    conn = sqlite3.connect('knihovna.db')
    c = conn.cursor()
    c.execute("INSERT INTO manhwa (title, score) VALUES (?, ?)", (title, int(score)))
    conn.commit()
    conn.close()
    
    return f"Úspěšně přidáno: {title} se skórem {score}/10! <br><a href='/'>Zpět</a>"

@app.route('/recommend', methods=['GET'])
def recommend():
    # 1. Zjistíme, co se ti líbí (skóre 8 a více)
    conn = sqlite3.connect('knihovna.db')
    c = conn.cursor()
    c.execute("SELECT title FROM manhwa WHERE score >= 8")
    favorites = [row[0] for row in c.fetchall()]
    conn.close()

    if not favorites:
        return "Zatím nemáš žádné oblíbené manhwy se skórem 8 a vyšším. Přidej nějaké! <br><a href='/'>Zpět</a>"

    # 2. RAG princip: Stáhneme si aktuální populární manhwy z veřejného Jikan API, aby si AI nevymýšlelo
    try:
        jikan_url = "https://api.jikan.moe/v4/manga?type=manhwa&order_by=popularity&sort=desc&limit=15"
        response = requests.get(jikan_url)
        real_manhwas = response.json().get('data', [])
        
        # Připravíme textový seznam reálných manhw pro AI
        context_text = ""
        for m in real_manhwas:
            title = m.get('title', 'Neznámý název')
            synopsis = m.get('synopsis', 'Bez popisu')[:300] # Ořízneme kvůli délce
            context_text += f"- {title}: {synopsis}...\n"
    except Exception as e:
        return f"Chyba při stahování dat z API: {e}"

    # 3. Zkonstruujeme chytrý prompt pro tvé AI
    prompt = f"""
    Jsi expert na manhwy. Uživatel má velmi rád tyto manhwy: {', '.join(favorites)}.
    
    Zde je seznam existujících manhw z naší databáze:
    {context_text}
    
    Vyber z tohoto seznamu 2 nejlepší manhwy, které by se uživateli mohly líbit na základě jeho vkusu.
    Nesmíš si vymýšlet žádné názvy, vybírej striktně jen ze seznamu výše! 
    Odpověz česky a stručně vysvětli, proč mu je doporučuješ.
    """

    # 4. Zavoláme Kurim AI (model gemma3:27b podle zadání)
    try:
        odpoved = client.chat.completions.create(
            model="gemma3:27b",
            messages=[{"role": "user", "content": prompt}]
        )
        ai_text = odpoved.choices[0].message.content
        
        # Zobrazíme výsledek
        return f"<h2>Tvé AI Doporučení:</h2><p style='white-space: pre-wrap;'>{ai_text}</p><br><a href='/'>Zpět</a>"
    
    except Exception as e:
        return f"Chyba při komunikaci s AI: {e}"

if __name__ == '__main__':
    # Spuštění aplikace na portu ze zadání (nebo 5000 jako výchozí)
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=True)
