import json
from typing import Tuple

import threading

import numpy as np
from PIL import Image

from config import CALIBRACION_DETECCION_PATH, MODELO_DETECCION_PATH

# Temperatura y umbral elegidos en validacion (notebook de entrenamiento v3).
# Sin archivo de calibracion, las probabilidades se usan tal cual con umbral 0.5.
_calibracion = {}
if CALIBRACION_DETECCION_PATH.exists():
    _calibracion = json.loads(CALIBRACION_DETECCION_PATH.read_text(encoding="utf-8"))
TEMPERATURA = float(_calibracion.get("temperatura", 1.0))
UMBRAL_DANIO = float(_calibracion.get("umbral_dano", 0.5))

# El modelo se carga recién cuando se lo necesita (o en segundo plano al arrancar),
# así la app abre sin esperar a TensorFlow.
_modelo = None
_cerrojo = threading.Lock()


def cargar():
    global _modelo
    with _cerrojo:
        if _modelo is None:
            import tensorflow as tf
            _modelo = tf.keras.models.load_model(str(MODELO_DETECCION_PATH))
    return _modelo


def hay_dano(imagen: Image.Image) -> Tuple[bool, float]:
    """Devuelve (hay_dano, probabilidad_de_dano). El modelo predice la
    probabilidad de que la imagen esté SIN daño ("undamaged"), por eso
    se invierte. Antes de compararla con el umbral se calibra: se pasa a
    logit, se divide por la temperatura y se vuelve a sigmoid."""
    img_array = np.expand_dims(np.array(imagen), axis=0)
    prob_sin_dano = float(cargar().predict(img_array, verbose=0)[0][0])
    p = min(max(prob_sin_dano, 1e-6), 1 - 1e-6)
    logit_dano = np.log((1 - p) / p)
    prob_dano = float(1 / (1 + np.exp(-logit_dano / TEMPERATURA)))
    return prob_dano >= UMBRAL_DANIO, prob_dano
