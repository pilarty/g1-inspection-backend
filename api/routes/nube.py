from datetime import datetime, timezone
from typing import Optional

import requests
from fastapi import APIRouter, Body, HTTPException, Request, Response
from pydantic import BaseModel

from infrastructure import nube, repositorio_datos, trayectoria

router = APIRouter(prefix="/nube")

# Solo se reenvian estos recursos de la API de AWS
RECURSOS = {
    "proyectos", "edificaciones", "robots", "usuarios", "documentos",
    "relevamientos", "hallazgos", "informes", "archivos", "resumen", "yo", "plantas", "alquileres", "licencia",
}


class LoginIn(BaseModel):
    usuario: str
    clave: str


class RelevamientoIn(BaseModel):
    relevamiento_id: int


class IniciarIn(BaseModel):
    edificacion_id: int
    robot_id: int
    fecha_programada: Optional[str] = None
    planta: Optional[str] = None  # piso que se inspecciona (ej. "PB", "Piso 1", "Subsuelo 1")
    motivo: Optional[str] = None  # rutina | seguimiento | post_evento | tasacion
    observaciones: Optional[str] = None  # condiciones del lugar al empezar


def _ahora() -> str:
    return datetime.now(timezone.utc).isoformat()


def _finalizar(rid: int) -> None:
    """Marca un relevamiento como finalizado en la nube."""
    r = nube.reenviar("PUT", f"relevamientos/{rid}",
                      cuerpo={"fecha_fin": _ahora(), "estado": "finalizado"})
    r.raise_for_status()


@router.post("/login")
def login(d: LoginIn):
    try:
        nube.iniciar_sesion(d.usuario, d.clave)
    except Exception:
        raise HTTPException(401, "no se pudo iniciar sesion")
    return {"ok": True, "usuario": nube.nombre_usuario}


@router.post("/logout")
def logout():
    nube.cerrar_sesion()
    return {"ok": True}


# Perfil de la cuenta

class DatosIn(BaseModel):
    nombre: str
    apellido: str = ""


class EmailIn(BaseModel):
    email: str


class CodigoEmailIn(BaseModel):
    email: str
    codigo: str


class UsuarioIn(BaseModel):
    usuario: str


class RestablecerIn(BaseModel):
    usuario: str
    codigo: str
    nueva: str


class EliminarCuentaIn(BaseModel):
    clave: str


def _codigo_cognito(e: Exception) -> str:
    """Código de error que devuelve Cognito (ej. NotAuthorizedException)."""
    respuesta = getattr(e, "response", None)
    return respuesta.get("Error", {}).get("Code", "") if isinstance(respuesta, dict) else type(e).__name__


def _sesion():
    if not nube.sesion_activa():
        raise HTTPException(401, "sin sesion")


@router.get("/perfil")
def ver_perfil():
    _sesion()
    return nube.perfil()


@router.put("/perfil")
def cambiar_datos(d: DatosIn):
    _sesion()
    nombre, apellido = d.nombre.strip(), d.apellido.strip()
    if not nombre:
        raise HTTPException(400, "El nombre no puede quedar vacío.")
    try:
        mostrar = nube.cambiar_datos(nombre, apellido)
    except Exception as e:
        print("[nube] no se pudo cambiar el nombre:", _codigo_cognito(e))
        raise HTTPException(400, "No se pudieron guardar los datos.")
    # También en la tabla de usuarios (si falla, la cuenta ya quedó cambiada)
    try:
        nube.reenviar("PUT", f"usuarios/{nube.usuario_id()}", cuerpo={"nombre": mostrar})
    except Exception:
        pass
    return {"ok": True, "mostrar": mostrar}


@router.post("/perfil/email")
def cambiar_email(d: EmailIn):
    """Manda un código al correo nuevo; el cambio se completa con /perfil/email/confirmar."""
    _sesion()
    email = d.email.strip().lower()
    if "@" not in email:
        raise HTTPException(400, "El correo no es válido.")
    try:
        nube.cambiar_email(email)
    except Exception as e:
        codigo = _codigo_cognito(e)
        if codigo == "AliasExistsException":
            raise HTTPException(400, "Ya hay una cuenta con ese correo.")
        if codigo == "InvalidParameterException":
            raise HTTPException(400, "El correo no es válido.")
        print("[nube] no se pudo cambiar el correo:", codigo)
        raise HTTPException(502, "No se pudo cambiar el correo.")
    return {"ok": True}


@router.post("/perfil/email/confirmar")
def confirmar_email(d: CodigoEmailIn):
    _sesion()
    try:
        uid = nube.usuario_id()  # se busca con el correo viejo, antes de cambiarlo
    except Exception:
        uid = None
    try:
        nube.confirmar_email(d.email.strip().lower(), d.codigo.strip())
    except Exception as e:
        codigo = _codigo_cognito(e)
        if codigo in ("CodeMismatchException", "ExpiredCodeException"):
            raise HTTPException(400, "El código no es correcto o ya venció.")
        print("[nube] no se pudo confirmar el correo:", codigo)
        raise HTTPException(502, "No se pudo confirmar el correo.")
    if uid is not None:
        try:
            nube.reenviar("PUT", f"usuarios/{uid}", cuerpo={"email": d.email.strip().lower()})
        except Exception:
            pass
    return {"ok": True}


def _enviar_codigo(usuario: str) -> dict:
    try:
        destino = nube.enviar_codigo_clave(usuario)
    except Exception as e:
        codigo = _codigo_cognito(e)
        if codigo == "LimitExceededException":
            raise HTTPException(429, "Demasiados intentos. Esperá unos minutos y probá de nuevo.")
        if codigo in ("UserNotFoundException", "InvalidParameterException"):
            raise HTTPException(400, "No encontramos una cuenta con ese usuario o correo.")
        print("[nube] no se pudo mandar el código:", codigo)
        raise HTTPException(502, "No se pudo mandar el correo.")
    return {"ok": True, "destino": destino}


@router.post("/perfil/clave/enviar")
def enviar_codigo_desde_perfil():
    """Desde la ventana de perfil: manda el correo para cambiar la contraseña de la cuenta actual."""
    _sesion()
    return _enviar_codigo(nube.perfil()["usuario"])


@router.post("/clave/olvide")
def olvide_clave(d: UsuarioIn):
    """Desde el inicio de sesión (sin estar adentro): manda el correo con el código."""
    return _enviar_codigo(d.usuario.strip())


@router.post("/clave/restablecer")
def restablecer_clave(d: RestablecerIn):
    try:
        nube.restablecer_clave(d.usuario.strip(), d.codigo.strip(), d.nueva)
    except Exception as e:
        codigo = _codigo_cognito(e)
        if codigo in ("CodeMismatchException", "ExpiredCodeException"):
            raise HTTPException(400, "El código no es correcto o ya venció.")
        if codigo in ("InvalidPasswordException", "InvalidParameterException"):
            raise HTTPException(400, "La contraseña nueva no cumple los requisitos: al menos 8 caracteres, con mayúsculas, minúsculas y números.")
        if codigo == "LimitExceededException":
            raise HTTPException(429, "Demasiados intentos. Esperá unos minutos y probá de nuevo.")
        print("[nube] no se pudo restablecer la contraseña:", codigo)
        raise HTTPException(502, "No se pudo cambiar la contraseña.")
    return {"ok": True}


# Registro de cuentas nuevas (sin estar adentro)

class RegistroIn(BaseModel):
    nombre: str
    apellido: str = ""
    email: str
    clave: str


class ConfirmarRegistroIn(BaseModel):
    usuario: str
    codigo: str


@router.post("/registro")
def registro(d: RegistroIn):
    nombre, email = d.nombre.strip(), d.email.strip().lower()
    if not nombre or "@" not in email:
        raise HTTPException(400, "Completá el nombre y un correo válido.")
    try:
        usuario = nube.registrar(nombre, d.apellido.strip(), email, d.clave)
    except Exception as e:
        codigo = _codigo_cognito(e)
        if codigo in ("UsernameExistsException", "AliasExistsException"):
            raise HTTPException(400, "Ya hay una cuenta con ese correo.")
        if codigo == "InvalidPasswordException":
            raise HTTPException(400, "La contraseña no cumple los requisitos: al menos 8 caracteres, con mayúsculas, minúsculas y números.")
        if codigo == "NotAuthorizedException":
            raise HTTPException(403, "El registro no está habilitado. Pedile a quien administra la app que te cree la cuenta.")
        if codigo == "InvalidParameterException":
            raise HTTPException(400, "Revisá los datos: el correo o la contraseña no son válidos.")
        print("[nube] no se pudo registrar:", codigo, e)
        raise HTTPException(502, "No se pudo crear la cuenta.")
    return {"ok": True, "usuario": usuario}


@router.post("/registro/confirmar")
def confirmar_registro(d: ConfirmarRegistroIn):
    try:
        nube.confirmar_registro(d.usuario.strip(), d.codigo.strip())
    except Exception as e:
        codigo = _codigo_cognito(e)
        if codigo in ("CodeMismatchException", "ExpiredCodeException"):
            raise HTTPException(400, "El código no es correcto o ya venció.")
        print("[nube] no se pudo confirmar el registro:", codigo)
        raise HTTPException(502, "No se pudo confirmar la cuenta.")
    return {"ok": True}


@router.post("/registro/reenviar")
def reenviar_registro(d: UsuarioIn):
    try:
        nube.reenviar_codigo_registro(d.usuario.strip())
    except Exception as e:
        codigo = _codigo_cognito(e)
        if codigo == "LimitExceededException":
            raise HTTPException(429, "Demasiados intentos. Esperá unos minutos y probá de nuevo.")
        raise HTTPException(502, "No se pudo reenviar el código.")
    return {"ok": True}


@router.post("/perfil/eliminar")
def eliminar_cuenta(d: EliminarCuentaIn):
    """Borra la cuenta de acceso. Pide la contraseña otra vez para confirmar."""
    if not nube.sesion_activa():
        raise HTTPException(401, "sin sesion")
    if nube.relevamiento_actual is not None:
        raise HTTPException(409, "Hay una inspección en curso. Detenela antes de eliminar la cuenta.")
    try:
        nube.verificar_clave(d.clave)
    except Exception:
        raise HTTPException(400, "La contraseña no es correcta.")
    try:
        nube.eliminar_cuenta()
    except Exception as e:
        print("[nube] no se pudo eliminar la cuenta:", _codigo_cognito(e))
        raise HTTPException(502, "No se pudo eliminar la cuenta.")
    return {"ok": True}


@router.post("/relevamiento")
def elegir_relevamiento(d: RelevamientoIn):
    nube.relevamiento_actual = d.relevamiento_id
    return {"ok": True}


@router.post("/relevamientos/iniciar")
def iniciar_relevamiento(d: IniciarIn):
    """Crea el relevamiento en la nube; desde aqui cada deteccion se envia a el."""
    if not nube.sesion_activa():
        raise HTTPException(401, "sin sesion")
    try:
        anterior = nube.relevamiento_actual
        if anterior is not None:
            nube.relevamiento_actual = None
            try:
                _finalizar(anterior)
            except requests.RequestException:
                pass  # no impide empezar uno nuevo
        cuerpo = {
            "edificacion_id": d.edificacion_id,
            # (el operador lo define la API de AWS a partir del token)
            "robot_id": d.robot_id,
            "fecha_inicio": _ahora(),
            "estado": "en_curso",
        }
        if d.fecha_programada:
            cuerpo["fecha_programada"] = d.fecha_programada
        r = nube.reenviar("POST", "relevamientos", cuerpo=cuerpo)
        r.raise_for_status()
    except (requests.RequestException, RuntimeError):
        raise HTTPException(502, "no se pudo crear el relevamiento en la nube")
    relevamiento = r.json()
    nube.relevamiento_actual = relevamiento["id"]
    if d.planta:
        try:
            nube.reenviar("PUT", f"relevamientos/{relevamiento['id']}/planta",
                          cuerpo={"planta": d.planta, "motivo": d.motivo, "observaciones": d.observaciones}).raise_for_status()
        except requests.RequestException:
            print("[nube] no se pudo guardar la planta de la inspección")
    # Si el simulador ya mandó el plano antes de empezar, se guarda con esta inspección
    trayectoria.subir_plano(relevamiento["id"], repositorio_datos.obtener_room_layout())
    return relevamiento


@router.post("/relevamientos/detener")
def detener_relevamiento():
    """Deja de enviar detecciones y marca el relevamiento como finalizado."""
    trayectoria.enviar_pendientes()  # que no se pierdan los últimos puntos del camino
    rid = nube.relevamiento_actual
    nube.relevamiento_actual = None
    if rid is not None and nube.sesion_activa():
        try:
            _finalizar(rid)
        except requests.RequestException:
            raise HTTPException(502, "no se pudo cerrar el relevamiento en la nube")
    return {"ok": True}


@router.get("/estado")
def estado():
    return {
        "sesion": nube.sesion_activa(),
        "relevamiento_id": nube.relevamiento_actual,
        "usuario": nube.nombre_usuario,
    }


@router.api_route("/api/{ruta:path}", methods=["GET", "POST", "PUT", "DELETE"])
def reenviar(ruta: str, request: Request, cuerpo: Optional[dict] = Body(default=None)):
    if not nube.sesion_activa():
        raise HTTPException(401, "sin sesion")
    if ruta.split("/")[0] not in RECURSOS:
        raise HTTPException(404, "recurso desconocido")
    if "credenciales" in ruta.split("/"):
        # las contraseñas de los robots solo las lee este backend al reconectar, nunca la interfaz
        raise HTTPException(403, "no permitido")
    try:
        r = nube.reenviar(request.method, ruta, dict(request.query_params), cuerpo)
    except requests.RequestException:
        raise HTTPException(502, "no se pudo conectar con la nube")
    return Response(
        content=r.content,
        status_code=r.status_code,
        media_type=r.headers.get("content-type", "application/json"),
    )
