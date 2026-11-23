"""(sacado de inspeccion.py) Decision del barrido: elegir el proximo punto de vista. Corre en el backend; el control de llegada y orientacion queda en el robot."""
import time

import numpy as np

from domain.navegacion import cobertura
from domain.navegacion import exploracion
from domain.navegacion import planificador
from domain.navegacion.mapa_ocupacion import RES, UMBRAL_OCC
from domain.navegacion.planificador import a_celda, celda_mas_cercana, zona_transitable

PASO_POS = 0.3
N_YAW = 16
DESFASE_CAMARA = 0.12
MIN_GANANCIA = 12
MIN_GANANCIA_FINAL = 4
PESO_DIST = 0.5
MAX_INTENTOS = 2
ANCHO, ALTO, FOCAL = 320, 240, 120.0


MIN_GANANCIA_DEFECTO = MIN_GANANCIA
DIST_MAX_DEFECTO = cobertura.DIST_MAX


def aplicar_parametros(params):
    """Los parametros del yaml que usa el calculo (antes los fijaba inspeccion_crear como variables globales). Viajan en CADA llamada: el backend no recuerda
    nada de una llamada a la otra, asi lo pueden usar dos clientes con yamls distintos y una llamada se puede repetir sin efectos."""
    global MIN_GANANCIA
    MIN_GANANCIA = params.get("inspeccion_ganancia_min", MIN_GANANCIA_DEFECTO)
    cobertura.DIST_MAX = params.get("inspeccion_dist_max", DIST_MAX_DEFECTO)


def pendientes(cob, ins):
    """Tramos-altura sin ver: (puntos (n,3), normales (n,2), indice de parche (n), claves (n), bandas (n), centros de parche (p,2))."""
    nb, zb = cob["nb"], (np.arange(cob["nb"]) + 0.5) * cob["alto"] / cob["nb"]
    pts, nor, pid, cl, ba, cen = [], [], [], [], [], []
    for k, est in cob["estado"].items():
        libres = [b for b in np.nonzero(est == 0)[0] if ins["intentos"].get((k, int(b)), 0) < MAX_INTENTOS]
        if not libres:
            continue
        c, n = cob["geom"][k]
        for b in libres:
            pts.append([c[0], c[1], zb[b]])
            nor.append(n)
            pid.append(len(cen))
            cl.append(k)
            ba.append(int(b))
        cen.append(c)
    if not pts:
        return None
    return np.array(pts), np.array(nor), np.array(pid), cl, ba, np.array(cen)


def visibilidad(L, lo, pos, cen, muestras=14):
    """(m, p) True si desde la posicion i se ve el parche j sin una pared de por medio (segun el mapa)."""
    ocup = L > UMBRAL_OCC
    d = cen[None, :, :] - pos[:, None, :]
    largo = np.maximum(np.linalg.norm(d, axis=2), 1e-6)
    hasta = np.clip(1.0 - 0.3 / largo, 0.0, 1.0)              # no cuenta el ultimo tramo: es la pared misma
    t = np.linspace(0.02, 1.0, muestras)[None, None, :] * hasta[:, :, None]
    p = pos[:, None, None, :] + t[..., None] * d[:, :, None, :]
    c = np.floor((p - lo) / RES).astype(int)
    dentro = (c[..., 0] >= 0) & (c[..., 0] < L.shape[1]) & (c[..., 1] >= 0) & (c[..., 1] < L.shape[0])
    cx, cy = np.clip(c[..., 0], 0, L.shape[1] - 1), np.clip(c[..., 1], 0, L.shape[0] - 1)
    tapado = (ocup[cy, cx] & dentro).any(axis=2)
    return ~tapado


def elegir_punto_de_vista(L, lo, cob, ins, pos, cam_z, min_ganancia=None, Lv=None):
    """El mejor punto de vista (x, y, yaw, ganancia, esperados) o None. L: mapa para planificar (con obstaculos bajos); Lv: mapa de paredes para la visibilidad (sin ellos:
    la camara ve por arriba de un objeto bajo)."""
    Lv = L if Lv is None else Lv
    pen = pendientes(cob, ins)
    if pen is None:
        return None
    P, N, pid, cl, ba, cen = pen
    trans, _ = zona_transitable(L, casco=True)
    ci = a_celda(pos, lo)
    ci2 = ci if trans[ci[1], ci[0]] else celda_mas_cercana(trans, ci)
    if ci2 is None:
        return None
    costo = exploracion.costos_desde(trans, ci2)
    paso = max(1, int(PASO_POS / RES))
    mask = np.zeros(trans.shape, dtype=bool)
    mask[::paso, ::paso] = True
    fs, cs = np.nonzero(mask & trans & np.isfinite(costo))
    if len(fs) == 0:
        return None
    cand = lo + (np.stack([cs, fs], axis=1) + 0.5) * RES
    dist_m = costo[fs, cs] * RES
    vis = visibilidad(Lv, lo, cand, cen)[:, pid]                   # (m, n)
    mejor, mejor_neto = None, -np.inf
    for k in range(N_YAW):
        yaw = 2 * np.pi * k / N_YAW
        c, s = np.cos(yaw), np.sin(yaw)
        cx, cy = cand[:, 0] + DESFASE_CAMARA * c, cand[:, 1] + DESFASE_CAMARA * s
        rx, ry, rz = P[None, :, 0] - cx[:, None], P[None, :, 1] - cy[:, None], P[None, :, 2] - cam_z
        fwd = c * rx + s * ry
        lat = -s * rx + c * ry
        fw = np.where(fwd > 1e-6, fwd, 1.0)
        u, v = ANCHO / 2 - FOCAL * lat / fw, ALTO / 2 - FOCAL * rz / fw
        dist3 = np.maximum(np.sqrt(rx ** 2 + ry ** 2 + rz ** 2), 1e-9)
        cos_inc = -(rx * N[None, :, 0] + ry * N[None, :, 1]) / dist3
        ok = (vis & (fwd > 1e-6) & (fwd >= cobertura.DIST_MIN) & (fwd <= cobertura.DIST_MAX)
              & (u >= cobertura.MARGEN_PX) & (u < ANCHO - cobertura.MARGEN_PX) & (v >= cobertura.MARGEN_PX) & (v < ALTO - cobertura.MARGEN_PX)
              & (cos_inc >= np.cos(np.radians(cobertura.ANGULO_MAX))))
        ganancia = ok.sum(axis=1)
        neto = ganancia - PESO_DIST * dist_m
        i = int(neto.argmax())
        if ganancia[i] >= (MIN_GANANCIA if min_ganancia is None else min_ganancia) and neto[i] > mejor_neto:
            mejor_neto = neto[i]
            mejor = (cand[i].copy(), yaw, int(ganancia[i]), [(cl[j], ba[j]) for j in np.nonzero(ok[i])[0]])
    if mejor is None:
        return None
    return mejor[0], mejor[1], mejor[2], mejor[3]


def elegir(L, Lv, lo, cob, ins, pos, cam_z, params):
    """Cola de inspeccion_decidir (lo que no se resuelve sin mirar el mapa). No modifica 'ins': devuelve que paso y el robot lo aplica."""
    t0 = time.perf_counter()
    aplicar_parametros(params)
    cobertura.cob_registrar(cob, Lv, lo)   # las paredes del mapa actual, todavia sin ver
    pct = cobertura.cob_resumen(cob)[0]
    r = {"cob": cob, "pct": pct}
    if ins["objetivo"] is not None and pct >= ins["objetivo"]:
        r["estado"] = "objetivo"
        return r
    v = elegir_punto_de_vista(L, lo, cob, ins, pos, cam_z, Lv=Lv)
    if v is None and MIN_GANANCIA_FINAL < MIN_GANANCIA:
        v = elegir_punto_de_vista(L, lo, cob, ins, pos, cam_z, MIN_GANANCIA_FINAL, Lv)
    if v is None:
        r["estado"] = "sin_pared"
        return r
    xy, yaw, ganancia, esperados = v
    wp, _, _ = planificador.planificar(L, lo, pos, xy, casco=True)
    r.update({"xy": xy, "yaw": yaw, "ganancia": ganancia, "esperados": esperados, "wp": wp, "ms": 1000 * (time.perf_counter() - t0)})
    r["estado"] = "sin_ruta" if wp is None else "ok"
    return r
