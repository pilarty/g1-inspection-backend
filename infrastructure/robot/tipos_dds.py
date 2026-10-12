"""Tipos DDS que la app escucha durante la prueba de conexion.

Los tipos unitree_hg son copia exacta de unitree_sdk2_python
(unitree_sdk2py/idl/unitree_hg/msg/dds_), BSD 3-Clause,
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


TOPICO_ESTADO = "rt/lowstate"

