"""Cobertura de inspeccion: que partes de las paredes vio la CAMARA en condiciones de poder detectar danos.
Las paredes salen del mapa del SLAM, se dividen en parches de 0,5 m por bandas de altura, y un parche-banda cuenta como inspeccionado
si en alguna imagen estuvo dentro del encuadre, a distancia razonable, de frente (no de costado) y sin nada adelante (se verifica
contra la imagen de profundidad, no contra el LiDAR)."""
import cv2
import numpy as np

from domain.navegacion.mapa_ocupacion import RES, UMBRAL_OCC

PARCHE = 0.5            # m de pared por parche
DIST_MIN, DIST_MAX = 0.7, 2.0   # m, profundidad de la camara al parche (2 m ~ 8 mm por pixel en la foto de 640 px)
BANDAS_BAJO = 4         # un parche con al menos tantas bandas "sin pared a esa altura" es un objeto bajo (mueble, escombro, caja), no estructura: se descarta
ANGULO_MAX = 60.0       # grados entre la normal de la pared y la direccion hacia la camara (en 3D)
TOL_PROF = 0.35         # m: la profundidad medida tiene que coincidir con la esperada para dar por vista esa pared
MARGEN_PX = 8           # el parche tiene que caer al menos a esto del borde de la imagen
CELDAS_MIN = 4          # un parche con menos celdas de pared es ruido del mapa
BINES_NORMAL = 12       # las normales se agrupan de a 30 grados: asi las dos caras de una pared fina no se mezclan


def cob_crear(alto_pared=2.8, bandas=6):
    return {"alto": alto_pared, "nb": bandas, "estado": {}, "geom": {}}   # estado: 0 sin ver, 1 cubierto, 2 vacio (ahi no hay pared)


def superficies(L, lo):
    """Parches de pared del mapa: (claves, centros (n,2) en m, normales (n,2) hacia el lado libre)."""
    ocup = L > UMBRAL_OCC
    libre = (L < -0.2).astype(np.float32)
    toca_libre = cv2.dilate(libre.astype(np.uint8), np.ones((3, 3), np.uint8)) > 0
    sup = ocup & toca_libre
    suave = cv2.GaussianBlur(libre, (0, 0), 3)
    gx, gy = cv2.Sobel(suave, cv2.CV_32F, 1, 0), cv2.Sobel(suave, cv2.CV_32F, 0, 1)
    f, c = np.nonzero(sup)
    n = np.stack([gx[f, c], gy[f, c]], axis=1)
    mod = np.hypot(n[:, 0], n[:, 1])
    ok = mod > 1e-4
    f, c, n, mod = f[ok], c[ok], n[ok], mod[ok]
    if len(f) == 0:
        return [], np.zeros((0, 2)), np.zeros((0, 2))
    n = n / mod[:, None]
    p = lo + (np.stack([c, f], axis=1) + 0.5) * RES
    ang = np.arctan2(n[:, 1], n[:, 0])
    bn = np.floor(((ang + np.pi) / (2 * np.pi)) * BINES_NORMAL).astype(np.int64) % BINES_NORMAL
    bx, by = np.floor(p[:, 0] / PARCHE).astype(np.int64), np.floor(p[:, 1] / PARCHE).astype(np.int64)
    clave = ((bx + 5000) * 10000 + (by + 5000)) * BINES_NORMAL + bn
    u, inv, cuenta = np.unique(clave, return_inverse=True, return_counts=True)
    cen = np.stack([np.bincount(inv, p[:, 0]), np.bincount(inv, p[:, 1])], axis=1) / cuenta[:, None]
    nor = np.stack([np.bincount(inv, n[:, 0]), np.bincount(inv, n[:, 1])], axis=1)
    nor /= np.maximum(np.hypot(nor[:, 0], nor[:, 1]), 1e-9)[:, None]
    bien = cuenta >= CELDAS_MIN
    return [int(k) for k in u[bien]], cen[bien], nor[bien]


def cob_foto(cob, L, lo, cam_pos, R_cam, depth, f):
    """Suma lo que vio una imagen. cam_pos (3,) y R_cam (3,3): pose de la camara en el marco del mapa (camara MuJoCo: x der, y arriba, mira por -z).
    depth: imagen de profundidad en m (inf = invalida); f: distancia focal en pixeles."""
    claves, cen, nor = superficies(L, lo)
    if not claves:
        return
    nb = cob["nb"]
    alto_img, ancho_img = depth.shape
    zb = (np.arange(nb) + 0.5) * cob["alto"] / nb
    P = np.zeros((len(claves), nb, 3))
    P[:, :, 0], P[:, :, 1], P[:, :, 2] = cen[:, None, 0], cen[:, None, 1], zb[None, :]
    rel = P - np.asarray(cam_pos)
    pc = rel @ R_cam                        # R_cam.T @ rel, por fila
    fwd = -pc[:, :, 2]
    adelante = fwd > 1e-6
    fw = np.where(adelante, fwd, 1.0)
    u = ancho_img / 2 + f * pc[:, :, 0] / fw
    v = alto_img / 2 - f * pc[:, :, 1] / fw
    dentro = (u >= MARGEN_PX) & (u < ancho_img - MARGEN_PX) & (v >= MARGEN_PX) & (v < alto_img - MARGEN_PX)
    dist3 = np.maximum(np.linalg.norm(rel, axis=2), 1e-9)
    cos_inc = -(rel[:, :, 0] * nor[:, None, 0] + rel[:, :, 1] * nor[:, None, 1]) / dist3
    cand = adelante & dentro & (fwd >= DIST_MIN) & (fwd <= DIST_MAX) & (cos_inc >= np.cos(np.radians(ANGULO_MAX)))
    iu = np.clip(np.round(u).astype(int), 1, ancho_img - 2)
    iv = np.clip(np.round(v).astype(int), 1, alto_img - 2)
    coincide = np.zeros(cand.shape, dtype=bool)
    detras = np.ones(cand.shape, dtype=bool)          # todos los vecinos miden mas lejos que lo esperado (o nada): ahi no hay pared
    for dv in (-1, 0, 1):
        for du in (-1, 0, 1):
            zd = depth[iv + dv, iu + du]
            coincide |= np.abs(zd - fwd) <= TOL_PROF
            detras &= ~np.isfinite(zd) | (zd > fwd + TOL_PROF)
    cubierto, vacio = cand & coincide, cand & detras
    for i, k in enumerate(claves):
        est = cob["estado"].setdefault(k, np.zeros(nb, dtype=np.uint8))
        est[cubierto[i]] = 1
        est[vacio[i] & (est == 0)] = 2
        if (est == 2).sum() >= BANDAS_BAJO:
            est[:] = 2
        cob["geom"][k] = (cen[i].copy(), nor[i].copy())


def cob_resumen(cob):
    """(porcentaje, cubiertos, sin ver, vacios): sobre parches-banda; los vacios (no hay pared a esa altura) no cuentan."""
    if not cob["estado"]:
        return 0.0, 0, 0, 0
    e = np.concatenate(list(cob["estado"].values()))
    cub, sin, vac = int((e == 1).sum()), int((e == 0).sum()), int((e == 2).sum())
    return 100.0 * cub / max(cub + sin, 1), cub, sin, vac


def cob_texto(cob):
    pct, cub, sin, vac = cob_resumen(cob)
    return f"{pct:.0f}% de la pared inspeccionada ({cub} de {cub + sin} tramos-altura; {len(cob['estado'])} parches de {PARCHE} m, {vac} sin pared a esa altura)"


def cob_dibujar(cob, L, lo, trayecto, px_por_m=40):
    """Mapa con cada parche de pared coloreado: rojo = nada visto, verde = todo visto (entre medio: amarillo)."""
    f = px_por_m * RES
    img = np.full(L.shape + (3,), 160, np.uint8)
    img[L < -0.2] = (255, 255, 255)
    img[L > UMBRAL_OCC] = (0, 0, 0)
    img = cv2.resize(img, None, fx=f, fy=f, interpolation=cv2.INTER_NEAREST)

    def px(a):
        return np.round((np.asarray(a) - lo) / RES * f).astype(np.int32)
    cv2.polylines(img, [px(trayecto).reshape(-1, 1, 2)], False, (220, 120, 0), 1, cv2.LINE_AA)
    for k, est in cob["estado"].items():
        medibles = int((est != 2).sum())
        if medibles == 0:
            continue
        frac = float((est == 1).sum()) / medibles
        color = (0, int(200 * min(1.0, 2 * frac)) + 30, int(220 * min(1.0, 2 * (1 - frac))) + 30) if frac < 1 else (0, 170, 0)   # BGR
        cen, nor = cob["geom"][k]
        tan = np.array([-nor[1], nor[0]])
        a, b = cen + 0.12 * nor - 0.24 * tan, cen + 0.12 * nor + 0.24 * tan
        cv2.line(img, tuple(int(x) for x in px(a)), tuple(int(x) for x in px(b)), color, 5)
    return cv2.imencode(".png", img[::-1])[1].tobytes()   # el robot guarda el archivo


def cob_por_zona(cob, L, lo, tol=0.35):
    """Cobertura separada en (perimetro, objetos): los parches pegados al contorno exterior del espacio libre son las paredes del recinto;
    los demas son objetos sueltos (columnas, muebles, divisiones). Devuelve ((pct, tramos), (pct, tramos)); pct None si no hay parches de ese tipo."""
    libre = cv2.morphologyEx((L < -0.2).astype(np.uint8), cv2.MORPH_CLOSE, np.ones((5, 5), np.uint8))
    n, etiq, est, _ = cv2.connectedComponentsWithStats(libre, connectivity=8)
    if n < 2 or not cob["estado"]:
        return (None, 0), (None, 0)
    mayor = (etiq == 1 + int(np.argmax(est[1:, cv2.CC_STAT_AREA]))).astype(np.uint8)
    cont, _ = cv2.findContours(mayor, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_NONE)   # solo el contorno de afuera: los objetos son huecos adentro
    borde = np.zeros(L.shape, np.uint8)
    cv2.drawContours(borde, cont, -1, 1, 1)
    dist = cv2.distanceTransform((borde == 0).astype(np.uint8), cv2.DIST_L2, 5) * RES
    cuenta = {True: [0, 0], False: [0, 0]}   # perimetro?: [cubiertos, medibles]
    for k, e in cob["estado"].items():
        c = np.floor((cob["geom"][k][0] - lo) / RES).astype(int)
        if not (0 <= c[1] < L.shape[0] and 0 <= c[0] < L.shape[1]):
            continue
        z = cuenta[bool(dist[c[1], c[0]] <= tol)]
        z[0] += int((e == 1).sum())
        z[1] += int((e != 2).sum())
    return tuple((100.0 * z[0] / z[1] if z[1] else None, z[1]) for z in (cuenta[True], cuenta[False]))


def cob_texto_zonas(cob, L, lo):
    (pp, np_), (po, no) = cob_por_zona(cob, L, lo)
    f = lambda p, n: "sin tramos" if p is None else f"{p:.0f}% de {n} tramos-altura"
    return f"paredes del perimetro {f(pp, np_)}; objetos dentro de la sala {f(po, no)}"


def cob_registrar(cob, L, lo):
    """Pone al dia los parches de pared con el mapa actual. Los parches del mapa viejo que ya no existen se descartan (si no, quedan "fantasmas"
    que nunca se pueden ver); lo ya visto pasa a los parches nuevos que quedan en el mismo lugar y de frente al mismo lado."""
    claves, cen, nor = superficies(L, lo)
    viejas = [k for k in cob["estado"] if k in cob["geom"]]
    if viejas:
        vc = np.array([cob["geom"][k][0] for k in viejas])
        vn = np.array([cob["geom"][k][1] for k in viejas])
        ve = np.array([cob["estado"][k] for k in viejas])
    estado, geom = {}, {}
    for i, k in enumerate(claves):
        if k in cob["estado"]:
            est = cob["estado"][k].copy()
        else:
            est = np.zeros(cob["nb"], dtype=np.uint8)
            if viejas:
                cerca = (np.hypot(vc[:, 0] - cen[i, 0], vc[:, 1] - cen[i, 1]) <= 0.35) & (vn @ nor[i] >= 0.7)
                if cerca.any():
                    e = ve[cerca]
                    est[(e == 2).any(axis=0)] = 2
                    est[(e == 1).any(axis=0)] = 1
        estado[k] = est
        geom[k] = (cen[i].copy(), nor[i].copy())
    cob["estado"], cob["geom"] = estado, geom


def cob_por_altura(cob):
    """Porcentaje inspeccionado en cada banda de altura, de abajo hacia arriba: [(desde_m, hasta_m, porcentaje)]."""
    if not cob["estado"]:
        return []
    E = np.array(list(cob["estado"].values()))
    h = cob["alto"] / cob["nb"]
    sal = []
    for b in range(cob["nb"]):
        cub, sin = int((E[:, b] == 1).sum()), int((E[:, b] == 0).sum())
        sal.append((b * h, (b + 1) * h, 100.0 * cub / max(cub + sin, 1)))
    return sal
