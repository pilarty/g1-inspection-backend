"""Mapa de ocupacion 2D a partir de una corrida grabada (grabaciones/*.npz) usando la pose REAL del robot.
Uso:  python navegacion/mapa_ocupacion.py [grabaciones/corrida_X.npz]   (sin argumento usa la ultima)
Solo depende del .npz y de sensores.json: no lee el escenario."""
import glob
import json
import os
import sys

import cv2
import numpy as np

RES = 0.05            # m por celda
BANDA = (-0.6, 0.8)   # alturas (m) respecto al torso que cuentan como obstaculo; mas abajo = piso, mas arriba = techo
USAR_1_DE = 2         # usa 1 de cada N barridos (2 -> 5 Hz)
L_OCC, L_LIBRE = 0.85, -0.4   # cuanto suma/resta cada observacion (log-odds)
L_TOPE = 4.0
UMBRAL_OCC = 0.5


def direcciones_lidar(cal):
    """Direcciones de los rayos en el marco del torso, en el mismo orden en que se grabaron."""
    n_az = cal["lidar"]["rayos_por_giro"]
    az = np.deg2rad(np.arange(n_az) * 360.0 / n_az)
    el = np.deg2rad(cal["lidar"]["elevaciones_grados"])
    A, E = np.meshgrid(az, el)
    return np.stack([np.cos(E) * np.cos(A), np.cos(E) * np.sin(A), np.sin(E)], axis=-1).reshape(-1, 3)


def puntos_por_barrido(d, cal, usar_1_de):
    """Por cada barrido: origen del LiDAR y extremos de los rayos (marco del mundo), separados en obstaculo / piso."""
    dirs = direcciones_lidar(cal)
    off = np.array(cal["lidar"]["pos_en_base_m"])
    out = []
    for i in range(0, len(d["lidar_idx"]), usar_1_de):
        k = d["lidar_idx"][i]
        R, pos = d["torso_mat"][k], d["torso_pos"][k]
        o = pos + R @ off
        r = d["lidar"][i]
        hit = np.isfinite(r) & (r <= cal["lidar"]["rango_m"][1])   # descarta lo que paso del rango maximo
        p = o + (dirs[hit] @ R.T) * r[hit, None]
        z_rel = p[:, 2] - pos[2]
        out.append((o, p[(z_rel > BANDA[0]) & (z_rel < BANDA[1])], p[z_rel <= BANDA[0]]))
    return out


def construir_mapa(barridos, xy0, c, s):
    """Pasa todo al marco del primer pose (origen y rumbo iniciales) y acumula log-odds en una grilla."""
    Rinv = np.array([[c, s], [-s, c]])
    def tr(a):
        return (a[:, :2] - xy0) @ Rinv.T
    tr_b = [(tr(o[None]), tr(occ), tr(piso)) for o, occ, piso in barridos]
    todo = np.vstack([np.vstack(b) for b in tr_b])
    lo = todo.min(axis=0) - 0.5
    hi = todo.max(axis=0) + 0.5
    shape = np.ceil((hi - lo) / RES).astype(int)[::-1]   # (filas=y, columnas=x)
    L = np.zeros(shape, dtype=np.float32)
    def celda(a):
        return np.floor((a - lo) / RES).astype(np.int32)
    for o, occ, piso in tr_b:
        co = tuple(celda(o)[0])
        libre = np.zeros(shape, dtype=np.uint8)
        for e in celda(np.vstack([occ, piso])):
            cv2.line(libre, co, (int(e[0]), int(e[1])), 1)
        ocup = np.zeros(shape, dtype=bool)
        ce = celda(occ)
        ocup[ce[:, 1], ce[:, 0]] = True
        L[(libre > 0) & ~ocup] += L_LIBRE
        L[ocup] += L_OCC
        np.clip(L, -L_TOPE, L_TOPE, out=L)
    return L, lo, tr


def dibujar(L, lo, trayecto, waypoints, ruta_png, px_por_m=40, trayecto_ref=None, nuevas=None):
    f = px_por_m * RES
    img = np.full(L.shape + (3,), 160, np.uint8)       # gris = desconocido
    img[L < -0.2] = (255, 255, 255)                    # blanco = libre
    img[L > UMBRAL_OCC] = (0, 0, 0)                    # negro = ocupado
    if nuevas is not None:
        img[nuevas] = (255, 0, 255)                    # magenta = obstaculo que el mapa guardado no tenia
    img = cv2.resize(img, None, fx=f, fy=f, interpolation=cv2.INTER_NEAREST)
    def px(a):
        return np.round((a - lo) / RES * f).astype(np.int32)
    if trayecto_ref is not None:                       # verde = recorrido real (solo para comparar)
        cv2.polylines(img, [px(trayecto_ref).reshape(-1, 1, 2)], False, (0, 170, 0), 1, cv2.LINE_AA)
    cv2.polylines(img, [px(trayecto).reshape(-1, 1, 2)], False, (220, 120, 0), 1, cv2.LINE_AA)
    for w in px(waypoints):
        cv2.circle(img, (int(w[0]), int(w[1])), 5, (0, 0, 220), -1, cv2.LINE_AA)
    cv2.imwrite(ruta_png, img[::-1])                   # y hacia arriba


def main():
    raiz = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    ruta = sys.argv[1] if len(sys.argv) > 1 else sorted(glob.glob(os.path.join(raiz, "grabaciones", "*.npz")))[-1]
    d = np.load(ruta)
    d = {k: d[k] for k in d.files}
    with open(os.path.join(raiz, "sensores.json")) as f:
        cal = json.load(f)
    R0 = d["torso_mat"][0]
    yaw0 = np.arctan2(R0[1, 0], R0[0, 0])
    c, s = np.cos(yaw0), np.sin(yaw0)
    xy0 = d["torso_pos"][0, :2]
    barridos = puntos_por_barrido(d, cal, USAR_1_DE)
    L, lo, tr = construir_mapa(barridos, xy0, c, s)
    os.makedirs(os.path.join(raiz, "mapas"), exist_ok=True)
    base = os.path.join(raiz, "mapas", os.path.splitext(os.path.basename(ruta))[0] + "_mapa_real")
    np.savez_compressed(base + ".npz", logodds=L, origen_xy=lo, resolucion=RES)
    dibujar(L, lo, tr(d["torso_pos"]), tr(d["waypoints"]), base + ".png")
    print(f"[mapa] {L.shape[1]}x{L.shape[0]} celdas ({L.shape[1]*RES:.1f} x {L.shape[0]*RES:.1f} m), "
          f"ocupadas {(L > UMBRAL_OCC).mean()*100:.1f}%, libres {(L < -0.2).mean()*100:.1f}%, desconocidas {(np.abs(L) <= 0.2).mean()*100:.1f}%")
    print(f"[mapa] guardado: {base}.png")


if __name__ == "__main__":
    main()
