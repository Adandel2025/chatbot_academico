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
    'hola','hola como estas','hola asistente',
    'buenos dias','buenas tardes','buenas noches',
    'hey','holi','qué tal','que tal','buenas noches'
]

DESPEDIDAS = [
    'adios',  'adios tilin','bye','nos vemos','hasta luego','gracias', 'nos vemos luego tilin','gracias tilin','nos vemos luego','fue un placer','que tengas linda tarde'
]

# RESPUESTAS CONVERSACIONALES
CONVERSACION = {
    "como estas": "😊 Estoy muy bien, gracias por preguntar. ¿En qué tema o subtema puedo ayudarte?",
    "como estas hoy": "😊 Estoy contento de verte  hoy. ¿En qué puedo ayudarte?",
    "quien eres": "🤖 Soy Tilin, un chatbot creado para ayudarte con información.",
    "que eres": "🤖 Soy Tilin, un asistente virtual que responde tus dudas sobre fundamentos de programacion.",
}

EMOCIONES = {
    "me siento mal": "💙 Lamento oir eso,en que  tema o subtema puedo ayudarte.",
    "estoy triste": "💙 Lamento que te sientas así,si necesitas ayuda en un tema dimelo.",
    "estoy cansado": "😌 Tal vez necesitas un pequeño descanso.",
    "estoy bien": "😄 ¡Qué bueno! Me alegra saber que te sientes bien.",
}

STOPWORDS = {
    "que","es","un","una","el","la","los","las",
    "de","del","a","en","y","para","con","por"
}


def normalize_text(t):
    return re.sub(r'\s+', ' ', (t or '').strip()).lower()


def top_keywords(text):

    words = re.findall(r"\w+", text.lower())

    keywords = [w for w in words if w not in STOPWORDS and len(w) > 2]

    if not keywords and words:
        keywords = sorted(words, key=len, reverse=True)[:1]

    return keywords


# -------- BUSCAR SUBTEMA EXACTO --------

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
            """,(q,))

            r = cur.fetchone()

            if not r:
                return None

            respuesta = r['contenido']

            if r.get('referencias'):
                respuesta += "\n\n📚 Referencia:\n" + r['referencias']

            return respuesta

    finally:
        conn.close()


# -------- LISTAR TEMAS --------

def list_topics():

    conn = get_db_connection()

    try:
        with conn.cursor() as cur:

            cur.execute("SELECT DISTINCT tema FROM contenidos ORDER BY tema")

            rows = cur.fetchall()

            return [r['tema'] for r in rows]

    finally:
        conn.close()


# -------- LISTAR SUBTEMAS --------

def list_subtopics(tema):

    conn = get_db_connection()

    try:
        with conn.cursor() as cur:

            cur.execute(
                "SELECT id, subtema FROM contenidos WHERE LOWER(tema)=%s ORDER BY subtema",
                (tema.lower(),)
            )

            return cur.fetchall()

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
    q_lower = query.lower()

    for r in rows:

        contenido_lower = (r['contenido'] or '').lower()
        score = 0

        if q_lower in (r['subtema'] or '').lower():
            score += 50

        for k in keywords:

            if re.search(rf"\b{re.escape(k)}\b", contenido_lower):
                score += 10

            if re.search(rf"\b{re.escape(k)}\b", (r['subtema'] or '').lower()):
                score += 8

        if q_lower in contenido_lower:
            score += 30

        if score > 0:
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


    # CONVERSACION GENERAL
    for frase in CONVERSACION:
        if frase in low:

            resp = CONVERSACION[frase]

            save_history(message, resp)

            return jsonify({'ok': True, 'response': resp})


    # EMOCIONES
    for frase in EMOCIONES:
        if frase in low:

            resp = EMOCIONES[frase]

            save_history(message, resp)

            return jsonify({'ok': True, 'response': resp})


    # SALUDO
    if any(s in low for s in SALUDOS):

        temas = list_topics()

        texto = "🤖 Hola soy Tilin.\n\n¿En qué tema puedo ayudarte?\n\n"

        for t in temas:
            texto += f"- {t}\n"

        save_history(message, texto)

        return jsonify({'ok': True, 'response': texto})


    # DESPEDIDA
    if any(d in low for d in DESPEDIDAS):

        resp = "👋 ¡Adiós! Si necesitas más ayuda vuelve pronto."

        save_history(message, resp)

        return jsonify({'ok': True, 'response': resp})


    # TEMA EXACTO
    temas = [t.lower() for t in list_topics()]

    if low in temas:

        sub = list_subtopics(low)

        lista = f"📚 Subtemas de {low.title()}:\n\n"

        for s in sub:
            lista += f"- {s['subtema']}\n"

        save_history(message, lista)

        return jsonify({'ok': True, 'response': lista})


    # SUBTEMA EXACTO
    exacto = search_exact_subtopic(message)

    if exacto:

        save_history(message, exacto)

        return jsonify({'ok': True, 'response': exacto})


    # BUSQUEDA
    found = free_search(message)

    if found:

        save_history(message, found)

        return jsonify({'ok': True, 'response': found})


    # SIN RESULTADOS
    resp = "❌ No encontré información relacionada."

    save_history(message, resp)

    return jsonify({'ok': True, 'response': resp})


# ------------------ RUN ------------------

if __name__ == '__main__':
    app.run(debug=True)