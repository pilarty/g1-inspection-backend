"""Tipos DDS del G1 que usa la app: el estado (unitree_hg) y las peticiones (unitree_api).

Son copia exacta de unitree_sdk2_python (unitree_sdk2py/idl/unitree_hg/msg/dds_ y
unitree_sdk2py/idl/unitree_api/msg/dds_), BSD 3-Clause,
Copyright (c) 2016-2024 HangZhou YuShu TECHNOLOGY CO.,LTD. ("Unitree Robotics").
Deben coincidir campo por campo con los del robot: si no, DDS no los empareja.
"""
from dataclasses import dataclass

import cyclonedds.idl as idl
import cyclonedds.idl.annotations as annotate
import cyclonedds.idl.types as types


# ─── Unitree G1 (unitree_hg) ──────────────────────────────────────────────────

@dataclass
@annotate.final
@annotate.autoid("sequential")
class IMUState_(idl.IdlStruct, typename="unitree_hg.msg.dds_.IMUState_"):
    quaternion: types.array[types.float32, 4]
    gyroscope: types.array[types.float32, 3]
    accelerometer: types.array[types.float32, 3]
    rpy: types.array[types.float32, 3]
    temperature: types.int16


@dataclass
@annotate.final
@annotate.autoid("sequential")
class MotorState_(idl.IdlStruct, typename="unitree_hg.msg.dds_.MotorState_"):
    mode: types.uint8
    q: types.float32
    dq: types.float32
    ddq: types.float32
    tau_est: types.float32
    temperature: types.array[types.int16, 2]
    vol: types.float32
    sensor: types.array[types.uint32, 2]
    motorstate: types.uint32
    reserve: types.array[types.uint32, 4]


@dataclass
@annotate.final
@annotate.autoid("sequential")
class LowState_(idl.IdlStruct, typename="unitree_hg.msg.dds_.LowState_"):
    version: types.array[types.uint32, 2]
    mode_pr: types.uint8
    mode_machine: types.uint8
    tick: types.uint32
    imu_state: IMUState_
    motor_state: types.array[MotorState_, 35]
    wireless_remote: types.array[types.uint8, 40]
    reserve: types.array[types.uint32, 4]
    crc: types.uint32


# ─── Peticiones a servicios del robot (unitree_api) ──────────────────────────

@dataclass
@annotate.final
@annotate.autoid("sequential")
class RequestIdentity_(idl.IdlStruct, typename="unitree_api.msg.dds_.RequestIdentity_"):
    id: types.int64
    api_id: types.int64


@dataclass
@annotate.final
@annotate.autoid("sequential")
class RequestLease_(idl.IdlStruct, typename="unitree_api.msg.dds_.RequestLease_"):
    id: types.int64


@dataclass
@annotate.final
@annotate.autoid("sequential")
class RequestPolicy_(idl.IdlStruct, typename="unitree_api.msg.dds_.RequestPolicy_"):
    priority: types.int32
    noreply: bool


@dataclass
@annotate.final
@annotate.autoid("sequential")
class RequestHeader_(idl.IdlStruct, typename="unitree_api.msg.dds_.RequestHeader_"):
    identity: RequestIdentity_
    lease: RequestLease_
    policy: RequestPolicy_


@dataclass
@annotate.final
@annotate.autoid("sequential")
class Request_(idl.IdlStruct, typename="unitree_api.msg.dds_.Request_"):
    header: RequestHeader_
    parameter: str
    binary: types.sequence[types.uint8]


@dataclass
@annotate.final
@annotate.autoid("sequential")
class ResponseStatus_(idl.IdlStruct, typename="unitree_api.msg.dds_.ResponseStatus_"):
    code: types.int32


@dataclass
@annotate.final
@annotate.autoid("sequential")
class ResponseHeader_(idl.IdlStruct, typename="unitree_api.msg.dds_.ResponseHeader_"):
    identity: RequestIdentity_
    status: ResponseStatus_


@dataclass
@annotate.final
@annotate.autoid("sequential")
class Response_(idl.IdlStruct, typename="unitree_api.msg.dds_.Response_"):
    header: ResponseHeader_
    data: str
    binary: types.sequence[types.uint8]


TOPICO_ESTADO = "rt/lowstate"
# Servicio de locomocion del G1 ("sport"): mismo nombre de canal que usa el SDK
TOPICO_SPORT_PETICION = "rt/api/sport/request"
TOPICO_SPORT_RESPUESTA = "rt/api/sport/response"
API_LOCO_SET_FSM_ID = 7101
FSM_AMORTIGUADO = 1  # LocoClient.Damp(): lo mismo que L2 + B en el mando

