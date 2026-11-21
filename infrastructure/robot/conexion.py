"""Prueba de conexion con un Unitree G1 EDU de fabrica (real o simulado).

Un G1 de fabrica ofrece dos canales: SSH a su computadora de desarrollo
(192.168.123.164) y DDS del SDK de Unitree (rt/lowstate, Domain ID 0).
Comprueba, en orden: red, SSH, DDS y camara. Ningun paso envia ordenes al robot:
la red y SSH solo abren y cierran la conexion, DDS solo escucha y la camara se
comprueba con un unico comando de solo lectura (lsusb) por SSH.
"""
import ipaddress
import json
import re
import socket
import subprocess
import sys
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterator, Optional

import paramiko
import psutil

BACKEND_DIR = Path(__file__).resolve().parents[2]
RED_ROBOT = ipaddress.ip_network("192.168.123.0/24")  # red interna fija del G1

PASOS = [
    ("red", "Red"),
    ("ssh", "SSH"),
    ("dds", "DDS"),
    ("camara", "Cámara"),
]
PASOS_RAPIDOS = ["red", "ssh", "dds"]  # comprobacion al reconectar
LIMITE_S = {"red": 3, "ssh": 6, "dds": 5, "camara": 8}

# Unico comando que la app ejecuta en el robot: lista los USB (solo lectura).
# IDs USB de Intel RealSense: D435i 8086:0b3a, D435 8086:0b07.
COMANDO_CAMARA = "lsusb"
IDS_REALSENSE = ("8086:0b3a", "8086:0b07")


@dataclass
class Conexion:
    host: str
    ssh_usuario: str
    ssh_password: str
    ssh_puerto: int
    dds_domain_id: int
    interfaz: Optional[str] = None  # nombre elegido; None = detectar


# Interfaces de red

def listar_interfaces() -> list:
    stats = psutil.net_if_stats()
    salida = []
    for nombre, direcciones in psutil.net_if_addrs().items():
        ips = [d.address for d in direcciones if d.family == socket.AF_INET]
        if ips:
            salida.append({"nombre": nombre, "ips": ips, "activa": bool(stats.get(nombre) and stats[nombre].isup)})
    return salida


def _ip(texto: str):
    try:
        return ipaddress.ip_address(texto)
    except ValueError:
        return None


def sugerir_interfaz(host: str, interfaces: list) -> Optional[dict]:
    """La que esta en la misma red que el robot; si no, la que tiene IP 192.168.123.x."""
    destino = _ip(host)
    activas = [i for i in interfaces if i["activa"]]
    if destino is not None:
        if destino.is_loopback:
            red = ipaddress.ip_network("127.0.0.0/8")
        else:
            red = ipaddress.ip_network(f"{destino}/24", strict=False)
        for i in activas:
            if any(_ip(ip) in red for ip in i["ips"]):
                return i
    for i in activas:
        if any(_ip(ip) in RED_ROBOT for ip in i["ips"]):
            return i
    return None


def resolver_interfaz(cfg: Conexion) -> Optional[dict]:
    """Interfaz a usar: la elegida si sigue existiendo y activa; si no, se vuelve a detectar."""
    interfaces = listar_interfaces()
    if cfg.interfaz:
        for i in interfaces:
            if i["nombre"] == cfg.interfaz and i["activa"]:
                return i
    return sugerir_interfaz(cfg.host, interfaces)


def ip_de(interfaz: Optional[dict], host: str) -> Optional[str]:
    """IP de la interfaz que corresponde al host (para atar los sockets a esa tarjeta)."""
    if not interfaz:
        return None
    destino = _ip(host)
    if destino is not None:
        for ip in interfaz["ips"]:
            if destino.is_loopback == _ip(ip).is_loopback:
                return ip
    return interfaz["ips"][0]


# Pasos

class FalloPaso(Exception):
    """El paso fallo; el mensaje explica la causa probable en lenguaje claro."""


def _abrir_socket(cfg: Conexion, ip_local: Optional[str], timeout: float) -> socket.socket:
    origen = (ip_local, 0) if ip_local else None
    try:
        return socket.create_connection((cfg.host, cfg.ssh_puerto), timeout=timeout, source_address=origen)
    except socket.gaierror:
        raise FalloPaso(f"No se pudo resolver el host «{cfg.host}». Revisá que la IP o el nombre estén bien escritos.")
    except socket.timeout:
        raise FalloPaso(
            f"El robot no respondió en {cfg.host}:{cfg.ssh_puerto} en {timeout:g} s. "
            "Revisá que esté encendido, el cable de red y que la IP sea la correcta."
        )
    except ConnectionRefusedError:
        raise FalloPaso(
            f"Se llegó a {cfg.host}, pero el puerto {cfg.ssh_puerto} está cerrado. "
            "Revisá el puerto SSH o que el servicio SSH del robot esté activo."
        )
    except OSError as e:
        if getattr(e, "winerror", None) == 10049 or e.errno == 99:
            raise FalloPaso(f"La interfaz elegida ya no tiene la IP {ip_local}. Volvé a detectar las interfaces de red.")
        raise FalloPaso(
            f"No hay ruta hacia {cfg.host} desde esta PC ({e.strerror or e}). "
            "Revisá que la IP del robot esté en la misma red que la interfaz elegida."
        )


def paso_red(cfg: Conexion, interfaz: Optional[dict], ip_local: Optional[str]) -> str:
    destino = _ip(cfg.host)
    if interfaz is None and destino is not None and destino in RED_ROBOT:
        raise FalloPaso(
            "No hay una tarjeta de red con IP 192.168.123.x. Revisá el cable y que la PC tenga "
            "IP fija en esa red (por ejemplo 192.168.123.51, máscara 255.255.255.0)."
        )
    s = _abrir_socket(cfg, ip_local, LIMITE_S["red"])
    s.close()
    via = f" por {interfaz['nombre']} ({ip_local})" if interfaz else ""
    return f"El robot responde en {cfg.host}:{cfg.ssh_puerto}{via}."


def _sesion_ssh(cfg: Conexion, ip_local: Optional[str], limite: float) -> paramiko.SSHClient:
    sock = _abrir_socket(cfg, ip_local, limite)
    cliente = paramiko.SSHClient()
    cliente.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    try:
        cliente.connect(
            cfg.host, port=cfg.ssh_puerto, username=cfg.ssh_usuario, password=cfg.ssh_password, sock=sock,
            timeout=limite, banner_timeout=limite, auth_timeout=limite,
            look_for_keys=False, allow_agent=False,
        )
    except paramiko.AuthenticationException:
        cliente.close()
        raise FalloPaso(
            "El robot rechazó el usuario o la contraseña SSH. De fábrica son unitree / 123, "
            "salvo que quien tenga el robot las haya cambiado."
        )
    except (paramiko.SSHException, EOFError, socket.timeout) as e:
        cliente.close()
        raise FalloPaso(
            f"El puerto {cfg.ssh_puerto} responde pero no se pudo completar SSH ({e or 'sin respuesta'}). "
            "Revisá que ese puerto sea el de SSH."
        )
    return cliente


def paso_ssh(cfg: Conexion, ip_local: Optional[str]) -> str:
    cliente = _sesion_ssh(cfg, ip_local, LIMITE_S["ssh"])
    cliente.close()  # solo se comprueba el inicio de sesion: no se ejecuta ningun comando
    return f"Sesión SSH iniciada como «{cfg.ssh_usuario}» y cerrada sin ejecutar comandos."


def paso_camara(cfg: Conexion, ip_local: Optional[str]) -> str:
    """Comprueba por SSH que la camara RealSense de la cabeza este conectada (solo lectura).

    El G1 de fabrica no transmite video: la imagen solo se puede leer desde su
    computadora de desarrollo, asi que se comprueba que la camara este presente.
    """
    limite = LIMITE_S["camara"]
    cliente = _sesion_ssh(cfg, ip_local, limite)
    try:
        _, salida, errores = cliente.exec_command(COMANDO_CAMARA, timeout=limite)
        texto = salida.read().decode(errors="replace")
        error = errores.read().decode(errors="replace").strip()
    except (paramiko.SSHException, socket.timeout) as e:
        raise FalloPaso(f"No se pudo consultar los dispositivos USB del robot ({e or 'sin respuesta'}).")
    finally:
        cliente.close()
    for linea in texto.splitlines():
        if any(i in linea.lower() for i in IDS_REALSENSE):
            # "Bus 002 Device 003: ID 8086:0b3a Intel Corp. Intel(R) RealSense(TM) ..." -> el nombre
            nombre = re.sub(r"^.*?ID [0-9a-fA-F]{4}:[0-9a-fA-F]{4}\s*", "", linea).strip()
            return f"Cámara detectada en el robot: {nombre or 'Intel RealSense'}."
    if not texto.strip() and error:
        raise FalloPaso(f"El robot no pudo listar sus dispositivos USB ({error}).")
    raise FalloPaso(
        "La cámara RealSense de la cabeza no aparece conectada en el robot. "
        "Reiniciá el robot; si sigue sin aparecer, revisá el cable de la cámara con el servicio técnico."
    )


def _proceso_dds(modulo: str, args: list, ip_local: Optional[str], limite: float, que: str) -> dict:
    """Corre un modulo DDS en un proceso aparte y devuelve la linea JSON que imprime."""
    cmd = [sys.executable, "-B", "-m", modulo, *args]
    if ip_local:
        cmd += ["--interfaz", ip_local]
    try:
        p = subprocess.run(
            cmd, cwd=BACKEND_DIR, capture_output=True, text=True, timeout=limite + 10,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
    except subprocess.TimeoutExpired:
        return {"ok": False, "detalle": f"{que} no terminó a tiempo."}
    for linea in reversed(p.stdout.strip().splitlines()):
        try:
            return json.loads(linea)
        except ValueError:
            continue
    error = (p.stderr.strip().splitlines() or ["sin salida"])[-1]
    return {"ok": False, "detalle": f"{que} terminó con error: {error}"}


def _sonda(canal: str, dominio: int, ip_local: Optional[str]) -> dict:
    limite = LIMITE_S["dds"]
    return _proceso_dds("infrastructure.robot.sonda_dds",
                        ["--canal", canal, "--dominio", str(dominio), "--timeout", str(limite)],
                        ip_local, limite, "La escucha DDS")


def paso_dds(cfg: Conexion, interfaz: Optional[dict], ip_local: Optional[str]) -> str:
    r = _sonda("estado", cfg.dds_domain_id, ip_local)
    if not r["ok"]:
        via = f"la interfaz {interfaz['nombre']}" if interfaz else "ninguna interfaz en particular"
        raise FalloPaso(
            f"No llegó el estado del robot (rt/lowstate) en el Domain ID {cfg.dds_domain_id} por {via}. "
            "Con un G1 real el Domain ID es 0. Revisá que la interfaz elegida sea la del cable al robot, "
            "que el firewall de Windows no bloquee la app y que el robot sea la versión EDU. "
            f"Detalle: {r['detalle']}"
        )
    return r["detalle"]


# Prueba completa

def _ahora() -> str:
    return datetime.now(timezone.utc).isoformat()


def describir_interfaz(interfaz: Optional[dict], ip_local: Optional[str]) -> Optional[dict]:
    return {"nombre": interfaz["nombre"], "ip": ip_local} if interfaz else None


def probar(cfg: Conexion, pasos: Optional[list] = None) -> Iterator[dict]:
    """Ejecuta los pasos en orden y va emitiendo eventos (para mostrarlos en vivo)."""
    elegidos = [p for p in PASOS if pasos is None or p[0] in pasos]
    interfaz = resolver_interfaz(cfg)
    ip_local = ip_de(interfaz, cfg.host)
    yield {"tipo": "inicio", "fecha": _ahora(), "interfaz": describir_interfaz(interfaz, ip_local),
           "pasos": [{"id": i, "nombre": n, "limite_s": LIMITE_S[i]} for i, n in elegidos]}

    red_ok = ssh_ok = True
    resultados = []
    for id_paso, _ in elegidos:
        if not red_ok:
            res = {"estado": "omitido", "mensaje": "No se ejecutó porque falló la red."}
        elif id_paso == "camara" and not ssh_ok:
            res = {"estado": "omitido", "mensaje": "No se ejecutó porque falló SSH (la cámara se consulta por SSH)."}
        else:
            yield {"tipo": "paso", "paso": id_paso, "estado": "en_curso"}
            t0 = time.monotonic()
            try:
                if id_paso == "red":
                    mensaje = paso_red(cfg, interfaz, ip_local)
                elif id_paso == "ssh":
                    mensaje = paso_ssh(cfg, ip_local)
                elif id_paso == "dds":
                    mensaje = paso_dds(cfg, interfaz, ip_local)
                else:
                    mensaje = paso_camara(cfg, ip_local)
                res = {"estado": "ok", "mensaje": mensaje}
            except FalloPaso as e:
                res = {"estado": "error", "mensaje": str(e)}
            except Exception as e:  # error inesperado: se informa sin cortar la prueba
                res = {"estado": "error", "mensaje": f"Error inesperado: {type(e).__name__}: {e}"}
            res["ms"] = int((time.monotonic() - t0) * 1000)
            if id_paso == "red" and res["estado"] == "error":
                red_ok = False
            if id_paso == "ssh" and res["estado"] == "error":
                ssh_ok = False
        res.update(tipo="paso", paso=id_paso)
        resultados.append(res)
        yield res

    fallos = [r["paso"] for r in resultados if r["estado"] == "error"]
    yield {"tipo": "fin", "fecha": _ahora(), "resultado": "error" if fallos else "ok", "fallos": fallos}


def parar_emergencia(cfg: Conexion) -> dict:
    """Pone el robot en modo amortiguado (como L2 + B en el mando). No pide confirmacion."""
    interfaz = resolver_interfaz(cfg)
    ip_local = ip_de(interfaz, cfg.host)
    r = _proceso_dds("infrastructure.robot.parada_dds", ["--dominio", str(cfg.dds_domain_id), "--timeout", "2"],
                     ip_local, 2, "La orden de parada")
    r.setdefault("confirmada", False)
    return r
