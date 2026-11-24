"""Device layer: a simulator and a minimal async Modbus TCP client.

No homeassistant imports here on purpose: this file can be lifted into a
standalone PyPI library later (architecture principle 3).
"""
from __future__ import annotations

import asyncio
import contextlib
import logging
import math
import struct
import time
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any, Protocol

from .const import (
    CONF_HOST, CONF_PORT, CONF_SIMULATOR, CONF_UNIT_ID,
    DEFAULT_PORT, DEFAULT_UNIT_ID, MODEL,
)

_LOGGER = logging.getLogger(__name__)

# --- Errors -----------------------------------------------------------------
class InverterError(Exception):
    """Base class for everything the device layer reports."""


class InverterConnectionError(InverterError):
    """The inverter is unreachable or did not answer in time."""


class InverterAuthError(InverterError):
    """Credentials were rejected. The local Modbus example never raises this,
    but a cloud API client does, and the coordinator already maps it to reauth."""


class InverterWriteError(InverterError):
    """A write was rejected or not echoed back by the device."""


# --- Data model -------------------------------------------------------------
@dataclass(slots=True)
class DeviceIdentity:
    serial: str
    model: str
    sw_version: str


@dataclass(slots=True)
class InverterData:
    """One polling snapshot. Every entity reads from this, nobody polls alone."""

    pv_power: float | None = None
    grid_power: float | None = None
    load_power: float | None = None
    battery_power: float | None = None
    battery_soc: float | None = None
    temperature: float | None = None
    work_mode: int | None = None
    power_limit: int | None = None
    energy_today: float | None = None
    energy_total: float | None = None


class InverterClient(Protocol):
    """The contract both implementations must satisfy."""

    async def async_identify(self) -> DeviceIdentity: ...
    async def async_read(self) -> InverterData: ...
    async def async_write_power_limit(self, percent: int) -> None: ...
    async def async_close(self) -> None: ...


# --- Helpers ----------------------------------------------------------------
def _s16(value: int) -> float:
    """Two's complement register -> signed number."""
    return float(value - 0x10000 if value & 0x8000 else value)


def _u32(high: int, low: int) -> float:
    """High-word-first 32-bit value (confirmed by the device firmware table)."""
    return float((high << 16) | low)


# --- Implementation A: simulator (no hardware needed) ----------------------
class SimulatedInverter:
    """Produces plausible values so the whole integration can be built offline."""

    def __init__(self, serial: str = "SIM-0001") -> None:
        self._serial = serial
        self._limit = 100
        self._total = 1234.5

    async def async_identify(self) -> DeviceIdentity:
        await asyncio.sleep(0.05)
        return DeviceIdentity(self._serial, f"{MODEL} (sim)", "1.0.0")

    async def async_read(self) -> InverterData:
        await asyncio.sleep(0.05)  # pretend this is network latency
        now = time.time()
        solar = max(0.0, 2600 * math.sin(now / 300) + 1400)
        self._total += 0.02
        return InverterData(
            pv_power=round(solar, 1),
            grid_power=round(600 - solar * 0.35, 1),
            load_power=round(700 + 200 * math.sin(now / 90), 1),
            battery_power=round(solar * 0.25 - 400, 1),
            battery_soc=round(55 + 20 * math.sin(now / 1800), 1),
            temperature=round(32 + 4 * math.sin(now / 600), 1),
            work_mode=1,
            power_limit=self._limit,
            energy_today=round(8.0 + (now % 86400) / 3600 * 0.6, 2),
            energy_total=round(self._total, 2),
        )

    async def async_write_power_limit(self, percent: int) -> None:
        if not 0 <= percent <= 100:
            raise InverterWriteError("power limit must be between 0 and 100")
        await asyncio.sleep(0.05)
        self._limit = percent

    async def async_close(self) -> None:
        return None


# --- Implementation B: real Modbus TCP -------------------------------------
# ★ REGISTER MAP from the device firmware table abRegMap_ht0_high_ESS[]
#   (HT0 high-voltage ESS, 3-phase hybrid inverter).
#   - Power block: signed 16-bit raw values in 0.1 kW  ->  W = raw * 100
#   - Energy block: unsigned 32-bit, 2 registers, HIGH word first, in 0.1 kWh
#   - The registers are NOT contiguous, so one poll issues several FC03 reads.
REG_WORK_MODE = 0x1100        # "work_mode", U16, raw enum
REG_FAULT_CODE = 0x110A       # "fault_code", U16 (kept for future diagnostics)

REG_HOME_LOAD_A = 0x1120      # "home_load_a_power", I16, 0.1 kW
REG_HOME_LOAD_B = 0x1121
REG_HOME_LOAD_C = 0x1122

REG_PV1_POWER = 0x1128        # "pv1_power" .. "pv4_power", I16, 0.1 kW
REG_PV2_POWER = 0x1129
REG_PV3_POWER = 0x112A
REG_PV4_POWER = 0x112B

REG_BAT1_POWER = 0x1131       # "bat1_power", I16, 0.1 kW
REG_BAT2_POWER = 0x1133       # "bat2_power" (0x1132 is unmapped -> read singly)

REG_BAT1_SOC = 0x1138         # "bat1_soc", U16, %
# NOTE: the table lists "bat2_soc" at 0x1138 as well (likely a copy/paste bug).
#       Only bat1 is polled until the real bat2 address is confirmed.

REG_GRID_A = 0x1173           # "grid_a_power" .. "grid_c_power", I16, 0.1 kW
REG_GRID_B = 0x1174
REG_GRID_C = 0x1175

REG_PV_TOTAL_ENERGY = 0x11C5  # "pv_total_gen_energy", U32 high word first, 0.1 kWh
REG_POWER_SETPOINT = 0x220E   # "eco1_power_set", U16 (ECO rule 1 discharge power)

POWER_SCALE_W = 100.0         # 0.1 kW -> W
ENERGY_SCALE_KWH = 0.1        # 0.1 kWh -> kWh

_MODBUS_ERRORS = {
    1: "illegal function",
    2: "illegal data address",
    3: "illegal data value",
    4: "device failure",
    5: "acknowledge",
    6: "device busy",
    7: "negative acknowledge",
    8: "memory parity error",
    10: "gateway path unavailable",
    11: "gateway target failed to respond",
}


class ModbusTcpInverter:
    """FC03 / FC06 client over one persistent asyncio stream.

    Frame: MBAP header [tid, protocol=0, length, unit] + PDU [fc, ...].
    `length` counts the unit byte plus the PDU, hence `length - 1` bytes of PDU.
    A poll touches several scattered registers, so the socket is kept open
    between requests and reconnected lazily if the peer drops it.
    """

    def __init__(
        self, host: str, port: int, unit_id: int, timeout: float = 5.0
    ) -> None:
        self._host = host
        self._port = port
        self._unit_id = unit_id
        self._timeout = timeout
        self._transaction_id = 0
        self._reader: asyncio.StreamReader | None = None
        self._writer: asyncio.StreamWriter | None = None
        self._lock = asyncio.Lock()

    async def _ensure_connection(self) -> asyncio.StreamWriter:
        if self._writer is not None and not self._writer.is_closing():
            return self._writer
        try:
            self._reader, self._writer = await asyncio.wait_for(
                asyncio.open_connection(self._host, self._port), self._timeout
            )
        except (OSError, TimeoutError) as err:
            self._reader = self._writer = None
            raise InverterConnectionError(
                f"cannot connect to {self._host}:{self._port}"
            ) from err
        return self._writer

    async def _drop_connection(self) -> None:
        writer, self._writer = self._writer, None
        self._reader = None
        if writer is not None:
            writer.close()
            with contextlib.suppress(OSError):
                await writer.wait_closed()

    async def _exchange(self, pdu: bytes) -> bytes:
        writer = await self._ensure_connection()
        reader = self._reader
        assert reader is not None

        self._transaction_id = (self._transaction_id + 1) % 0xFFFF
        tid = self._transaction_id
        frame = struct.pack(">HHHB", tid, 0, len(pdu) + 1, self._unit_id) + pdu

        try:
            writer.write(frame)
            await asyncio.wait_for(writer.drain(), self._timeout)
            header = await asyncio.wait_for(reader.readexactly(7), self._timeout)
            r_tid, r_proto, length, r_unit = struct.unpack(">HHHB", header)
            if length < 2:
                raise InverterConnectionError("invalid Modbus length")
            body = await asyncio.wait_for(
                reader.readexactly(length - 1), self._timeout
            )
        except (OSError, asyncio.IncompleteReadError, TimeoutError) as err:
            raise InverterConnectionError(f"inverter did not answer: {err}") from err

        if r_tid != tid or r_proto != 0 or r_unit != self._unit_id:
            raise InverterConnectionError("mismatched Modbus response")
        if not body:
            raise InverterConnectionError("empty Modbus response")
        if body[0] & 0x80:                       # Modbus exception frame
            code = body[1]
            detail = _MODBUS_ERRORS.get(code, "unknown")
            raise InverterError(f"Modbus exception {code} ({detail})")
        return body

    async def _request(self, pdu: bytes) -> bytes:
        async with self._lock:
            try:
                return await self._exchange(pdu)
            except InverterConnectionError:
                # Stale socket (inverter dropped an idle connection): retry once.
                await self._drop_connection()
                try:
                    return await self._exchange(pdu)
                except InverterConnectionError:
                    await self._drop_connection()
                    raise

    async def _read_registers(self, address: int, count: int) -> list[int]:
        try:
            body = await self._request(struct.pack(">BHH", 0x03, address, count))
        except InverterError as err:
            raise InverterError(f"FC03 @0x{address:04X} x{count}: {err}") from err
        if len(body) < 2 + 2 * count or body[0] != 0x03 or body[1] != 2 * count:
            raise InverterError("unexpected FC03 response")
        return list(struct.unpack(f">{count}H", body[2 : 2 + 2 * count]))

    async def _write_register(self, address: int, value: int) -> None:
        try:
            body = await self._request(struct.pack(">BHH", 0x06, address, value))
        except InverterError as err:
            raise InverterWriteError(
                f"FC06 @0x{address:04X} = {value}: {err}"
            ) from err
        echo = struct.pack(">HH", address, value)
        if len(body) != 5 or body[0] != 0x06 or body[1:5] != echo:
            raise InverterWriteError("inverter did not echo the write")

    async def async_identify(self) -> DeviceIdentity:
        # This firmware map has no serial-number register, so the TCP endpoint
        # is the stable identifier. Swap in a serial register if you have one.
        return DeviceIdentity(
            serial=f"{self._host}:{self._port}",
            model=MODEL,
            sw_version="unknown",
        )

    async def async_read(self) -> InverterData:
        work_mode = (await self._read_registers(REG_WORK_MODE, 1))[0]
        home_load = await self._read_registers(REG_HOME_LOAD_A, 3)
        pv = await self._read_registers(REG_PV1_POWER, 4)
        bat1 = (await self._read_registers(REG_BAT1_POWER, 1))[0]
        bat2 = (await self._read_registers(REG_BAT2_POWER, 1))[0]
        soc = (await self._read_registers(REG_BAT1_SOC, 1))[0]
        grid = await self._read_registers(REG_GRID_A, 3)
        pv_total = await self._read_registers(REG_PV_TOTAL_ENERGY, 2)
        try:
            power_limit = int(
                (await self._read_registers(REG_POWER_SETPOINT, 1))[0]
            )
        except InverterError as err:
            _LOGGER.debug("cannot read power setpoint: %s", err)
            power_limit = None

        return InverterData(
            pv_power=sum(_s16(v) for v in pv) * POWER_SCALE_W,
            grid_power=sum(_s16(v) for v in grid) * POWER_SCALE_W,
            load_power=sum(_s16(v) for v in home_load) * POWER_SCALE_W,
            battery_power=(_s16(bat1) + _s16(bat2)) * POWER_SCALE_W,
            battery_soc=float(soc),
            temperature=None,       # not present in this firmware map
            work_mode=work_mode,
            power_limit=power_limit,
            energy_today=None,      # only lifetime counters are exposed
            energy_total=_u32(pv_total[0], pv_total[1]) * ENERGY_SCALE_KWH,
        )

    async def async_write_power_limit(self, percent: int) -> None:
        """Write "eco1_power_set" (0x220E). The firmware table does not
        document the unit; treated as a percent here — verify before use."""
        if not 0 <= percent <= 100:
            raise InverterWriteError("power limit must be between 0 and 100")
        await self._write_register(REG_POWER_SETPOINT, percent)

    async def async_close(self) -> None:
        async with self._lock:
            await self._drop_connection()


# --- Factory: the only place that knows about config keys -------------------
def create_client(config: Mapping[str, Any]) -> InverterClient:
    if config.get(CONF_SIMULATOR):
        return SimulatedInverter()
    return ModbusTcpInverter(
        host=config[CONF_HOST],
        port=int(config.get(CONF_PORT, DEFAULT_PORT)),
        unit_id=int(config.get(CONF_UNIT_ID, DEFAULT_UNIT_ID)),
    )