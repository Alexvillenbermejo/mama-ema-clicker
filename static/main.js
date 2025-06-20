const socket = io();

const loginContainer = document.getElementById("login-container");
const nombreInput = document.getElementById("nombreInput");
const entrarBtn = document.getElementById("entrarBtn");

const gameContainer = document.getElementById("game-container");
const cookieCount = document.getElementById("cookie-count");
const cpsCount = document.getElementById("cps-count");
const clickBtn = document.getElementById("click-btn");

const tiendaContainer = document.getElementById("tienda-container");
const tiendaMultContainer = document.getElementById("tienda-mult-container");
const jugadoresLista = document.getElementById("jugadores-lista");
const mensaje = document.getElementById("mensaje");

const boostContainer = document.createElement("div");
boostContainer.id = "boost-container";
boostContainer.style.display = "none";
boostContainer.style.position = "fixed";
boostContainer.style.top = "20px";
boostContainer.style.right = "20px";
boostContainer.style.backgroundColor = "#ffe082";
boostContainer.style.padding = "15px";
boostContainer.style.borderRadius = "10px";
boostContainer.style.fontWeight = "bold";
boostContainer.style.boxShadow = "0 0 8px rgba(0,0,0,0.2)";
boostContainer.style.color = "#333";
document.body.appendChild(boostContainer);

const boostLabel = document.createElement("p");
const boostTimer = document.createElement("p");
boostContainer.appendChild(boostLabel);
boostContainer.appendChild(boostTimer);

let miNombre = null;
let mejorasJugador = {};
let multiplicadoresJugador = {};
let mejorasBase = {};
let multiplicadoresBase = {};

let boostTiempoRestante = 0;
let boostInterval = null;

entrarBtn.onclick = () => {
    const nombre = nombreInput.value.trim();
    socket.emit("login", nombre);
};

socket.on("login_ok", (data) => {
    miNombre = data.nombre;
    loginContainer.style.display = "none";
    gameContainer.style.display = "flex";
});

clickBtn.onclick = () => {
    socket.emit("click");
};

function comprar(id) {
    socket.emit("comprar", id);
}

function comprarMultiplicador(id) {
    socket.emit("comprar_multiplicador", id);
}

// Función para mostrar mensajes evento
socket.on("mensaje_evento", (msg) => {
    mensaje.textContent = msg;
    setTimeout(() => { mensaje.textContent = ""; }, 5000);
});

socket.on("estado", (estado) => {
    cookieCount.textContent = estado.cookies;
    cpsCount.textContent = estado.cps;

    jugadoresLista.innerHTML = "";
    for (const [nombre, cps] of Object.entries(estado.usuarios)) {
        const li = document.createElement("li");
        li.textContent = `${nombre} — ${cps} CPS`;
        jugadoresLista.appendChild(li);
    }

    if (estado.mejoras_base) mejorasBase = estado.mejoras_base;
    if (estado.multiplicadores_base) multiplicadoresBase = estado.multiplicadores_base;

    if (estado.tu_mejoras) mejorasJugador = estado.tu_mejoras;
    if (estado.tu_multiplicadores) multiplicadoresJugador = estado.tu_multiplicadores;

    // Render tienda mejoras
    tiendaContainer.innerHTML = "";
    for (const [id, cantidad] of Object.entries(mejorasJugador)) {
        const base = mejorasBase[id];
        const precio = calcularPrecio(base.base_price, cantidad);
        const div = document.createElement("div");
        div.className = "mejora";
        div.innerHTML = `
            <strong>${base.nombre}</strong><br>
            Cantidad: ${cantidad} | Precio: ${precio} | +${base.cps} CPS
            <br>
            <button onclick="comprar('${id}')">Comprar</button>
            <hr>
        `;
        tiendaContainer.appendChild(div);
    }

    // Render tienda multiplicadores
    tiendaMultContainer.innerHTML = "";
    for (const [id, comprado] of Object.entries(multiplicadoresJugador)) {
        const base = multiplicadoresBase[id];
        const btnDisabled = comprado ? "disabled" : "";
        const btnText = comprado ? "Comprado" : "Comprar";
        const div = document.createElement("div");
        div.className = "mejora";
        div.innerHTML = `
            <strong>${base.nombre}</strong><br>
            Precio: ${base.precio} <br>
            <button onclick="comprarMultiplicador('${id}')" ${btnDisabled}>${btnText}</button>
            <hr>
        `;
        tiendaMultContainer.appendChild(div);
    }

    // Manejo de boosts
    if ((estado.boost && estado.boost.duracion > 0) || (estado.evento_global && estado.evento_global_duracion > 0)) {
        let label = "";
        let tiempo = 0;

        if (estado.evento_global && estado.evento_global_duracion > 0) {
            label += `Evento Global x2`;
            tiempo = estado.evento_global_duracion;
        }

        if (estado.boost && estado.boost.duracion > 0) {
            if (label) label += " + ";
            label += `Galleta Dorada x${estado.boost.factor}`;
            tiempo = Math.max(tiempo, estado.boost.duracion);
        }

        iniciarTemporizadorBoost(label, tiempo);
    } else {
        detenerTemporizadorBoost();
    }
});

function iniciarTemporizadorBoost(factor, duracion) {
    boostTiempoRestante = duracion;
    boostLabel.textContent = `🔥 Multiplicador activo: ${factor}`;
    boostTimer.textContent = `⏳ Tiempo restante: ${boostTiempoRestante} segundos`;
    boostContainer.style.display = "block";

    if (boostInterval) clearInterval(boostInterval);
    boostInterval = setInterval(() => {
        boostTiempoRestante--;
        if (boostTiempoRestante <= 0) {
            detenerTemporizadorBoost();
        } else {
            boostTimer.textContent = `⏳ Tiempo restante: ${boostTiempoRestante} segundos`;
        }
    }, 1000);
}

function detenerTemporizadorBoost() {
    boostContainer.style.display = "none";
    if (boostInterval) clearInterval(boostInterval);
    boostInterval = null;
}

function calcularPrecio(basePrice, cantidad) {
    return Math.ceil(basePrice * (1.15 ** cantidad));
}
