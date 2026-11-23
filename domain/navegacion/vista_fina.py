"""(sacado de inspeccion_fina.py) Donde pararse para cada foto de la inspeccion fina y la ruta hasta ahi. Corre en el backend."""
import math

import numpy as np

from domain.navegacion import exploracion
from domain.navegacion import inspeccion_decision as inspeccion
from domain.navegacion import planificador
from domain.navegacion.planificador import a_celda, celda_mas_cercana, zona_transitable

EXTRA_MAX = 0.8
DESVIOS_GRADOS = (0, 8, -8, 16, -16, 24, -24)


def _centro(z):
    return z["p"] + z["t"] * 0.5 * (z["s"][0] + z["s"][1])


def _punto_de_vista(ang, zona, paso, d, trans, costo, lo, Lv):
    """Donde parar al robot (x, y del robot y rumbo) para sacar esa foto, o None. La camara va a d de la pared mirando al centro del dano; si ahi no se puede
    estar (pared mapeada, obstaculo, sin camino) se prueba cada vez mas lejos."""
    z = zona
    c, n, t = _centro(z), z["n"], z["t"]
    th0 = {"general": 0.0, "cerca": 0.0, "izq": -math.radians(ang), "der": math.radians(ang)}[paso]   # izq: de frente a la pared es del lado -t
    for extra in np.arange(0.0, EXTRA_MAX + 1e-9, 0.1):
        for dg in DESVIOS_GRADOS:
            th = th0 + math.radians(dg)
            u = math.cos(th) * n + math.sin(th) * t
            robot = c + (d + extra + inspeccion.DESFASE_CAMARA) * u
            ce = a_celda(robot, lo)
            if not (0 <= ce[0] < trans.shape[1] and 0 <= ce[1] < trans.shape[0]):
                continue
            if not trans[ce[1], ce[0]] or not np.isfinite(costo[ce[1], ce[0]]):
                continue
            if not inspeccion.visibilidad(Lv, lo, robot[None, :], c[None, :])[0, 0]:
                continue
            return {"xy": robot, "yaw": math.atan2(-u[1], -u[0]), "d": d + float(extra), "c": c}
    return None


def vista(L, Lv, lo, pos, zona, paso, d, ang):
    """Con zona=None solo dice si el robot esta en una zona con espacio libre ('sin_espacio'). Con zona: punto de vista y ruta."""
    trans, _ = zona_transitable(L, casco=True)
    ci = a_celda(pos, lo)
    ci2 = ci if trans[ci[1], ci[0]] else celda_mas_cercana(trans, ci)
    if ci2 is None:
        return {"estado": "sin_espacio"}
    if zona is None:
        return {"estado": "ok"}
    costo = exploracion.costos_desde(trans, ci2)
    vpn = _punto_de_vista(ang, zona, paso, d, trans, costo, lo, Lv)
    if vpn is None:
        return {"estado": "sin_vista"}
    wp, _, _ = planificador.planificar(L, lo, pos, vpn["xy"], casco=True)
    return {"estado": "sin_ruta" if wp is None else "ok", "vpn": vpn, "wp": wp}
