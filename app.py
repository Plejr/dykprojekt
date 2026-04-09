import os
import requests
import httpx
import random
import time
import psycopg2
from flask import Flask, request, render_template_string
from openai import OpenAI

app = Flask(__name__)

# 1. KONFIGURACE AI (z environment)
client = OpenAI(
    api_key=os.environ.get("OPENAI_API_KEY"),
    base_url=os.environ.get("OPENAI_BASE_URL", "https://kurim.ithope.eu/v1"),
    http_client=httpx.Client(verify=False)
)

# 2. DATABÁZE (Retry loop podle zadání)
DATABASE_URL = os.environ.get("DATABASE_URL", "postgresql://student:heslo123@db:5432/manhwadb")

def get_db_connection():
    return psycopg2.connect(DATABASE_URL)

def init_db():
    """Čeká na start DB a vytvoří tabulku."""
    for i in range(10):
        try:
            conn = get_db_connection()
            c = conn.cursor()
            c.execute('''CREATE TABLE IF NOT EXISTS manhwa 
                         (id SERIAL PRIMARY KEY, username TEXT, title TEXT, score INTEGER)''')
            conn.commit()
            conn.close()
            print("DB připravena.")
            return
        except Exception as e:
            print(f"Čekám na DB... {e}")
            time.sleep(2)

# 3. HTML ŠABLONA (Beze změn, jen opraveno username v cyklu)
HTML_LAYOUT = """
<!DOCTYPE html>
<html lang="cs">
<head>
    <meta charset="UTF-8">
    <title>Manhwa AI Manager</title>
    <style>
        body { font-family: sans-serif; background: #0c0c0c; color: #eee; padding: 20px; }
        .container { max-width: 800px; margin: auto; }
        .box { background: #161616; padding: 20px; border-radius: 8px; margin-bottom: 20px; border: 1px solid #333; }
        input, button { padding: 10px; margin: 5px 0; width: 100%; border-radius: 4px; border: 1px solid #444; }
        button { background: #007bff; color: white; cursor: pointer; border: none; }
        table { width: 100%; border-collapse: collapse; }
        th, td { padding: 10px; border-bottom: 1px solid #333; text-align: left; }
    </style>
</head>
<body>
    <div class="container">
        <h1>📚 Manhwa AI Manager</h1>
        <div class="box">
            <form action="/add" method="POST">
                <input type="text" name="user" placeholder="Jméno" required>
                <input type="text" name="title" placeholder="Název Manhwy" required>
                <input type="number" name="score" min="1" max="10" placeholder="Skóre (1-10)" required>
                <button type="submit">Uložit</button>
            </form>
        </div>
        <div class="box">
            <form action="/recommend" method="GET">
                <input type="text" name="user" placeholder="Zadej jméno pro doporučení" required>
                <button type="submit" style="background: #28a745;">Najít pecky přes AI</button>
            </form>
        </div>
        <div class="box">
            <h3>Historie</h3>
            <table>
                {% for item in library %}
                <tr><td>{{ item[1] }}</td><td>{{ item[2] }}</td><td>{{ item[3] }}/10</td></tr>
                {% endfor %}
            </table>
        </div>
    </div>
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

@app.route('/recommend', methods=['GET'])
def recommend():
    user = request.args.get('user').strip().lower()
    conn = get_db_connection()
    c = conn.cursor()
    c.execute("SELECT title FROM manhwa WHERE username = %s", (user,))
    read = [r[0].lower() for r in c.fetchall()]
    c.execute("SELECT title FROM manhwa WHERE username = %s AND score >= 8", (user,))
    favs = [r[0] for r in c.fetchall()]
    conn.close()

    if not favs: return "Nemáš oblíbené (8+). <a href='/'>Zpět</a>"

    try:
        res = requests.get(f"https://api.jikan.moe/v4/top/manga?type=manhwa&page={random.randint(1,3)}")
        candidates = [f"{m['title']}: {m.get('synopsis','')[:200]}" for m in res.json()['data'] if m['title'].lower() not in read]
        
        prompt = f"Uživatel má rád {favs}. Vyber 3 z tohoto seznamu: {candidates[:15]}. Odpověz česky, název - důvod."
        ai_res = client.chat.completions.create(model="gemma3:27b", messages=[{"role": "user", "content": prompt}])
        
        return f"<div style='background:#161616;color:white;padding:20px;'>{ai_res.choices[0].message.content}<br><a href='/'>Zpět</a></div>"
    except Exception as e:
        return f"Chyba: {e} <a href='/'>Zpět</a>"

if __name__ == '__main__':
    init_db()
    # DŮLEŽITÉ: Port z os.environ.get("PORT")
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
