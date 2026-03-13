
import os
import re
from datetime import timedelta
from flask import (
    Flask, render_template, request, redirect,
    url_for, flash, session, jsonify
)
import pymysql

# ---------- CONFIG ----------
UPLOAD_FOLDER = 'uploads'

DB_CONFIG = {
    'host': 'localhost',
    'user': 'root',
    'password': '',
    'db': 'chatbot',
    'charset': 'utf8mb4',
    'cursorclass': pymysql.cursors.DictCursor
}

ADMIN_USER = 'admin'
ADMIN_PASS = 'admin123'
SECRET_KEY = 'clave_secreta_segura'

# ----------------------------

app = Flask(__name__)
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
app.secret_key = SECRET_KEY
app.permanent_session_lifetime = timedelta(hours=5)
os.makedirs(UPLOAD_FOLDER, exist_ok=True)


def get_db_connection():
    return pymysql.connect(**DB_CONFIG)


# ---------------- BOT CONFIG ----------------

SALUDOS = [
    "hola","holaa","holaaa","hola chatbot","hola pybot",
    "buenas","buenos dias","buen día","buenas tardes","buenas noches",
    "hey","holi","holis","que tal","ola","necesito ayuda", "ayudame",
    "hola que tal","saludos"
]

DESPEDIDAS = [
    "adios","adiós","bye","hasta luego",
    "nos vemos","hasta pronto","chao",
    "cuídate","gracias","muchas gracias"
]

STOPWORDS = {
    "que","es","un","una","el","la","los","las",
    "de","del","a","en","y","para","con","por"
}

BOT_PREGUNTAS = [
    "quien eres","qué eres",
    "que eres","que puedes hacer",
    "eres un bot","como funcionas",
    "qué haces","que haces"
]

ESTADOS_USUARIO = [
    "estoy bien","todo bien","me siento bien",
    "estoy mal","todo mal","me siento mal",
    "no estoy bien","triste","feliz",
    "cansado","cansada",
    "estresado","estresada",
    "preocupado","preocupada",
    "contento","contenta",
    "enojado","enojada",
    "deprimido","deprimida"
]


# -------- NORMALIZAR TEXTO --------

def normalize_text(t):
    return re.sub(r'\s+', ' ', (t or '').strip()).lower()


# -------- DETECTAR TEXTO BASURA --------

def is_garbage(text):

    words = re.findall(r"\w+", text)

    if text.isnumeric():
        return True

    if len(text) <= 2:
        return True

    if len(words) == 1 and len(words[0]) <= 3:
        return True

    return False


# -------- PALABRAS CLAVE --------

def top_keywords(text):

    words = re.findall(r"[a-zA-Záéíóúñ]+", text.lower())

    keywords = [
        w for w in words
        if w not in STOPWORDS and len(w) > 3
    ]

    return keywords


# -------- BUSQUEDA EXACTA SUBTEMA --------

def search_exact_subtopic(phrase):

    q = normalize_text(phrase)

    conn = get_db_connection()

    try:
        with conn.cursor() as cur:

            cur.execute("""
            SELECT contenido, referencias
            FROM contenidos
            WHERE LOWER(subtema) = %s
            LIMIT 1
            """, (q,))

            r = cur.fetchone()

            if not r:
                return None

            respuesta = r['contenido']

            if r.get('referencias'):
                respuesta += "\n\n📚 Referencia:\n" + r['referencias']

            return respuesta

    finally:
        conn.close()


# -------- LISTA TEMAS --------

def list_topics():

    conn = get_db_connection()

    try:
        with conn.cursor() as cur:

            cur.execute("SELECT DISTINCT tema FROM contenidos ORDER BY tema")

            rows = cur.fetchall()

            return [r['tema'] for r in rows]

    finally:
        conn.close()


# -------- LISTA SUBTEMAS --------

def list_subtopics(tema):

    conn = get_db_connection()

    try:
        with conn.cursor() as cur:

            cur.execute("""
            SELECT subtema
            FROM contenidos
            WHERE LOWER(tema) = %s
            ORDER BY subtema
            """, (tema.lower(),))

            rows = cur.fetchall()

            return [r['subtema'] for r in rows]

    finally:
        conn.close()


# -------- BUSQUEDA INTELIGENTE --------

def free_search(query):

    keywords = top_keywords(query)

    if not keywords:
        return None

    conn = get_db_connection()

    try:
        with conn.cursor() as cur:

            cur.execute("""
            SELECT id, tema, subtema, contenido, referencias
            FROM contenidos
            """)

            rows = cur.fetchall()

    finally:
        conn.close()

    resultados = []

    for r in rows:

        contenido = (r['contenido'] or '').lower()
        subtema = (r['subtema'] or '').lower()

        score = 0

        for k in keywords:

            pattern = r'\b' + re.escape(k) + r'\b'

            if re.search(pattern, subtema):
                score += 40

            if re.search(pattern, contenido):
                score += 20

        if score >= 40:
            resultados.append((score, r))

    if not resultados:
        return None

    resultados.sort(reverse=True, key=lambda x: x[0])

    mejor = resultados[0][1]

    respuesta = f"{mejor['subtema']} ({mejor['tema']}):\n\n{mejor['contenido']}"

    if mejor.get('referencias'):
        respuesta += "\n\n📚 Referencia:\n" + mejor['referencias']

    return respuesta


# -------- GUARDAR HISTORIAL --------

def save_history(user_message, bot_response):

    conn = get_db_connection()

    try:
        with conn.cursor() as cur:

            cur.execute(
                "INSERT INTO history (user_message, bot_response) VALUES (%s,%s)",
                (user_message, bot_response)
            )

            conn.commit()

    finally:
        conn.close()


# ------------------ CHAT ------------------

@app.route('/')
def index():
    return render_template('chat.html')


@app.route('/api/chat', methods=['POST'])
def api_chat():

    data = request.get_json()
    message = (data.get('message') or '').strip()

    if not message:
        return jsonify({'ok': False, 'message': 'Mensaje vacío'}), 400

    low = message.lower().strip()

# -------- QUIEN ERES --------

    if any(p in low for p in BOT_PREGUNTAS):

        resp = """🤖 Soy PyBot, un chatbot educativo.

Puedo ayudarte a encontrar información sobre temas almacenados en mi base de datos.

Puedes preguntarme por ejemplo:

• algoritmos
• programación
• estructuras de datos
"""

        save_history(message, resp)
        return jsonify({'ok': True, 'response': resp})


# -------- COMO ESTAS --------

    if "como estas" in low or "cómo estás" in low:

        resp = "🤖 Estoy bien gracias 😊 ¿Cuál es tu pregunta?"

        save_history(message, resp)
        return jsonify({'ok': True, 'response': resp})


# -------- ESTADOS DE ANIMO --------

    if any(e in low for e in ESTADOS_USUARIO):

        if any(x in low for x in ["mal","triste","deprimido","estresado"]):
            resp = "😟 Lamento escuchar eso. Espero que pronto te sientas mejor."

        elif any(x in low for x in ["bien","feliz","contento"]):
            resp = "😊 Me alegra saber que te sientes bien."

        elif "cansado" in low:
            resp = "😴 Parece que necesitas descansar."

        else:
            resp = "🙂 Gracias por contarme cómo te sientes."

        save_history(message, resp)
        return jsonify({'ok': True, 'response': resp})


# -------- SALUDOS --------

    if any(s in low for s in SALUDOS):

        temas = list_topics()

        texto = "🤖 Hola soy PyBot.\n\n¿En qué tema o subtema puedo ayudarte?\n\n"

        for t in temas:
            texto += f"- {t}\n"

        save_history(message, texto)
        return jsonify({'ok': True, 'response': texto})


# -------- DESPEDIDAS --------

    if any(d in low for d in DESPEDIDAS):

        resp = "👋 ¡Adiós! Si necesitas más ayuda vuelve pronto."

        save_history(message, resp)
        return jsonify({'ok': True, 'response': resp})


# -------- SI ES UN TEMA --------

    temas = list_topics()

    for t in temas:

        if low == t.lower():

            subtemas = list_subtopics(t)

            if subtemas:

                texto = f"📚 Tema: {t}\n\nSelecciona un subtema:\n\n"

                for s in subtemas:
                    texto += f"- {s}\n"

                save_history(message, texto)
                return jsonify({'ok': True, 'response': texto})


# -------- TEXTO BASURA --------

    if is_garbage(message):

        resp = "❌ No encontré información. Intenta escribir una pregunta o tema."

        save_history(message, resp)
        return jsonify({'ok': True, 'response': resp})


# -------- BUSQUEDA EXACTA --------

    exacto = search_exact_subtopic(message)

    if exacto:
        save_history(message, exacto)
        return jsonify({'ok': True, 'response': exacto})


# -------- BUSQUEDA INTELIGENTE --------

    found = free_search(message)

    if found:
        save_history(message, found)
        return jsonify({'ok': True, 'response': found})


# -------- SIN RESULTADOS --------

    resp = "❌ No encontré información relacionada intenta escribir un tema o pregunta."

    save_history(message, resp)
    return jsonify({'ok': True, 'response': resp})





# ------------------ ADMIN ------------------

@app.route('/admin')
def admin_login_get():
    return render_template('admin_login.html')


@app.route('/admin/login', methods=['POST'])
def admin_login():

    username = request.form.get('username')
    password = request.form.get('password')

    if username == ADMIN_USER and password == ADMIN_PASS:

        session['admin_logged'] = True
        return redirect(url_for('admin_dashboard'))

    flash('Credenciales inválidas')
    return redirect(url_for('admin_login_get'))

@app.route('/admin/dashboard')
def admin_dashboard():

    if not session.get('admin_logged'):
        return redirect(url_for('admin_login_get'))

    conn = get_db_connection()

    try:
        with conn.cursor() as cur:

            cur.execute("""
            SELECT id, tema, subtema, contenido, referencias, created_at
            FROM contenidos
            ORDER BY tema, subtema
            """)

            rows = cur.fetchall()

    finally:
        conn.close()

    return render_template('admin_dashboard.html', contenidos=rows)


@app.route('/admin/history')
def admin_history():

    if not session.get('admin_logged'):
        return redirect(url_for('admin_login_get'))

    conn = get_db_connection()

    try:
        with conn.cursor() as cur:

            cur.execute("""
            SELECT id, user_message, bot_response, created_at
            FROM history
            ORDER BY id DESC
            """)

            rows = cur.fetchall()

    finally:
        conn.close()

    return render_template('admin_history.html', history=rows)


@app.route('/admin/delete_history/<int:id>', methods=['POST'])
def delete_history(id):

    if not session.get('admin_logged'):
        return redirect(url_for('admin_login_get'))

    conn = get_db_connection()

    try:
        with conn.cursor() as cur:
            cur.execute(
                "DELETE FROM history WHERE id=%s",
                (id,)
            )
            conn.commit()
    finally:
        conn.close()

    flash('Conversación eliminada')
    return redirect(url_for('admin_history'))


@app.route('/admin/clear_history', methods=['POST'])
def clear_history():

    if not session.get('admin_logged'):
        return redirect(url_for('admin_login_get'))

    conn = get_db_connection()

    try:
        with conn.cursor() as cur:
            cur.execute("DELETE FROM history")
            conn.commit()
    finally:
        conn.close()

    flash('Historial eliminado completamente')
    return redirect(url_for('admin_history'))


@app.route('/admin/delete_old_history', methods=['POST'])
def delete_old_history():

    if not session.get('admin_logged'):
        return redirect(url_for('admin_login_get'))

    conn = get_db_connection()

    try:
        with conn.cursor() as cur:

            cur.execute("""
            DELETE FROM history
            WHERE created_at < DATE_SUB(NOW(), INTERVAL 30 DAY)
            """)

            conn.commit()

    finally:
        conn.close()

    flash('Historial antiguo eliminado')
    return redirect(url_for('admin_history'))


@app.route('/admin/add', methods=['GET','POST'])
def admin_add():

    if not session.get('admin_logged'):
        return redirect(url_for('admin_login_get'))

    if request.method == 'POST':

        tema = request.form.get('tema').strip()
        subtema = request.form.get('subtema').strip()
        contenido = request.form.get('contenido').strip()
        referencias = request.form.get('referencias').strip()

        conn = get_db_connection()

        try:
            with conn.cursor() as cur:

                cur.execute("""
                INSERT INTO contenidos
                (tema, subtema, contenido, referencias)
                VALUES (%s,%s,%s,%s)
                """, (tema, subtema, contenido, referencias))

                conn.commit()

        finally:
            conn.close()

        flash('Contenido agregado')
        return redirect(url_for('admin_dashboard'))

    return render_template('admin_add.html')


@app.route('/admin/edit/<int:id>', methods=['GET','POST'])
def admin_edit(id):

    if not session.get('admin_logged'):
        return redirect(url_for('admin_login_get'))

    conn = get_db_connection()

    try:
        with conn.cursor() as cur:

            if request.method == 'POST':

                tema = request.form.get('tema').strip()
                subtema = request.form.get('subtema').strip()
                contenido = request.form.get('contenido').strip()
                referencias = request.form.get('referencias').strip()

                cur.execute("""
                UPDATE contenidos
                SET tema=%s, subtema=%s, contenido=%s, referencias=%s
                WHERE id=%s
                """, (tema, subtema, contenido, referencias, id))

                conn.commit()

                flash('Contenido actualizado correctamente')
                return redirect(url_for('admin_dashboard'))

            cur.execute("SELECT * FROM contenidos WHERE id=%s", (id,))
            contenido = cur.fetchone()

    finally:
        conn.close()

    return render_template('admin_edit.html', contenido=contenido)


@app.route('/admin/delete/<int:id>', methods=['POST'])
def admin_delete(id):

    if not session.get('admin_logged'):
        return redirect(url_for('admin_login_get'))

    conn = get_db_connection()

    try:
        with conn.cursor() as cur:

            cur.execute(
                "DELETE FROM contenidos WHERE id=%s",
                (id,)
            )

            conn.commit()

    finally:
        conn.close()

    flash('Contenido eliminado correctamente')
    return redirect(url_for('admin_dashboard'))


@app.route('/admin/logout')
def admin_logout():

    session.pop('admin_logged', None)
    return redirect(url_for('admin_login_get'))


# ------------------ RUN ------------------

if __name__ == '__main__':
    app.run(debug=True)