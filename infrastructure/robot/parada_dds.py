"""Parada de emergencia: pone el G1 en modo amortiguado (LocoClient.Damp del SDK).

Es lo mismo que L2 + B en el mando: los motores dejan de empujar y solo frenan,
y el robot se afloja despacio. Es la unica orden que la app envia sin pedir
confirmacion, porque sirve para detenerlo.

Corre en un proceso aparte (python -m infrastructure.robot.parada_dds ...), igual
que sonda_dds, porque la interfaz de Cyclone DDS se fija al crear el dominio.

Imprime una linea JSON: {"ok": bool, "confirmada": bool, "detalle": str, "ms": int}
"""
import argparse
import json
import os
import sys
import time

from infrastructure.robot.sonda_dds import configurar_interfaz


def amortiguar(dominio, timeout):
    from cyclonedds.domain import DomainParticipant
    from cyclonedds.pub import DataWriter
    from cyclonedds.sub import DataReader
    from cyclonedds.topic import Topic

    from infrastructure.robot.tipos_dds import (
        API_LOCO_SET_FSM_ID, FSM_AMORTIGUADO, TOPICO_SPORT_PETICION, TOPICO_SPORT_RESPUESTA,
        Request_, RequestHeader_, RequestIdentity_, RequestLease_, RequestPolicy_, Response_,
    )

    dp = DomainParticipant(dominio)
    respuestas = DataReader(dp, Topic(dp, TOPICO_SPORT_RESPUESTA, Response_))
    peticiones = DataWriter(dp, Topic(dp, TOPICO_SPORT_PETICION, Request_))
    time.sleep(0.5)  # tiempo para que DDS descubra al robot (el SDK espera lo mismo)

    id_peticion = time.monotonic_ns()
    peticion = Request_(
        header=RequestHeader_(
            identity=RequestIdentity_(id=id_peticion, api_id=API_LOCO_SET_FSM_ID),
            lease=RequestLease_(id=0),
            policy=RequestPolicy_(priority=0, noreply=False),
        ),
        parameter=json.dumps({"data": FSM_AMORTIGUADO}),
        binary=[],
    )
    inicio = time.monotonic()
    peticiones.write(peticion)
    while time.monotonic() - inicio < timeout:
        for r in respuestas.take(N=10):
            if r.header.identity.id == id_peticion:
                codigo = r.header.status.code
                if codigo == 0:
                    return True, True, "El robot confirmó el modo amortiguado.", inicio
                return False, True, f"El robot rechazó la orden de amortiguar (código {codigo}).", inicio
        time.sleep(0.02)
    return True, False, "Orden de amortiguar enviada, pero el robot no la confirmó.", inicio


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--dominio", type=int, required=True)
    p.add_argument("--interfaz", default="")
    p.add_argument("--timeout", type=float, default=2.0)
    a = p.parse_args()

    configurar_interfaz(a.interfaz)
    inicio = time.monotonic()
    try:
        ok, confirmada, detalle, inicio = amortiguar(a.dominio, a.timeout)
    except Exception as e:
        ok, confirmada, detalle = False, False, f"Error de DDS: {e}"
    print(json.dumps({"ok": ok, "confirmada": confirmada, "detalle": detalle,
                      "ms": int((time.monotonic() - inicio) * 1000)}), flush=True)
    sys.stdout.flush()
    os._exit(0)


if __name__ == "__main__":
    main()
