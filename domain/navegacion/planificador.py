"""Planifica una ruta sobre un mapa de ocupacion (mapas/*_mapa_estimado.npz) hasta un destino (x, y).
Uso:  python navegacion/planificador.py X Y [X0 Y0] [mapa.npz]     (inicio por defecto: 0 0; sin mapa usa el ultimo)
Las coordenadas son del marco del mapa: origen en donde arranco el robot, x hacia adelante.
Imprime la linea 'waypoints: [...]' lista para g1_nav_config.yaml y guarda una imagen en mapas/."""
import glob
import heapq
import os
import sys

import cv2
import numpy as np

from domain.navegacion.mapa_ocupacion import RES, UMBRAL_OCC, dibujar

RADIO_ROBOT = 0.35      # m: distancia minima a paredes y a zonas desconocidas
DIST_COMODA = 1.0       # m: dentro de esta distancia a una pared el camino "cuesta mas", asi se centra en pasillos
PESO_PARED = 3.0        # cuanto mas caro es pasar pegado a una pared (0 = ir siempre por el camino mas corto)
CASCO_MARGEN = 0.0      # m: con casco=True el robot no se aleja de las paredes mapeadas mas que esto (ver dentro_de_paredes)
TRAMO_MAX = 2.0         # m: largo maximo de cada tramo recto entre waypoints


def cargar_mapa(ruta):
    m = np.load(ruta)
    if "logodds" not in m.files:
        sys.exit("[planificador] ese .npz es de una version vieja (solo tiene posiciones): volve a correr navegacion/odometria_lidar.py")
    return m["logodds"], m["origen_xy"], float(m["resolucion"])


def a_celda(p, lo):
    return int(np.floor((p[0] - lo[0]) / RES)), int(np.floor((p[1] - lo[1]) / RES))   # (columna, fila)


def a_metros(c, lo):
    return np.array([lo[0] + (c[0] + 0.5) * RES, lo[1] + (c[1] + 0.5) * RES])


def dentro_de_paredes(L):
    """Celdas que quedan dentro del casco convexo de las paredes mapeadas, mas CASCO_MARGEN. Una puerta o un hueco al exterior
    deja ver espacio "libre" mas alla de las paredes; sin paredes alrededor el SLAM se pierde, asi que alli el robot no planifica."""
    n, etiq, est, _ = cv2.connectedComponentsWithStats((L > UMBRAL_OCC).astype(np.uint8), connectivity=8)
    grande = np.zeros(max(n, 1), dtype=bool)
    grande[1:] = est[1:, cv2.CC_STAT_AREA] >= 6      # sin puntos sueltos
    ys, xs = np.nonzero(grande[etiq])
    if len(xs) < 3:
        return np.ones(L.shape, dtype=bool)
    casco = cv2.convexHull(np.stack([xs, ys], axis=1).astype(np.int32))
    m = np.zeros(L.shape, dtype=np.uint8)
    cv2.fillConvexPoly(m, casco, 1)
    k = int(CASCO_MARGEN / RES)
    if k > 0:
        m = cv2.dilate(m, cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (2 * k + 1, 2 * k + 1)))
    return m > 0


def zona_transitable(L, casco=False):
    """Celdas libres que ademas quedan a RADIO_ROBOT o mas de cualquier obstaculo o zona desconocida.
    Con casco=True, ademas dentro de las paredes mapeadas (dentro_de_paredes)."""
    libre = (L < -0.2).astype(np.uint8)
    dist = cv2.distanceTransform(libre, cv2.DIST_L2, 5) * RES   # m hasta lo no libre mas cercano
    trans = dist >= RADIO_ROBOT
    if casco:
        trans &= dentro_de_paredes(L)
    return trans, dist


def celda_mas_cercana(trans, c, max_m=1.0):
    ys, xs = np.nonzero(trans)
    if len(xs) == 0:
        return None
    d = np.hypot(xs - c[0], ys - c[1]) * RES
    i = d.argmin()
    return (int(xs[i]), int(ys[i])) if d[i] <= max_m else None


def a_estrella(trans, dist, ini, fin):
    """Camino de celdas (columna, fila) de ini a fin, o None. 8 vecinos; cuesta mas ir pegado a las paredes."""
    alto, ancho = trans.shape
    pasos = [(1, 0, 1.0), (-1, 0, 1.0), (0, 1, 1.0), (0, -1, 1.0),
             (1, 1, 1.4142), (1, -1, 1.4142), (-1, 1, 1.4142), (-1, -1, 1.4142)]
    g = {ini: 0.0}
    padre = {}
    abiertos = [(0.0, ini)]
    while abiertos:
        _, c = heapq.heappop(abiertos)
        if c == fin:
            ruta = [c]
            while c in padre:
                c = padre[c]
                ruta.append(c)
            return ruta[::-1]
        for dx, dy, costo in pasos:
            n = (c[0] + dx, c[1] + dy)
            if not (0 <= n[0] < ancho and 0 <= n[1] < alto) or not trans[n[1], n[0]]:
                continue
            extra = PESO_PARED * max(0.0, DIST_COMODA - dist[n[1], n[0]]) / DIST_COMODA
            gn = g[c] + costo * (1.0 + extra)
            if gn < g.get(n, 1e18):
                g[n] = gn
                padre[n] = c
                h = np.hypot(fin[0] - n[0], fin[1] - n[1])
                heapq.heappush(abiertos, (gn + h, n))
    return None


def linea_libre(trans, a, b):
    m = np.zeros(trans.shape, dtype=np.uint8)
    cv2.line(m, a, b, 1)
    return bool(trans[m > 0].all())


def simplificar(trans, ruta):
    """Deja solo los puntos donde hace falta doblar: tramos rectos lo mas largos posible (hasta TRAMO_MAX)."""
    maxc = TRAMO_MAX / RES
    sal = [ruta[0]]
    i = 0
    while i < len(ruta) - 1:
        j = len(ruta) - 1
        while j > i + 1 and (np.hypot(ruta[j][0] - ruta[i][0], ruta[j][1] - ruta[i][1]) > maxc
                             or not linea_libre(trans, ruta[i], ruta[j])):
            j -= 1
        sal.append(ruta[j])
        i = j
    return sal


def planificar(L, lo, inicio, destino, casco=False):
    """Devuelve (waypoints en metros sin el punto de inicio, camino completo en metros, mensaje)."""
    trans, dist = zona_transitable(L, casco)
    ci, cf = a_celda(inicio, lo), a_celda(destino, lo)
    ci2 = ci if trans[ci[1], ci[0]] else celda_mas_cercana(trans, ci)
    if ci2 is None:
        return None, None, "el inicio cae en una zona sin espacio libre conocido"
    cf2 = cf if (0 <= cf[1] < trans.shape[0] and 0 <= cf[0] < trans.shape[1] and trans[cf[1], cf[0]]) else celda_mas_cercana(trans, cf)
    if cf2 is None:
        return None, None, "el destino esta fuera del mapa, pegado a una pared o en zona desconocida (a mas de 1 m de lo transitable)"
    ruta = a_estrella(trans, dist, ci2, cf2)
    if ruta is None:
        return None, None, "no hay camino libre entre el inicio y el destino (puede estar en una zona que el mapa no conecta)"
    msg = "" if cf2 == cf else f"destino ajustado a ({a_metros(cf2, lo)[0]:.2f}, {a_metros(cf2, lo)[1]:.2f}) por estar muy cerca de una pared"
    wp = [a_metros(c, lo) for c in simplificar(trans, ruta)[1:]]
    return np.array(wp), np.array([a_metros(c, lo) for c in ruta]), msg


def main():
    args = [a for a in sys.argv[1:] if not a.endswith(".npz")]
    raiz = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    ruta_mapa = next((a for a in sys.argv[1:] if a.endswith(".npz")), None)
    if ruta_mapa is None:
        ruta_mapa = sorted(glob.glob(os.path.join(raiz, "mapas", "*_mapa_estimado.npz")))[-1]
    if len(args) not in (2, 4):
        sys.exit("uso: python navegacion/planificador.py X Y [X0 Y0] [mapa.npz]")
    destino = np.array([float(args[0]), float(args[1])])
    inicio = np.array([float(args[2]), float(args[3])]) if len(args) == 4 else np.zeros(2)
    L, lo, _ = cargar_mapa(ruta_mapa)
    wp, camino, msg = planificar(L, lo, inicio, destino)
    if wp is None:
        sys.exit(f"[planificador] sin ruta: {msg}")
    if msg:
        print(f"[planificador] {msg}")
    largo = np.linalg.norm(np.diff(camino, axis=0), axis=1).sum()
    print(f"[planificador] ruta de {largo:.1f} m con {len(wp)} waypoints (mapa: {os.path.basename(ruta_mapa)})")
    print("waypoints: [" + ", ".join(f"[{x:.2f}, {y:.2f}]" for x, y in wp) + "]")
    png = os.path.join(raiz, "mapas", f"ruta_a_{destino[0]:.1f}_{destino[1]:.1f}.png")
    dibujar(L, lo, camino, wp, png)
    print(f"[planificador] imagen: {png}")


if __name__ == "__main__":
    main()
