"""Exploracion por fronteras sobre el mapa que arma slam_vivo.py.
Frontera = celda libre que toca una zona que el robot todavia no vio. El robot va a la frontera alcanzable mas cercana;
al llegar (o si la frontera ya se aclaro) elige otra, hasta que no queda ninguna: ahi la exploracion termino."""
import heapq
import time

import cv2
import numpy as np

from domain.navegacion import planificador
from domain.navegacion.mapa_ocupacion import RES, UMBRAL_OCC
from domain.navegacion.planificador import a_celda, a_metros, celda_mas_cercana, linea_libre, zona_transitable

MIN_FRONTERA = 8        # celdas (40 cm): una frontera mas chica es un hueco entre rayos o un borde sucio, no un pasillo
RADIO_META = 1.0        # m: la meta es la celda transitable alcanzable mas cercana a la frontera, a menos de esto
REPETIDA = 1.0          # m: no se vuelve a elegir una meta a menos de esto de una ya visitada
SALIDA_MAX = 3.0        # m: una meta no puede estar mas lejos que esto de la pared mapeada (caja que envuelve a las paredes vistas); si no, una puerta o un
                        # hueco al exterior lleva al robot a espacios sin paredes donde el SLAM se pierde. Cada pared nueva que se descubre agranda la caja.
HUECO = 7               # celdas (35 cm): huecos de "no visto" mas chicos que esto, entre rayos del LiDAR, no cuentan como zona desconocida
PASOS = [(1, 0, 1.0), (-1, 0, 1.0), (0, 1, 1.0), (0, -1, 1.0), (1, 1, 1.4142), (1, -1, 1.4142), (-1, 1, 1.4142), (-1, -1, 1.4142)]


def explorar_crear():
    return {"meta": None, "visitadas": [], "metas": 0, "terminada": False}


def fronteras(L):
    """Lista de fronteras; cada una es un arreglo de celdas (columna, fila)."""
    visto = cv2.morphologyEx((L != 0).astype(np.uint8), cv2.MORPH_CLOSE, np.ones((HUECO, HUECO), np.uint8))
    toca = cv2.dilate((visto == 0).astype(np.uint8), np.ones((3, 3), np.uint8))
    borde = ((L < -0.2) & (toca > 0)).astype(np.uint8)
    n, etiq, est, _ = cv2.connectedComponentsWithStats(borde, connectivity=8)
    return [np.argwhere(etiq == i)[:, ::-1] for i in range(1, n) if est[i, cv2.CC_STAT_AREA] >= MIN_FRONTERA]


def costos_desde(trans, ini):
    """Largo del camino (en celdas) desde ini hasta cada celda transitable; inf donde no se llega."""
    alto, ancho = trans.shape
    libre = trans.ravel().tolist()
    costo = [float("inf")] * (alto * ancho)
    costo[ini[1] * ancho + ini[0]] = 0.0
    cola = [(0.0, ini[0], ini[1])]
    while cola:
        g, x, y = heapq.heappop(cola)
        if g > costo[y * ancho + x]:
            continue
        for dx, dy, w in PASOS:
            nx, ny = x + dx, y + dy
            if 0 <= nx < ancho and 0 <= ny < alto and libre[ny * ancho + nx] and g + w < costo[ny * ancho + nx]:
                costo[ny * ancho + nx] = g + w
                heapq.heappush(cola, (g + w, nx, ny))
    return np.array(costo, dtype=np.float32).reshape(alto, ancho)


def elegir_meta(L, lo, pos, visitadas):
    """La meta (x, y en metros) de la frontera alcanzable mas cercana, o None si no hay ninguna."""
    trans, _ = zona_transitable(L, casco=True)
    ci = a_celda(pos, lo)
    ci2 = ci if trans[ci[1], ci[0]] else celda_mas_cercana(trans, ci)
    if ci2 is None:
        return None
    costo = costos_desde(trans, ci2)
    ys, xs = np.nonzero(trans)
    pm = np.stack([lo[0] + (xs + 0.5) * RES, lo[1] + (ys + 0.5) * RES], axis=1)
    ok = np.ones(len(xs), dtype=bool)
    for v in visitadas:
        ok &= np.hypot(pm[:, 0] - v[0], pm[:, 1] - v[1]) > REPETIDA
    fo, co = np.nonzero(L > UMBRAL_OCC)   # caja que envuelve a las paredes mapeadas
    if len(fo):
        x0, x1 = lo[0] + co.min() * RES - SALIDA_MAX, lo[0] + (co.max() + 1) * RES + SALIDA_MAX
        y0, y1 = lo[1] + fo.min() * RES - SALIDA_MAX, lo[1] + (fo.max() + 1) * RES + SALIDA_MAX
        ok &= (pm[:, 0] >= x0) & (pm[:, 0] <= x1) & (pm[:, 1] >= y0) & (pm[:, 1] <= y1)
    k = int(RADIO_META / RES)
    elipse = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (2 * k + 1, 2 * k + 1))
    mejor, mejor_costo = None, float("inf")
    for g in fronteras(L):
        m = np.zeros(L.shape, dtype=np.uint8)
        m[g[:, 1], g[:, 0]] = 1
        cerca = cv2.dilate(m, elipse)[ys, xs] > 0
        c = np.where(ok & cerca, costo[ys, xs], np.inf)
        i = int(c.argmin())
        if c[i] < mejor_costo:
            mejor, mejor_costo = pm[i], float(c[i])
    return mejor


def meta_sigue_valida(L, lo, meta):
    """True si todavia hay frontera cerca de la meta."""
    for g in fronteras(L):
        p = lo + (g + 0.5) * RES
        if np.hypot(p[:, 0] - meta[0], p[:, 1] - meta[1]).min() <= RADIO_META + 0.3:
            return True
    return False


def ruta_libre(L, lo, pos, waypoints, idx):
    """True si lo que falta de la ruta sigue siendo transitable con el mapa actualizado."""
    trans, _ = zona_transitable(L, casco=True)
    pts = [np.asarray(pos)] + [np.asarray(w) for w in waypoints[idx:]]
    for a, b in zip(pts[:-1], pts[1:]):
        ca, cb = a_celda(a, lo), a_celda(b, lo)
        if not (0 <= ca[1] < trans.shape[0] and 0 <= ca[0] < trans.shape[1] and 0 <= cb[1] < trans.shape[0] and 0 <= cb[0] < trans.shape[1]):
            return False
        if not trans[cb[1], cb[0]] or not linea_libre(trans, ca, cb):
            return False
    return True


def explorar_paso(L, lo, pos, ex, waypoints, idx, llegada):
    """Se llama cada segundo. Devuelve (waypoints nuevos o None si sigue igual, mensaje)."""
    t0 = time.perf_counter()
    if llegada and ex["meta"] is not None:
        ex["visitadas"].append(ex["meta"])
        ex["meta"] = None
    if ex["meta"] is not None:
        if meta_sigue_valida(L, lo, ex["meta"]):
            if ruta_libre(L, lo, pos, waypoints, idx):
                return None, ""
            wp, _, _ = planificador.planificar(L, lo, pos, ex["meta"], casco=True)
            if wp is not None and len(wp) > 0:
                return wp, f"ruta corregida hacia ({ex['meta'][0]:.1f}, {ex['meta'][1]:.1f}) por mapa nuevo"
        ex["meta"] = None   # la frontera ya se aclaro (o no hay ruta): se elige otra
    meta = elegir_meta(L, lo, pos, ex["visitadas"])
    if meta is None:
        ex["terminada"] = True
        return None, f"no quedan fronteras alcanzables: exploracion terminada ({len(ex['visitadas'])} metas visitadas)"
    wp, _, _ = planificador.planificar(L, lo, pos, meta, casco=True)
    if wp is None or len(wp) == 0:
        ex["visitadas"].append(meta)   # no se puede llegar (o ya esta ahi): que no la vuelva a elegir
        return None, f"meta ({meta[0]:.1f}, {meta[1]:.1f}) descartada"
    ex["meta"] = meta
    ex["metas"] += 1
    return wp, f"meta {ex['metas']}: frontera cerca de ({meta[0]:.1f}, {meta[1]:.1f}), {len(wp)} waypoints ({1000 * (time.perf_counter() - t0):.0f} ms)"
