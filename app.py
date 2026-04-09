import os
import requests
import httpx
import random
import time
import psycopg2
import sqlite3  # Přidáno pro dočasnou databázi
from flask import Flask, request, render_template_string, jsonify
from openai import OpenAI

app = Flask(__name__)

# 1. KONFIGURACE
client = OpenAI(
    api_key=os.environ.get("OPENAI_API_KEY"),
    base_url=os.environ.get("OPENAI_BASE_URL", "https://kurim.ithope.eu/v1"),
    http_client=httpx.Client(verify=False)
)

# Cesty k DB
POSTGRES_URL = os.environ.get("DATABASE_URL", "postgresql://postgres:heslo123@db:5432/manhwadb")
SQLITE_PATH = "/tmp/history.db"  # Tady se data po restartu SMAŽOU

def get_pg_conn():
    return psycopg2.connect(POSTGRES_URL)

def get_sl_conn():
    return sqlite3.connect(SQLITE_PATH)

def init_db():
    # Inicializace TRVALÉHO katalogu (Postgres)
    for i in range(20):
        try:
            conn = get_pg_conn()
            c = conn.cursor()
            c.execute("CREATE TABLE IF NOT EXISTS manhwa_catalog (id SERIAL PRIMARY KEY, title TEXT UNIQUE, synopsis TEXT)")
            conn.commit()
            conn.close()
            break
        except Exception:
            time.sleep(2)
            
    # Inicializace DOČASNÉ historie (SQLite v /tmp)
    conn = get_sl_conn()
    c = conn.cursor()
    c.execute("CREATE TABLE IF NOT EXISTS manhwa (id INTEGER PRIMARY KEY AUTOINCREMENT, username TEXT, title TEXT, score INTEGER)")
    conn.commit()
    conn.close()

def refresh_catalog_if_needed():
    conn = get_pg_conn()
    c = conn.cursor()
    c.execute("SELECT COUNT(*) FROM manhwa_catalog")
    if c.fetchone()[0] < 50:
        try:
            for page in [1, 2]:
                res = requests.get(f"https://api.jikan.moe/v4/top/manga?type=manhwa&page={page}", timeout=10)
                items = res.json().get('data', [])
                for item in items:
                    c.execute("INSERT INTO manhwa_catalog (title, synopsis) VALUES (%s, %s) ON CONFLICT (title) DO NOTHING", 
                              (item.get('title'), item.get('synopsis', '')))
            conn.commit()
        except Exception as e: print(f"Katalog error: {e}")
    conn.close()

# --- HTML zůstává stejné, jen upravíme zobrazení ---
HTML_LAYOUT = """
... (stejné jako předtím, jen přidáme info o dočasnosti) ...
<p style="color: #ffaa00; text-align:center;">⚠️ Historie čtení je v /tmp (po restartu zmizí)</p>
"""

@app.route('/')
def home():
    refresh_catalog_if_needed()
    # Čtení z DOČASNÉ SQLite
    conn = get_sl_conn()
    c = conn.cursor()
    c.execute("SELECT * FROM manhwa ORDER BY id DESC LIMIT 10")
    library = c.fetchall()
    conn.close()
    
    # Čtení z TRVALÉHO Postgresu (jen pro počet)
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
    score = int(request.form.get('score'))
    # Ukládáme do DOČASNÉ SQLite
    conn = get_sl_conn()
    c = conn.cursor()
    c.execute("INSERT INTO manhwa (username, title, score) VALUES (?, ?, ?)", (user, title, score))
    conn.commit()
    conn.close()
    return "<script>window.location.href='/';</script>"

@app.route('/api/recommend')
def api_recommend():
    user = request.args.get('user').strip().lower()
    
    # 1. Zjistíme co uživatel četl z DOČASNÉ DB
    conn = get_sl_conn()
    c = conn.cursor()
    c.execute("SELECT title FROM manhwa WHERE username = ?", (user,))
    read = [r[0].lower() for r in c.fetchall()]
    c.execute("SELECT title FROM manhwa WHERE username = ? AND score >= 8", (user,))
    favs = [r[0] for r in c.fetchall()]
    conn.close()

    if not favs: return jsonify({"error": "Přidej aspoň jednu oblíbenou (8+)."})

    # 2. Vybereme kandidáty z TRVALÉHO katalogu
    pg_conn = get_pg_conn()
    pg_c = pg_conn.cursor()
    pg_c.execute("SELECT title, synopsis FROM manhwa_catalog ORDER BY RANDOM() LIMIT 20")
    db_items = pg_c.fetchall()
    pg_conn.close()

    candidates = [f"{m[0]}: {m[1][:200]}" for m in db_items if m[0].lower() not in read]

    try:
        prompt = f"Uživatel má rád {favs}. Doporuč 3 manhwy z: {candidates}. Česky."
        ai_res = client.chat.completions.create(model="gemma3:27b", messages=[{"role": "user", "content": prompt}])
        return jsonify({"recommendation": ai_res.choices[0].message.content})
    except Exception as e: return jsonify({"error": str(e)})

if __name__ == '__main__':
    init_db()
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)))
