from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Optional


@dataclass
class FelshareState:
    device_id: str
    connected: bool = False
    last_seen: Optional[datetime] = None

    power_on: Optional[bool] = None
    fan_on: Optional[bool] = None

    oil_name: Optional[str] = None
    consumption: Optional[float] = None  # ml/h
    capacity: Optional[int] = None  # ml
    remain_oil: Optional[int] = None  # ml
    liquid_level: Optional[int] = None  # %

    # Work schedule ("WorkTime" / 0x32 0x01)
    work_start: Optional[str] = None  # "HH:MM"
    work_end: Optional[str] = None  # "HH:MM"
    work_run_s: Optional[int] = None
    work_stop_s: Optional[int] = None
    work_enabled: Optional[bool] = None
    work_days_mask: Optional[int] = None  # bitmask (Mon=1, Tue=2, Wed=4, Thu=8, Fri=16, Sat=32, Sun=64)
    work_flag_raw: Optional[int] = None  # raw flag byte (0..255)
    work_days: Optional[str] = None  # human-friendly ("Mon,Tue,...")

    last_topic: Optional[str] = None
    last_payload_hex: Optional[str] = None
