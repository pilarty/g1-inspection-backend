"""(sacado de mapa_vivo.py) Replanificacion de la ruta cuando aparece un obstaculo nuevo. Corre en el backend."""
import numpy as np

from domain.navegacion import planificador
def replanificar(L, lo, off, nuevas, pos, waypoints, idx, destino):
    """Si lo que falta de la ruta cruza obstaculos nuevos, calcula otra ruta desde 'pos' (x, y del mundo).
    Devuelve (waypoints del mundo, mensaje). waypoints None y mensaje '' = la ruta sigue libre, no hace falta nada;
    waypoints None y mensaje con texto = la ruta esta bloqueada y no hay otra."""
    L2 = L.copy()
    L2[nuevas] = 4.0                                        # los obstaculos nuevos pasan a ser parte del mapa
    trans_viejo, _ = planificador.zona_transitable(L)
    trans_nuevo, _ = planificador.zona_transitable(L2)
    puntos = [np.asarray(pos, dtype=float) - off] + [np.asarray(w, dtype=float) - off for w in waypoints[idx:]]
    celdas = [planificador.a_celda(p, lo) for p in puntos]
    bloqueada = any(planificador.linea_libre(trans_viejo, a, b) and not planificador.linea_libre(trans_nuevo, a, b)
                    for a, b in zip(celdas[:-1], celdas[1:]))
    if not bloqueada:
        return None, ""
    wp, _, msg = planificador.planificar(L2, lo, puntos[0], np.asarray(destino, dtype=float) - off)
    if wp is None:
        return None, msg
    return (wp + off).tolist(), msg
