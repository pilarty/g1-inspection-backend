"""Posición del robot durante la inspección.

El simulador (o el robot real) manda su posición cada medio segundo a POST /pose.
Acá se guarda la última (para mostrar «el robot está acá» en vivo) y, si hay una
inspección en curso, se juntan los puntos y se mandan a la nube en lotes cada
pocos segundos, sin frenar al que los manda.
"""
import threading
import time
from typing import List, Optional

import requests

from infrastructure import nube

INTERVALO_ENVIO = 3.0  # segundos entre lotes a la nube

ultima: Optional[dict] = None
_pendientes: List[dict] = []
_lock = threading.Lock()
_hilo: Optional[threading.Thread] = None


def registrar(x: float, y: float, yaw: Optional[float], t: Optional[float]) -> dict:
    global ultima
    punto = {"t": t if t is not None else time.time(), "x": x, "y": y, "yaw": yaw}
    ultima = {**punto, "relevamiento_id": nube.relevamiento_actual}
    if nube.relevamiento_actual is not None and nube.sesion_activa():
        with _lock:
            _pendientes.append({**punto, "_rid": nube.relevamiento_actual})
        _asegurar_hilo()
    return ultima


def _asegurar_hilo() -> None:
    global _hilo
    if _hilo is None or not _hilo.is_alive():
        _hilo = threading.Thread(target=_enviar_periodicamente, daemon=True)
        _hilo.start()


def _enviar_periodicamente() -> None:
    while True:
        time.sleep(INTERVALO_ENVIO)
        enviar_pendientes()


def enviar_pendientes() -> None:
    """Manda a la nube los puntos juntados (agrupados por inspección)."""
    with _lock:
        lote = list(_pendientes)
        _pendientes.clear()
    if not lote or not nube.sesion_activa():
        return
    por_rel: dict = {}
    for p in lote:
        por_rel.setdefault(p.pop("_rid"), []).append(p)
    for rid, puntos in por_rel.items():
        try:
            r = nube.reenviar("POST", f"relevamientos/{rid}/trayectoria", cuerpo={"puntos": puntos})
            r.raise_for_status()
        except requests.RequestException as e:
            print("[nube] no se pudo enviar la trayectoria:", e)
            if len(puntos) < 5000:  # se reintenta en el próximo lote, sin crecer sin límite
                with _lock:
                    _pendientes[:0] = [{**p, "_rid": rid} for p in puntos]


def subir_plano(rid: int, room: Optional[dict]) -> None:
    """Guarda en la nube el plano (contorno y paredes del escenario) de esa inspección, sin frenar."""
    if room is None or not nube.sesion_activa():
        return

    def tarea():
        try:
            r = nube.reenviar("PUT", f"relevamientos/{rid}/plano", cuerpo=room)
            r.raise_for_status()
        except requests.RequestException as e:
            print("[nube] no se pudo enviar el plano:", e)

    threading.Thread(target=tarea, daemon=True).start()
