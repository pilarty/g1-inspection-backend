"""Prueba rapida de los calculos de navegacion (no necesita el robot ni los modelos). Uso, desde la carpeta del backend:  python prueba_navegacion.py"""
import sys

sys.dont_write_bytecode = True

import numpy as np
from fastapi import HTTPException

from api import codec_navegacion as codec
from api.routes import navegacion


def llamar(nombre, *args):
    """Lo mismo que hace el robot: empaqueta, pasa por la ruta y desempaqueta."""
    return codec.desempaquetar(navegacion._atender(nombre, codec.empaquetar(args)))["r"]


def rechaza(nombre, cuerpo, codigo):
    try:
        navegacion._atender(nombre, cuerpo)
    except HTTPException as e:
        assert e.status_code == codigo, (nombre, e.status_code)
        return
    raise AssertionError(f"{nombre}: tendria que dar {codigo}")


# 1. el formato conserva tipos, claves no-texto y arrays (escribibles)
x = {"a": (1, [2.5, None]), (1, 2): np.float32(1.5), 7: {3, 4}, "m": np.arange(6, dtype=np.int16).reshape(2, 3)}
y = codec.desempaquetar(codec.empaquetar(x))
assert list(y) == list(x) and y["a"] == x["a"] and y[7] == {3, 4} and type(y[(1, 2)]) is np.float32
assert np.array_equal(y["m"], x["m"]) and y["m"].flags.writeable

# 2. lo que no es del formato se rechaza (un pickle no se ejecuta ni se lee)
import pickle
rechaza("explorar", pickle.dumps(("x",)), 400)
rechaza("no_existe", codec.empaquetar(()), 404)
rechaza("cob_resumen", codec.empaquetar((1, 2, 3, 4)), 422)

# 3. un calculo real: planificar en una sala de 10 x 10 m (celdas de 5 cm) con una pared en el medio y un hueco
L = np.full((200, 200), -2.0, np.float32)
L[:2], L[-2:], L[:, :2], L[:, -2:] = 3, 3, 3, 3
L[:140, 100:103] = 3                      # pared de x=0 a 0.15 m, con paso libre abajo (filas 140 en adelante)
wp, camino, msg = llamar("planificar", L, np.array([-5.0, -5.0]), np.array([-3.0, -3.0]), np.array([3.0, -3.0]))
assert wp is not None and np.hypot(*(wp[-1] - np.array([3.0, -3.0]))) < 0.1, msg
assert (camino[:, 1] > -5.0 + 140 * 0.05 - 0.05).any(), "tendria que rodear la pared"

# 4. el estado de cobertura viaja de ida y vuelta
cob = llamar("cob_crear", 2.8, 6)
assert llamar("cob_resumen", cob)[0] == 0.0
print("navegacion: todo bien")
