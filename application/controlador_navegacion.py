import threading

from domain.navegacion import cobertura, exploracion, inspeccion_decision, planificador, replanificacion, vista_fina

# MIN_GANANCIA y cobertura.DIST_MAX son variables del modulo: se fijan con los parametros que trae cada llamada.
# El cerrojo evita que dos llamadas con parametros distintos se pisen; solo lo usan las dos rutas que dependen de ellos.
_cerrojo = threading.Lock()


def _explorar(L, lo, pos, ex, waypoints, idx, llegada):
    wp, msg = exploracion.explorar_paso(L, lo, pos, ex, waypoints, idx, llegada)
    return wp, msg, ex  # ex se modifica en el lugar: el robot lo recibe de vuelta


def _cob_foto(cob, L, lo, cam_pos, R_cam, depth, f, params):
    with _cerrojo:
        inspeccion_decision.aplicar_parametros(params)
        cobertura.cob_foto(cob, L, lo, cam_pos, R_cam, depth, f)
    return cob


def _elegir(L, Lv, lo, cob, ins, pos, cam_z, params):
    with _cerrojo:
        return inspeccion_decision.elegir(L, Lv, lo, cob, ins, pos, cam_z, params)


CALCULOS = {
    "explorar": _explorar,
    "inspeccion_elegir": _elegir,
    "fina_vista": vista_fina.vista,
    "planificar": planificador.planificar,
    "replanificar": replanificacion.replanificar,
    "cob_foto": _cob_foto,
    "cob_crear": cobertura.cob_crear,
    "cob_resumen": cobertura.cob_resumen,
    "cob_texto": cobertura.cob_texto,
    "cob_texto_zonas": cobertura.cob_texto_zonas,
    "cob_por_altura": cobertura.cob_por_altura,
    "cob_dibujar": cobertura.cob_dibujar,
}


def calcular(nombre: str, args: tuple):
    """KeyError si el calculo no existe."""
    return CALCULOS[nombre](*args)
