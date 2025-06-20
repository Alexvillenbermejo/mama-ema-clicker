# server.py
from flask import Flask, render_template, request
from flask_socketio import SocketIO, emit
import threading
import time
import random
import sqlite3
import json
import math

app = Flask(__name__)
socketio = SocketIO(app, cors_allowed_origins="*", async_mode='threading')

lock = threading.Lock()
cookies = 0.0

mejoras_base = {
    "cursor":  {"nombre": "Cursor", "base_price": 15, "cps": 0.1},
    "abuela":  {"nombre": "Abuela", "base_price": 100, "cps": 1},
    "granja":  {"nombre": "Granja", "base_price": 1100, "cps": 8},
    "fabrica": {"nombre": "Fábrica", "base_price": 12000, "cps": 47},
}

multiplicadores_base = {
    "eficacia_1": {"nombre": "x1.2 Eficiencia", "factor": 1.2, "precio": 1000},
    "eficacia_2": {"nombre": "x1.5 Eficiencia", "factor": 1.5, "precio": 5000},
    "eficacia_3": {"nombre": "x2.0 Eficiencia", "factor": 2.0, "precio": 15000}
}

usuarios = {}  # sid -> info
DB_NAME = "cookie_clicker_individual.db"

def init_db():
    with sqlite3.connect(DB_NAME) as con:
        cur = con.cursor()
        cur.execute("""
        CREATE TABLE IF NOT EXISTS progreso_usuario (
            nombre TEXT PRIMARY KEY,
            mejoras TEXT,
            multiplicadores TEXT
        )""")
        cur.execute("""
        CREATE TABLE IF NOT EXISTS estado (
            key TEXT PRIMARY KEY,
            value TEXT
        )""")
        con.commit()

def save_progress():
    with lock, sqlite3.connect(DB_NAME) as con:
        cur = con.cursor()
        cur.execute("REPLACE INTO estado (key, value) VALUES (?, ?)", ("cookies", str(cookies)))
        con.commit()

def load_progress():
    global cookies
    with sqlite3.connect(DB_NAME) as con:
        cur = con.cursor()
        cur.execute("SELECT value FROM estado WHERE key = 'cookies'")
        row = cur.fetchone()
        if row:
            cookies = float(row[0])

def save_usuario_progreso(nombre, mejoras, multiplicadores):
    with sqlite3.connect(DB_NAME) as con:
        cur = con.cursor()
        cur.execute("""
            REPLACE INTO progreso_usuario (nombre, mejoras, multiplicadores) VALUES (?, ?, ?)
        """, (nombre, json.dumps(mejoras), json.dumps(multiplicadores)))
        con.commit()

def load_usuario_progreso(nombre):
    with sqlite3.connect(DB_NAME) as con:
        cur = con.cursor()
        cur.execute("SELECT mejoras, multiplicadores FROM progreso_usuario WHERE nombre = ?", (nombre,))
        row = cur.fetchone()
        if row:
            mejoras = json.loads(row[0])
            multiplicadores = json.loads(row[1])
            return mejoras, multiplicadores
        return None, None

def calcular_precio(base_price, cantidad):
    return math.ceil(base_price * (1.15 ** cantidad))

def calcular_cps_jugador(usuario):
    base_cps = sum(mejoras_base[mid]["cps"] * cantidad for mid, cantidad in usuario["mejoras"].items())
    multiplicador = 1.0
    for mid, comprado in usuario["multiplicadores"].items():
        if comprado:
            multiplicador *= multiplicadores_base[mid]["factor"]
    return base_cps * multiplicador

def enviar_estado():
    with lock:
        total_cps = sum(calcular_cps_jugador(u) for u in usuarios.values())
        estado_base = {
            "cookies": round(cookies, 1),
            "cps": round(total_cps, 1),
            "usuarios": {u["nombre"]: round(calcular_cps_jugador(u), 2) for u in usuarios.values()},
            "mejoras_base": mejoras_base,
            "multiplicadores_base": multiplicadores_base,
        }
        for sid, usuario in usuarios.items():
            estado_personal = estado_base.copy()
            estado_personal["tu_mejoras"] = usuario["mejoras"]
            estado_personal["tu_multiplicadores"] = usuario["multiplicadores"]
            socketio.emit("estado", estado_personal, to=sid)

def loop_incremento():
    global cookies
    while True:
        time.sleep(1)
        with lock:
            total_cps = sum(calcular_cps_jugador(u) for u in usuarios.values())
            cookies += total_cps
        enviar_estado()
        save_progress()

@app.route("/")
def index():
    return render_template("index.html")

@socketio.on("login")
def handle_login(nombre):
    if not nombre.strip():
        nombre = f"Jugador{random.randint(1000,9999)}"

    mejoras, mult = load_usuario_progreso(nombre)
    with lock:
        usuarios[request.sid] = {
            "nombre": nombre,
            "mejoras": mejoras if mejoras else {mid: 0 for mid in mejoras_base},
            "multiplicadores": mult if mult else {mid: False for mid in multiplicadores_base}
        }
    emit("login_ok", {"nombre": nombre})
    enviar_estado()

@socketio.on("disconnect")
def handle_disconnect():
    with lock:
        if request.sid in usuarios:
            u = usuarios[request.sid]
            save_usuario_progreso(u["nombre"], u["mejoras"], u["multiplicadores"])
            del usuarios[request.sid]
    enviar_estado()

@socketio.on("click")
def handle_click():
    global cookies
    with lock:
        cookies += 1
    enviar_estado()

@socketio.on("comprar")
def handle_compra(mid):
    global cookies
    with lock:
        if request.sid not in usuarios:
            return
        if mid in mejoras_base:
            u = usuarios[request.sid]
            cantidad = u["mejoras"][mid]
            precio = calcular_precio(mejoras_base[mid]["base_price"], cantidad)
            if cookies >= precio:
                cookies -= precio
                u["mejoras"][mid] += 1
                save_usuario_progreso(u["nombre"], u["mejoras"], u["multiplicadores"])
    enviar_estado()

@socketio.on("comprar_multiplicador")
def handle_multiplicador(mid):
    global cookies
    with lock:
        if request.sid not in usuarios:
            return
        if mid in multiplicadores_base:
            u = usuarios[request.sid]
            if not u["multiplicadores"][mid] and cookies >= multiplicadores_base[mid]["precio"]:
                cookies -= multiplicadores_base[mid]["precio"]
                u["multiplicadores"][mid] = True
                save_usuario_progreso(u["nombre"], u["mejoras"], u["multiplicadores"])
    enviar_estado()

if __name__ == "__main__":
    init_db()
    load_progress()
    threading.Thread(target=loop_incremento, daemon=True).start()
    socketio.run(app, host="0.0.0.0", port=5000, debug=False)
