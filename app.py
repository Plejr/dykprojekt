import os
import requests
import httpx
import random
import time
import psycopg2
from flask import Flask, request, render_template_string, jsonify
from openai import OpenAI

app = Flask(__name__)

# 1. KONFIGURACE AI
client = OpenAI(
    api_key=os.environ.get("OPENAI_API_KEY"),
    base_url=os.environ.get("OPENAI_BASE_URL", "https://kurim.ithope.eu/v1"),
    http_client=httpx.Client(verify=False)
)

DATABASE_URL = os.environ.get("DATABASE_URL", "postgresql://postgres:heslo123@db:5432/manhwadb")

def get_db_connection():
    return psycopg2.connect(DATABASE_URL)

def init_db():
    """Vytvoří tabulky pro uživatele i pro globální katalog manhwa."""
    for i in range(20):
        try:
            conn = get_db_connection()
            c = conn.cursor()
            # Tabulka pro historii uživatelů
            c.execute('''CREATE TABLE IF NOT EXISTS manhwa 
                         (id SERIAL PRIMARY KEY, username TEXT, title TEXT, score INTEGER)''')
            # Tabulka pro stažený katalog z internetu
            c.execute('''CREATE TABLE IF NOT EXISTS manhwa_catalog 
                         (id SERIAL PRIMARY KEY, title TEXT UNIQUE, synopsis TEXT)''')
            conn.commit()
            conn.close()
            return
        except Exception:
            time.sleep(2)

def refresh_catalog_if_needed():
    """Pokud je v katalogu málo dat, stáhne nové z Jikan API a uloží je do DB."""
    conn = get_db_connection()
    c = conn.cursor()
    c.execute("SELECT COUNT(*) FROM manhwa_catalog")
    count = c.fetchone()[0]
    
    if count < 50:
        try:
            # Stáhneme top manhwy (strana 1 a 2)
            for page in [1, 2]:
                res = requests.get(f"https://api.jikan.moe/v4/top/manga?type=manhwa&page={page}", timeout=10)
                items = res.json().get('data', [])
                for item in items:
                    title = item.get('title')
                    synopsis = item.get('synopsis', 'Popis chybí.')
                    # INSERT IGNORE ekvivalent v Postgresu
                    c.execute("INSERT INTO manhwa_catalog (title, synopsis) VALUES (%s, %s) ON CONFLICT (title) DO NOTHING", (title, synopsis))
            conn.commit()
        except Exception as e:
            print(f"Chyba při plnění katalogu: {e}")
    conn.close()

# --- HTML ŠABLONA (zůstává stejná jako v minulé verzi) ---
HTML_LAYOUT = """
<!DOCTYPE html>
<html lang="cs">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Manhwa AI Local Manager</title>
    <style>
        :root { --primary: #007bff; --success: #28a745; --bg: #0c0c0c; --card: #161616; --text: #eee; }
        body { font-family: sans-serif; background: var(--bg); color: var(--text); margin: 0; padding: 15px; }
        .container { max-width: 900px; margin: auto; }
        .grid { display: grid; grid-template-columns: 1fr 1fr; gap: 15px; }
        @media (max-width: 600px) { .grid { grid-template-columns: 1fr; } }
        .box { background: var(--card); padding: 20px; border-radius: 12px; border: 1px solid #333; margin-bottom: 20px; }
        input, button { width: 100%; padding: 12px; margin: 8px 0; border-radius: 8px; border: 1px solid #444; box-sizing: border-box; }
        button { background: var(--primary); color: white; border: none; font-weight: bold; cursor: pointer; }
        .btn-rec { background: var(--success); }
        #ai-result { margin-top: 15px; padding: 15px; background: #1e291e; border-left: 4px solid var(--success); display: none; white-space: pre-wrap; }
        .stats { font-size: 0.8rem; color: #888; text-align: center; margin-bottom: 10px; }
    </style>
</head>
<body>
    <div class="container">
        <h1>📚 Manhwa Database AI</h1>
        <p class="stats">V lokální databázi je uloženo: <strong>{{ catalog_count }}</strong> titulů</p>
        
        <div class="grid">
            <div class="box">
                <h3>➕ Moje historie</h3>
                <form action="/add" method="POST">
                    <input type="text" name="user" placeholder="Jméno" required>
                    <input type="text" name="title" placeholder="Název" required>
                    <input type="number" name="score" min="1" max="10" placeholder="Skóre" required>
                    <button type="submit">Uložit</button>
                </form>
            </div>
            <div class="box">
                <h3>✨ AI Doporučení z DB</h3>
                <input type="text" id="rec-user" placeholder="Tvé jméno">
                <button onclick="getRecommendation()" class="btn-rec">Doporučit z mého katalogu</button>
                <div id="ai-result"></div>
            </div>
        </div>

        <div class="box">
            <h3>📜 Poslední záznamy</h3>
            <table style="width:100%; border-collapse: collapse;">
                {% for item in library %}
                <tr><td style="padding:8px; border-bottom:1px solid #333;">{{ item[1] }}: <strong>{{ item[2] }}</strong> ({{ item[3] }}/10)</td></tr>
                {% endfor %}
            </table>
        </div>
    </div>

    <script>
        async function getRecommendation() {
            const user = document.getElementById('rec-user').value.trim();
            const resultDiv = document.getElementById('ai-result');
            if(!user) return;
            resultDiv.style.display = 'block';
            resultDiv.innerText = "AI prohledává tvou databázi...";
            
            const response = await fetch(`/api/recommend?user=${encodeURIComponent(user)}`);
            const data = await response.json();
            resultDiv.innerText = data.error || data.recommendation;
        }
    </script>
</body>
</html>
"""

@app.route('/')
def home():
    refresh_catalog_if_needed() # Zkontroluje/naplní katalog při návštěvě
    conn = get_db_connection()
    c = conn.cursor()
    c.execute("SELECT * FROM manhwa ORDER BY id DESC LIMIT 10")
    library = c.fetchall()
    c.execute("SELECT COUNT(*) FROM manhwa_catalog")
    catalog_count = c.fetchone()[0]
    conn.close()
    return render_template_string(HTML_LAYOUT, library=library, catalog_count=catalog_count)

@app.route('/add', methods=['POST'])
def add():
    user = request.form.get('user').strip().lower()
    title = request.form.get('title').strip()
    score = request.form.get('score')
    conn = get_db_connection()
    c = conn.cursor()
    c.execute("INSERT INTO manhwa (username, title, score) VALUES (%s, %s, %s)", (user, title, int(score)))
    conn.commit()
    conn.close()
    return "<script>window.location.href='/';</script>"

@app.route('/api/recommend')
def api_recommend():
    user = request.args.get('user').strip().lower()
    conn = get_db_connection()
    c = conn.cursor()
    
    # 1. Co uživatel četl
    c.execute("SELECT title FROM manhwa WHERE username = %s", (user,))
    read = [r[0].lower() for r in c.fetchall()]
    
    # 2. Co má rád
    c.execute("SELECT title FROM manhwa WHERE username = %s AND score >= 8", (user,))
    favs = [r[0] for r in c.fetchall()]
    
    # 3. Náhodný výběr kandidátů z NAŠÍ databáze (katalogu), které ještě nečetl
    c.execute("SELECT title, synopsis FROM manhwa_catalog ORDER BY RANDOM() LIMIT 20")
    db_items = c.fetchall()
    conn.close()

    if not favs:
        return jsonify({"error": "Musíš nejdřív přidat aspoň jednu oblíbenou věc (8+ bodů)."})

    candidates = [f"{m[0]}: {m[1][:200]}" for m in db_items if m[0].lower() not in read]

    try:
        prompt = f"Jsi expert. Uživatel {user} má rád {favs}. Z naší lokální DB jsem vybral tyto kandidáty: {candidates}. Vyber 3 nejlepší a česky napiš: Název - Proč."
        ai_res = client.chat.completions.create(model="gemma3:27b", messages=[{"role": "user", "content": prompt}])
        return jsonify({"recommendation": ai_res.choices[0].message.content})
    except Exception as e:
        return jsonify({"error": str(e)})

if __name__ == '__main__':
    init_db()
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)))
