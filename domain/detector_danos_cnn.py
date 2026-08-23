from typing import Tuple

import numpy as np
import tensorflow as tf
from PIL import Image

from config import MODELO_DETECCION_PATH

UMBRAL_DANIO = 0.5

_modelo = tf.keras.models.load_model(str(MODELO_DETECCION_PATH))


def hay_dano(imagen: Image.Image) -> Tuple[bool, float]:
    """Devuelve (hay_dano, probabilidad_de_dano). El modelo predice la
    probabilidad de que la imagen esté SIN daño ("undamaged"), por eso
    se invierte antes de compararla con el umbral."""
    img_array = np.expand_dims(np.array(imagen), axis=0)
    prob_sin_dano = float(_modelo.predict(img_array, verbose=0)[0][0])
    prob_dano = 1 - prob_sin_dano
    return prob_dano >= UMBRAL_DANIO, prob_dano
