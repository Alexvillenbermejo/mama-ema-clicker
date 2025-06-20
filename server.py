from flask import Flask, render_template, request
from flask_socketio import SocketIO, emit
import threading
import time
import random
import sqlite3
import json
import math

app = Flask(__name__)
socketio = SocketIO(app, cors_allowed_origins="*", async_mode="threading")

lock = threading.Lock()

cookies = 0.0

# Mejoras base
mejoras_base = {
    "cursor":  {"nombre": "Cursor", "base_price": 15, "cps": 0.1},
    "abuela":  {"nombre": "Abuela", "base_price": 100, "cps": 1},
    "granja":  {"nombre": "Granja", "base_price": 1100, "cps": 8},
    "fabrica": {"nombre": "Fábrica", "base_price": 12000, "cps": 47},
}

# Multiplicadores base
multiplicadores_base = {
    "eficacia_1": {"nombre": "x1.2 Eficiencia", "factor": 1.2, "precio": 1000, "duracion": 0},
    "eficacia_2": {"nombre": "x1.5 Eficiencia", "factor": 1.5, "precio": 5000, "duracion": 0},
    "eficacia_3": {"nombre": "x2.0 Eficiencia", "factor": 2.0, "precio": 15000, "duracion": 0},
    "evento_1": {"nombre": "Evento especial x2 CPS 60s", "factor": 2.0, "precio": 0, "duracion": 60},
}

usuarios = {}  # sid -> info

DB_NAME = "cookie_clicker_individual.db"

def init_db():
    with sqlite3.connect(DB_NAME) as con:
        cur = con.cursor()
        # Tabla progreso por usuario
        cur.execute("""
        CREATE TABLE IF NOT EXISTS progreso_usuario (
            nombre TEXT PRIMARY KEY,
            mejoras TEXT,
            multiplicadores TEXT
        )
        """)
        # Tabla para cookies globales
        cur.execute("""
        CREATE TABLE IF NOT EXISTS estado (
            key TEXT PRIMARY KEY,
            value TEXT
        )
        """)
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
        else:
            return None, None

def calcular_precio(base_price, cantidad):
    return math.ceil(base_price * (1.15 ** cantidad))

def calcular_cps_jugador(usuario):
    base_cps = 0.0
    for mid, cantidad in usuario["mejoras"].items():
        base_cps += mejoras_base[mid]["cps"] * cantidad
    multiplicador = 1.0
    # Multiplicadores normales
    for mid, comprado in usuario["multiplicadores"].items():
        if comprado and multiplicadores_base.get(mid, {}).get("duracion", 0) == 0:
            multiplicador *= multiplicadores_base[mid]["factor"]
    # Multiplicadores temporales activos
    now = time.time()
    if "eventos_activos" in usuario:
        for evento in usuario["eventos_activos"]:
            if evento["fin"] > now:
                multiplicador *= evento["factor"]
        # Limpiar eventos expirados
        usuario["eventos_activos"] = [e for e in usuario["eventos_activos"] if e["fin"] > now]
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

def background_task():
    global cookies
    while True:
        socketio.sleep(1)
        with lock:
            total_cps = sum(calcular_cps_jugador(u) for u in usuarios.values())
            cookies += total_cps

            # Cada 120 seg aprox evento global (multiplica x2 CPS 60s)
            if not hasattr(background_task, "ultimo_evento") or time.time() - background_task.ultimo_evento > 120:
                background_task.ultimo_evento = time.time()
                for usuario in usuarios.values():
                    if "eventos_activos" not in usuario:
                        usuario["eventos_activos"] = []
                    usuario["eventos_activos"].append({
                        "nombre": "Evento especial x2 CPS",
                        "factor": 2.0,
                        "fin": time.time() + 60,
                    })
                # Avisar a todos del evento
                socketio.emit("evento_global", {"mensaje": "Evento especial activo: x2 CPS por 60 segundos!"})

            # Galleta dorada individual, probabilidad baja por jugador cada segundo
            for usuario in usuarios.values():
                if random.random() < 0.005:  # ~0.5% por segundo
                    if "galleta_dorada" not in usuario or usuario["galleta_dorada"] < time.time():
                        usuario["galleta_dorada"] = time.time() + 30  # 30s efecto
                        socketio.emit("galleta_dorada", {"mensaje": f"Galleta dorada para {usuario['nombre']}! +x2 CPS 30s"}, to=get_sid_por_nombre(usuario["nombre"]))

        enviar_estado()
        save_progress()

def get_sid_por_nombre(nombre):
    for sid, u in usuarios.items():
        if u["nombre"] == nombre:
            return sid
    return None

@app.route("/")
def index():
    return render_template("index.html")

@socketio.on("login")
def handle_login(nombre):
    if not nombre.strip():
        nombre = f"Jugador{random.randint(1000,9999)}"

    mejoras_guardadas, mult_guardados = load_usuario_progreso(nombre)
    with lock:
        usuarios[request.sid] = {
            "nombre": nombre,
            "mejoras": mejoras_guardadas if mejoras_guardadas else {mid: 0 for mid in mejoras_base},
            "multiplicadores": mult_guardados if mult_guardados else {mid: False for mid in multiplicadores_base},
            "eventos_activos": [],
            "galleta_dorada": 0,
        }
    emit("login_ok", {"nombre": nombre})
    enviar_estado()

@socketio.on("disconnect")
def handle_disconnect():
    with lock:
        if request.sid in usuarios:
            usuario = usuarios[request.sid]
            save_usuario_progreso(usuario["nombre"], usuario["mejoras"], usuario["multiplicadores"])
            del usuarios[request.sid]
    enviar_estado()

@socketio.on("click")
def handle_click():
    global cookies
    with lock:
        cookies += 1
    enviar_estado()

@socketio.on("comprar")
def handle_compra(mejora_id):
    global cookies
    with lock:
        if request.sid not in usuarios:
            return
        if mejora_id in mejoras_base:
            usuario = usuarios[request.sid]
            cantidad = usuario["mejoras"][mejora_id]
            precio = calcular_precio(mejoras_base[mejora_id]["base_price"], cantidad)
            if cookies >= precio:
                cookies -= precio
                usuario["mejoras"][mejora_id] += 1
                save_usuario_progreso(usuario["nombre"], usuario["mejoras"], usuario["multiplicadores"])
    enviar_estado()

@socketio.on("comprar_multiplicador")
def handle_multiplicador(mid):
    global cookies
    with lock:
        if request.sid not in usuarios:
            return
        if mid in multiplicadores_base:
            usuario = usuarios[request.sid]
            comprado = usuario["multiplicadores"][mid]
            precio = multiplicadores_base[mid]["precio"]
            if not comprado and cookies >= precio:
                cookies -= precio
                usuario["multiplicadores"][mid] = True
                save_usuario_progreso(usuario["nombre"], usuario["mejoras"], usuario["multiplicadores"])
    enviar_estado()

if __name__ == "__main__":
    import os
    port = int(os.environ.get("PORT", 5000))
    init_db()
    load_progress()
    threading.Thread(target=loop_incremento, daemon=True).start()
    socketio.run(app, host="0.0.0.0", port=port)

