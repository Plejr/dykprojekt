import os
import sqlite3
import requests
import httpx
import random
from flask import Flask, request, render_template_string
from openai import OpenAI
from dotenv import load_dotenv

# 1. NAČTENÍ KONFIGURACE
load_dotenv()

# 2. INICIALIZACE FLASKU (Tímto se definuje 'app', musí to být nahoře!)
app = Flask(__name__)

# Použijeme složku /tmp, kde má Docker vždy právo zápisu
DB_PATH = '/tmp/knihovna.db'

client = OpenAI(
    api_key=os.environ.get("OPENAI_API_KEY"),
    base_url=os.environ.get("OPENAI_BASE_URL", "https://kurim.ithope.eu/v1"),
    http_client=httpx.Client(verify=False)
)

def init_db():
    """Vytvoří databázi, pokud neexistuje."""
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS manhwa 
                 (id INTEGER PRIMARY KEY AUTOINCREMENT, user TEXT, title TEXT, score INTEGER)''')
    conn.commit()
    conn.close()

init_db()

# 4. HTML ŠABLONA (Přímo v kódu pro maximální spolehlivost)
HTML_LAYOUT = """
<!DOCTYPE html>
<html lang="cs">
<head>
    <meta charset="UTF-8">
    <title>Manhwa AI Manager</title>
    <style>
        body { font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif; background: #0c0c0c; color: #eee; padding: 20px; line-height: 1.6; }
        .container { max-width: 900px; margin: auto; }
        .box { background: #161616; padding: 25px; border-radius: 12px; margin-bottom: 25px; border: 1px solid #333; box-shadow: 0 4px 15px rgba(0,0,0,0.5); }
        input, button { padding: 12px; margin: 8px 0; width: 100%; box-sizing: border-box; border-radius: 6px; border: 1px solid #444; font-size: 16px; }
        input { background: #222; color: white; }
        button { background: #007bff; color: white; cursor: pointer; font-weight: bold; border: none; transition: 0.3s; }
        button:hover { background: #0056b3; transform: translateY(-2px); }
        table { width: 100%; border-collapse: collapse; margin-top: 15px; }
        th, td { padding: 12px; border-bottom: 1px solid #333; text-align: left; }
        th { color: #007bff; text-transform: uppercase; font-size: 0.8em; letter-spacing: 1px; }
        .score-pill { background: #28a745; color: white; padding: 2px 8px; border-radius: 12px; font-size: 0.9em; }
        h1 { text-align: center; color: #007bff; font-size: 2.5em; margin-bottom: 30px; }
        h3 { margin-top: 0; color: #fff; border-left: 4px solid #007bff; padding-left: 10px; }
    </style>
</head>
<body>
    <div class="container">
        <h1>📚 Manhwa AI Manager</h1>
        
        <div style="display: grid; grid-template-columns: 1fr 1fr; gap: 20px;">
            <div class="box">
                <h3>➕ Přidat do historie</h3>
                <form action="/add" method="POST">
                    <input type="text" name="user" placeholder="Tvé jméno (např. karel)" required>
                    <input type="text" name="title" placeholder="Přesný název manhwy" required>
                    <input type="number" name="score" min="1" max="10" placeholder="Tvé hodnocení (1-10)" required>
                    <button type="submit">Uložit záznam</button>
                </form>
            </div>
            
            <div class="box">
                <h3>✨ AI Doporučení</h3>
                <form action="/recommend" method="GET">
                    <input type="text" name="user" placeholder="Zadej své jméno" required>
                    <button type="submit" style="background: #28a745;">Najít nové pecky</button>
                </form>
            </div>
        </div>

        <div class="box">
            <h3>📜 Moje historie čtení</h3>
            <table>
                <thead>
                    <tr><th>Uživatel</th><th>Název Manhwy</th><th>Skóre</th></tr>
                </thead>
                <tbody>
                    {% for item in library %}
                    <tr>
                        <td>{{ item[1] }}</td>
                        <td>{{ item[2] }}</td>
                        <td><span class="score-pill">{{ item[3] }}/10</span></td>
                    </tr>
                    {% endfor %}
                </tbody>
            </table>
        </div>
    </div>
</body>
</html>
"""

# 5. CESTY (ROUTES)
@app.route('/')
def home():
    conn = sqlite3.connect(DB_PATH)
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
    
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("INSERT INTO manhwa (user, title, score) VALUES (?, ?, ?)", (user, title, int(score)))
    conn.commit()
    conn.close()
    return "<script>window.location.href='/';</script>"

@app.route('/recommend', methods=['GET'])
def recommend():
    user = request.args.get('user').strip().lower()
    
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    # Co uživatel četl
    c.execute("SELECT title FROM manhwa WHERE user = ?", (user,))
    already_read = [row[0].lower().strip() for row in c.fetchall()]
    # Co má rád (pro kontext AI)
    c.execute("SELECT title FROM manhwa WHERE user = ? AND score >= 8", (user,))
    favs = [row[0] for row in c.fetchall()]
    conn.close()

    if not favs:
        return f"Uživatel {user} nemá v databázi žádné oblíbené (8/10+). Přidej něco pořádného! <br><a href='/'>Zpět</a>"

    try:
        # Získání dat z Jikan API (Top Manhwa)
        headers = {'User-Agent': 'Mozilla/5.0'}
        # Zkusíme náhodnou stránku 1-5, aby se seznam neustále měnil
        random_page = random.randint(1, 5)
        api_url = f"https://api.jikan.moe/v4/top/manga?type=manhwa&page={random_page}"
        
        response_api = requests.get(api_url, headers=headers, timeout=10)
        
        if response_api.status_code != 200:
            return f"API má zpoždění (Chyba {response_api.status_code}). Zkus to za pár vteřin. <br><a href='/'>Zpět</a>"

        data = response_api.json().get('data', [])
        
        # FILTROVÁNÍ: Do seznamu pro AI pošleme jen to, co v DB vůbec není
        candidates = []
        for m in data:
            t = m.get('title', '')
            if t and t.lower().strip() not in already_read:
                synopsis = m.get('synopsis', 'Popis není k dispozici.')[:250]
                candidates.append(f"TITUL: {t}\nPOPIS: {synopsis}")

        if not candidates:
            return "Na této stránce API jsou samé věci, které už znáš. Zkus kliknout znovu! <br><a href='/'>Zpět</a>"

        # PŘÍSNÝ PROMPT PRO AI
        prompt = f"""
        Jsi expert na manhwu. Uživatel {user} má velmi rád: {', '.join(favs)}.
        
        TVŮJ ÚKOL:
        Vyber 3 tituly z níže uvedeného seznamu, které by ho mohly bavit. 
        
        SEZNAM K VÝBĚRU (VYBÍREJ POUZE ODTEĎ):
        {chr(10).join(candidates[:20])}

        PRAVIDLA:
        1. NIKDY nenavrhuj tyto tituly (uživatel je četl): {', '.join(already_read)}.
        2. Odpověz česky.
        3. Formát: "Název" - krátký důvod (1 věta).
        4. Pokud v seznamu není nic podobného, vyber ty nejkvalitnější akční kousky.
        """

        ai_res = client.chat.completions.create(
            model="gemma3:27b",
            messages=[{"role": "user", "content": prompt}],
            temperature=0.1  # Velmi nízká teplota zabrání halucinacím
        )

        content = ai_res.choices[0].message.content

        return f"""
        <body style="background:#0c0c0c; color:#eee; font-family:sans-serif; padding:40px;">
            <div style="max-width:800px; margin:auto; background:#161616; padding:30px; border-radius:12px; border:1px solid #333;">
                <h2 style="color:#28a745;">✨ AI doporučení na míru</h2>
                <div style="white-space:pre-wrap; line-height:1.8; font-size:1.1em;">{content}</div>
                <hr style="border:0; border-top:1px solid #333; margin:25px 0;">
                <a href="/" style="color:#007bff; text-decoration:none; font-weight:bold; font-size:1.1em;">⬅ Zpět do knihovny</a>
            </div>
        </body>
        """

    except Exception as e:
        return f"Nastala chyba: {str(e)}. Zkus to znovu. <br><a href='/'>Zpět</a>"

# 6. SPUŠTĚNÍ APLIKACE
if __name__ == '__main__':
    app.run(host="0.0.0.0", port=5000, debug=True)
