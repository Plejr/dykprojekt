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
    for i in range(20):
        try:
            conn = get_db_connection()
            c = conn.cursor()
            c.execute('''CREATE TABLE IF NOT EXISTS manhwa 
                         (id SERIAL PRIMARY KEY, username TEXT, title TEXT, score INTEGER)''')
            conn.commit()
            conn.close()
            return
        except Exception:
            time.sleep(2)

# 2. MODERNÍ MOBILE-FRIENDLY HTML + JS
HTML_LAYOUT = """
<!DOCTYPE html>
<html lang="cs">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Manhwa AI Manager</title>
    <style>
        :root { --primary: #007bff; --success: #28a745; --bg: #0c0c0c; --card: #161616; --text: #eee; }
        body { font-family: 'Segoe UI', Roboto, sans-serif; background: var(--bg); color: var(--text); margin: 0; padding: 15px; }
        .container { max-width: 900px; margin: auto; }
        h1 { text-align: center; color: var(--primary); font-size: 2rem; margin-bottom: 20px; }
        
        /* Grid system pro mobily */
        .grid { display: grid; grid-template-columns: 1fr 1fr; gap: 15px; }
        @media (max-width: 600px) { .grid { grid-template-columns: 1fr; } }
        
        .box { background: var(--card); padding: 20px; border-radius: 12px; border: 1px solid #333; box-shadow: 0 4px 10px rgba(0,0,0,0.3); }
        h3 { margin-top: 0; border-left: 4px solid var(--primary); padding-left: 10px; font-size: 1.1rem; }
        
        input, button { width: 100%; padding: 12px; margin: 8px 0; border-radius: 8px; border: 1px solid #444; box-sizing: border-box; font-size: 1rem; }
        input { background: #222; color: white; }
        button { background: var(--primary); color: white; border: none; font-weight: bold; cursor: pointer; transition: 0.2s; }
        button:active { transform: scale(0.98); }
        
        .btn-rec { background: var(--success); }
        
        /* Historie Tabulka */
        .table-wrapper { overflow-x: auto; margin-top: 15px; }
        table { width: 100%; border-collapse: collapse; min-width: 400px; }
        th, td { padding: 12px; text-align: left; border-bottom: 1px solid #333; }
        th { color: var(--primary); font-size: 0.8rem; text-transform: uppercase; }
        .score { background: var(--success); padding: 2px 8px; border-radius: 10px; font-size: 0.9rem; }
        
        /* AI Doporučení sekce */
        #ai-result { margin-top: 15px; padding: 15px; background: #1e291e; border-left: 4px solid var(--success); display: none; white-space: pre-wrap; font-size: 0.95rem; }
        .loading { color: #888; font-style: italic; display: none; }
    </style>
</head>
<body>
    <div class="container">
        <h1>📚 Manhwa AI</h1>
        
        <div class="grid">
            <!-- Přidávání -->
            <div class="box">
                <h3>➕ Nový záznam</h3>
                <form action="/add" method="POST">
                    <input type="text" name="user" placeholder="Jméno (např. martin)" required>
                    <input type="text" name="title" placeholder="Název manhwy" required>
                    <input type="number" name="score" min="1" max="10" placeholder="Hodnocení (1-10)" required>
                    <button type="submit">Uložit do DB</button>
                </form>
            </div>
            
            <!-- AI Doporučení -->
            <div class="box">
                <h3>✨ AI Doporučení</h3>
                <input type="text" id="rec-user" placeholder="Zadej své jméno">
                <button onclick="getRecommendation()" class="btn-rec">Najít nové pecky</button>
                <div id="loading" class="loading">AI přemýšlí... (může to trvat 10s)</div>
                <div id="ai-result"></div>
            </div>
        </div>

        <div class="box" style="margin-top:20px;">
            <h3>📜 Historie čtení</h3>
            <div class="table-wrapper">
                <table>
                    <thead>
                        <tr><th>Kdo</th><th>Titul</th><th>Skóre</th></tr>
                    </thead>
                    <tbody>
                        {% for item in library %}
                        <tr>
                            <td>{{ item[1] }}</td>
                            <td>{{ item[2] }}</td>
                            <td><span class="score">{{ item[3] }}/10</span></td>
                        </tr>
                        {% endfor %}
                    </tbody>
                </table>
            </div>
        </div>
    </div>

    <script>
        async function getRecommendation() {
            const user = document.getElementById('rec-user').value.trim();
            const resultDiv = document.getElementById('ai-result');
            const loadingDiv = document.getElementById('loading');
            
            if(!user) { alert("Zadej jméno!"); return; }
            
            loadingDiv.style.display = 'block';
            resultDiv.style.display = 'none';
            
            try {
                const response = await fetch(`/api/recommend?user=${encodeURIComponent(user)}`);
                const data = await response.json();
                
                loadingDiv.style.display = 'none';
                resultDiv.style.display = 'block';
                
                if(data.error) {
                    resultDiv.innerHTML = `<span style="color:#ff4444">${data.error}</span>`;
                } else {
                    resultDiv.innerText = data.recommendation;
                }
            } catch (e) {
                loadingDiv.style.display = 'none';
                resultDiv.style.display = 'block';
                resultDiv.innerText = "Chyba při spojení se serverem.";
            }
        }
    </script>
</body>
</html>
"""

@app.route('/')
def home():
    conn = get_db_connection()
    c = conn.cursor()
    c.execute("SELECT * FROM manhwa ORDER BY id DESC")
    library = c.fetchall()
    conn.close()
    return render_template_string(HTML_LAYOUT, library=library)

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

# NOVÁ API CESTA PRO AJAX
@app.route('/api/recommend')
def api_recommend():
    user = request.args.get('user').strip().lower()
    conn = get_db_connection()
    c = conn.cursor()
    c.execute("SELECT title FROM manhwa WHERE username = %s", (user,))
    read = [r[0].lower() for r in c.fetchall()]
    c.execute("SELECT title FROM manhwa WHERE username = %s AND score >= 8", (user,))
    favs = [r[0] for r in c.fetchall()]
    conn.close()

    if not favs:
        return jsonify({"error": "Nemáš v DB oblíbené tituly se skóre 8+. Přidej je nejdřív!"})

    try:
        res = requests.get(f"https://api.jikan.moe/v4/top/manga?type=manhwa&page={random.randint(1,3)}", timeout=10)
        data = res.json().get('data', [])
        candidates = [f"{m['title']}: {m.get('synopsis','')[:200]}" for m in data if m['title'].lower() not in read]
        
        prompt = f"Uživatel {user} má rád {favs}. Vyber 3 z tohoto seznamu: {candidates[:15]}. Odpověz česky, Formát: Název - Proč se mu bude líbit."
        ai_res = client.chat.completions.create(model="gemma3:27b", messages=[{"role": "user", "content": prompt}])
        
        return jsonify({"recommendation": ai_res.choices[0].message.content})
    except Exception as e:
        return jsonify({"error": str(e)})

if __name__ == '__main__':
    init_db()
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)))
