import os
import requests
import httpx
import random
import time
import psycopg2
import sqlite3
from flask import Flask, request, render_template_string, jsonify
from openai import OpenAI

app = Flask(__name__)


client = OpenAI(
    api_key=os.environ.get("OPENAI_API_KEY"),
    base_url=os.environ.get("OPENAI_BASE_URL", "https://kurim.ithope.eu/v1"),
    http_client=httpx.Client(verify=False)
)


POSTGRES_URL = os.environ.get("DATABASE_URL", "postgresql://postgres:heslo123@db:5432/manhwadb")

TEMP_DB_PATH = "/tmp/user_history.db"

def get_pg_conn():
    return psycopg2.connect(POSTGRES_URL)

def get_temp_conn():
    return sqlite3.connect(TEMP_DB_PATH)

def init_db():
    """Inicializuje obě databáze."""
 
    for i in range(20):
        try:
            conn = get_pg_conn()
            c = conn.cursor()
            c.execute('''CREATE TABLE IF NOT EXISTS manhwa_catalog 
                         (id SERIAL PRIMARY KEY, title TEXT UNIQUE, synopsis TEXT)''')
            conn.commit()
            conn.close()
            print("Postgres (Katalog) připraven.")
            break
        except Exception as e:
            print(f"Čekám na Postgres... {e}")
            time.sleep(2)
            

    conn = get_temp_conn()
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS manhwa 
                 (id INTEGER PRIMARY KEY AUTOINCREMENT, username TEXT, title TEXT, score INTEGER)''')
    conn.commit()
    conn.close()
    print("SQLite (Dočasná historie) připravena v /tmp.")

def refresh_catalog_if_needed():
    """Naplní katalog z internetu, pokud je prázdný."""
    conn = get_pg_conn()
    c = conn.cursor()
    c.execute("SELECT COUNT(*) FROM manhwa_catalog")
    count = c.fetchone()[0]
    
    if count < 50:
        try:
            for page in [1, 2]:
                res = requests.get(f"https://api.jikan.moe/v4/top/manga?type=manhwa&page={page}", timeout=10)
                items = res.json().get('data', [])
                for item in items:
                    c.execute("INSERT INTO manhwa_catalog (title, synopsis) VALUES (%s, %s) ON CONFLICT (title) DO NOTHING", 
                              (item.get('title'), item.get('synopsis', 'Popis chybí.')))
            conn.commit()
        except Exception as e:
            print(f"Chyba při plnění katalogu: {e}")
    conn.close()


HTML_LAYOUT = """
<!DOCTYPE html>
<html lang="cs">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Manhwa AI Local Manager</title>
    <style>
        :root { --primary: #007bff; --success: #28a745; --bg: #0c0c0c; --card: #161616; --text: #eee; --warning: #ffaa00; }
        body { font-family: 'Segoe UI', Roboto, sans-serif; background: var(--bg); color: var(--text); margin: 0; padding: 15px; }
        .container { max-width: 900px; margin: auto; }
        h1 { text-align: center; color: var(--primary); margin-bottom: 5px; }
        .stats { font-size: 0.8rem; color: #888; text-align: center; margin-bottom: 20px; }
        .temp-alert { color: var(--warning); text-align: center; font-size: 0.85rem; margin-bottom: 20px; font-style: italic; }
        
        .grid { display: grid; grid-template-columns: 1fr 1fr; gap: 15px; }
        @media (max-width: 600px) { .grid { grid-template-columns: 1fr; } }
        
        .box { background: var(--card); padding: 20px; border-radius: 12px; border: 1px solid #333; box-shadow: 0 4px 10px rgba(0,0,0,0.3); }
        h3 { margin-top: 0; border-left: 4px solid var(--primary); padding-left: 10px; font-size: 1.1rem; }
        
        input, button { width: 100%; padding: 12px; margin: 8px 0; border-radius: 8px; border: 1px solid #444; box-sizing: border-box; font-size: 1rem; }
        input { background: #222; color: white; }
        button { background: var(--primary); color: white; border: none; font-weight: bold; cursor: pointer; transition: 0.2s; }
        button:active { transform: scale(0.98); }
        
        .btn-rec { background: var(--success); }
        
        #ai-result { margin-top: 15px; padding: 15px; background: #1e291e; border-left: 4px solid var(--success); display: none; white-space: pre-wrap; font-size: 0.95rem; }
        .loading { color: #888; font-style: italic; display: none; margin-top: 10px; }

        .table-wrapper { overflow-x: auto; margin-top: 15px; }
        table { width: 100%; border-collapse: collapse; }
        th, td { padding: 12px; text-align: left; border-bottom: 1px solid #333; }
        .score-tag { background: var(--success); padding: 2px 8px; border-radius: 10px; font-size: 0.9rem; }
    </style>
</head>
<body>
    <div class="container">
        <h1>📚 Manhwa AI Manager</h1>
        <p class="stats">V trvalé databázi: <strong>{{ catalog_count }}</strong> titulů</p>
        <p class="temp-alert">⚠️ Pozor: Seznam přečtených manhw se po restartu aplikace vymaže (uloženo v /tmp).</p>
        
        <div class="grid">
            <div class="box">
                <h3>➕ Přidat přečtené</h3>
                <form action="/add" method="POST">
                    <input type="text" name="user" placeholder="Tvé jméno" required>
                    <input type="text" name="title" placeholder="Název manhwy" required>
                    <input type="number" name="score" min="1" max="10" placeholder="Hodnocení (1-10)" required>
                    <button type="submit">Uložit do dočasné DB</button>
                </form>
            </div>
            
            <div class="box">
                <h3>✨ AI Doporučení</h3>
                <input type="text" id="rec-user" placeholder="Zadej své jméno">
                <button onclick="getRecommendation()" class="btn-rec">Najít pecky z katalogu</button>
                <div id="loading" class="loading">AI prohledává databázi...</div>
                <div id="ai-result"></div>
            </div>
        </div>

        <div class="box" style="margin-top:20px;">
            <h3>📜 Dočasná historie (aktivní relace)</h3>
            <div class="table-wrapper">
                <table>
                    <thead>
                        <tr><th>Uživatel</th><th>Titul</th><th>Skóre</th></tr>
                    </thead>
                    <tbody>
                        {% for item in library %}
                        <tr>
                            <td>{{ item[1] }}</td>
                            <td>{{ item[2] }}</td>
                            <td><span class="score-tag">{{ item[3] }}/10</span></td>
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
    refresh_catalog_if_needed()
  
    conn = get_temp_conn()
    c = conn.cursor()
    c.execute("SELECT * FROM manhwa ORDER BY id DESC")
    library = c.fetchall()
    conn.close()
    
   
    pg_conn = get_pg_conn()
    pg_c = pg_conn.cursor()
    pg_c.execute("SELECT COUNT(*) FROM manhwa_catalog")
    catalog_count = pg_c.fetchone()[0]
    pg_conn.close()
    
    return render_template_string(HTML_LAYOUT, library=library, catalog_count=catalog_count)

@app.route('/add', methods=['POST'])
def add():
    user = request.form.get('user').strip().lower()
    title = request.form.get('title').strip()
    score = request.form.get('score')
   
    conn = get_temp_conn()
    c = conn.cursor()
    c.execute("INSERT INTO manhwa (username, title, score) VALUES (?, ?, ?)", (user, title, int(score)))
    conn.commit()
    conn.close()
    return "<script>window.location.href='/';</script>"

@app.route('/api/recommend')
def api_recommend():
    user = request.args.get('user').strip().lower()
    
  
    conn = get_temp_conn()
    c = conn.cursor()
    c.execute("SELECT title FROM manhwa WHERE username = ?", (user,))
    read = [r[0].lower() for r in c.fetchall()]
    c.execute("SELECT title FROM manhwa WHERE username = ? AND score >= 8", (user,))
    favs = [r[0] for r in c.fetchall()]
    conn.close()

    if not favs:
        return jsonify({"error": "Musíš mít v dočasné historii aspoň jednu věc s hodnocením 8+."})

   
    pg_conn = get_pg_conn()
    pg_c = pg_conn.cursor()
    pg_c.execute("SELECT title, synopsis FROM manhwa_catalog ORDER BY RANDOM() LIMIT 20")
    db_items = pg_c.fetchall()
    pg_conn.close()

    candidates = [f"{m[0]}: {m[1][:200]}" for m in db_items if m[0].lower() not in read]

    try:
        prompt = f"Uživatel {user} má rád {favs}. Z naší databáze jsem vybral: {candidates}. Doporuč mu 3 nové kousky česky."
        ai_res = client.chat.completions.create(model="gemma3:27b", messages=[{"role": "user", "content": prompt}])
        return jsonify({"recommendation": ai_res.choices[0].message.content})
    except Exception as e:
        return jsonify({"error": str(e)})

if __name__ == '__main__':
    init_db()
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)))
