from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Optional


@dataclass
class FelshareState:
    device_id: str
    connected: bool = False

    # Device -> cloud visibility
    last_seen: Optional[datetime] = None
    last_seen_ts: Optional[float] = None

    # Outbound command visibility (diagnostics)
    last_publish_ts: Optional[float] = None
    last_status_request_ts: Optional[float] = None
    last_bulk_request_ts: Optional[float] = None

    # Last outbound TX (diagnostics)
    last_tx_ts: Optional[float] = None
    last_tx_key: Optional[str] = None
    last_tx_payload_hex: Optional[str] = None
    outbox_len: Optional[int] = None

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
    # Device mapping: Sun=1, Mon=2, Tue=4, Wed=8, Thu=16, Fri=32, Sat=64
    work_days_mask: Optional[int] = None
    work_flag_raw: Optional[int] = None  # raw flag byte (0..255)
    work_days: Optional[str] = None  # human-friendly ("Mon,Tue,...")

    last_topic: Optional[str] = None
    last_payload_hex: Optional[str] = None

    # Last error (best-effort, diagnostics)
    last_error: Optional[str] = None
