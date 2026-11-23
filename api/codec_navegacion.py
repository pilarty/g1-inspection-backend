"""Formato de las llamadas de navegacion entre el robot y el backend (el robot tiene una copia identica).

Reemplaza a pickle: leer un pickle que llega por la red ejecuta codigo del que lo manda, y este backend escucha en 0.0.0.0
sin autenticacion. Aca solo se aceptan None, bool, int, float, str, bytes, list, tuple, dict, set, numpy (arrays y escalares
de tipos numericos): cualquier otra cosa se rechaza, tanto al armar como al leer.

Formato: zlib(nivel 1) de  b"G1N1" + largo del encabezado (4 bytes) + encabezado JSON + datos de los arrays.
Los diccionarios viajan como lista de pares porque las claves pueden ser enteros o tuplas (JSON solo admite texto).
"""
import base64
import json
import struct
import zlib

import numpy as np

MAGIA = b"G1N1"
DTYPES = {"bool", "int8", "int16", "int32", "int64", "uint8", "uint16", "uint32", "uint64", "float16", "float32", "float64"}
MAX_BYTES = 256 * 1024 * 1024  # tope de lo que se descomprime (evita bombas de compresion)


def _codificar(x, arrays):
    if x is None or isinstance(x, (bool, str)):
        return x
    if isinstance(x, (int, float)) and not isinstance(x, (np.integer, np.floating)):
        return x
    if isinstance(x, list):
        return [_codificar(v, arrays) for v in x]
    if isinstance(x, tuple):
        return {"__t": [_codificar(v, arrays) for v in x]}
    if isinstance(x, dict):
        return {"__d": [[_codificar(k, arrays), _codificar(v, arrays)] for k, v in x.items()]}
    if isinstance(x, (set, frozenset)):
        return {"__s": [_codificar(v, arrays) for v in x]}
    if isinstance(x, bytes):
        return {"__b": base64.b64encode(x).decode("ascii")}
    if isinstance(x, np.generic):
        if x.dtype.name not in DTYPES:
            raise TypeError(f"tipo numpy no admitido: {x.dtype}")
        return {"__g": [x.dtype.name, x.item()]}
    if isinstance(x, np.ndarray):
        if x.dtype.name not in DTYPES:
            raise TypeError(f"tipo de array no admitido: {x.dtype}")
        arrays.append(np.ascontiguousarray(x))
        return {"__a": [len(arrays) - 1, x.dtype.name, list(x.shape)]}
    raise TypeError(f"tipo no admitido: {type(x).__name__}")


def empaquetar(objeto) -> bytes:
    arrays = []
    estructura = _codificar(objeto, arrays)
    encabezado = json.dumps(estructura, separators=(",", ":")).encode("utf-8")
    partes = [MAGIA, struct.pack("<I", len(encabezado)), encabezado]
    partes += [a.tobytes() for a in arrays]
    return zlib.compress(b"".join(partes), 1)


def _decodificar(x, datos, offsets):
    if isinstance(x, list):
        return [_decodificar(v, datos, offsets) for v in x]
    if not isinstance(x, dict):
        return x
    if len(x) != 1:
        raise ValueError("estructura invalida")
    (tag, v), = x.items()
    if tag == "__t":
        return tuple(_decodificar(e, datos, offsets) for e in v)
    if tag == "__d":
        return {_decodificar(k, datos, offsets): _decodificar(e, datos, offsets) for k, e in v}
    if tag == "__s":
        return set(_decodificar(e, datos, offsets) for e in v)
    if tag == "__b":
        return base64.b64decode(v)
    if tag == "__g":
        if v[0] not in DTYPES:
            raise ValueError("dtype no admitido")
        return np.dtype(v[0]).type(v[1])
    if tag == "__a":
        i, dtype, forma = v
        if dtype not in DTYPES:
            raise ValueError("dtype no admitido")
        dt = np.dtype(dtype)
        n = int(np.prod(forma, dtype=np.int64)) * dt.itemsize
        ini = offsets["pos"]
        if n < 0 or ini + n > len(datos):
            raise ValueError("array fuera de rango")
        offsets["pos"] = ini + n
        return np.frombuffer(datos, dtype=dt, count=n // dt.itemsize, offset=ini).reshape(forma)
    raise ValueError(f"etiqueta desconocida: {tag}")


def desempaquetar(cuerpo: bytes):
    d = zlib.decompressobj()
    plano = d.decompress(cuerpo, MAX_BYTES)
    if d.unconsumed_tail:
        raise ValueError("mensaje demasiado grande")
    if plano[:4] != MAGIA:
        raise ValueError("formato desconocido")
    (n,) = struct.unpack("<I", plano[4:8])
    estructura = json.loads(plano[8:8 + n].decode("utf-8"))
    datos = bytearray(plano[8 + n:])  # bytearray: los arrays que salen son escribibles, como los que dejaba pickle
    return _decodificar(estructura, datos, {"pos": 0})
