from __future__ import annotations

import json
import re
import socket
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

MPDU_RE = re.compile(r"^\[MPDU\s+(?P<time>\d{2}:\d{2}:\d{2})\s+(?P<direction>AIR|GND)(?:\s+(?P<air_id>[A-Z0-9\-]+))?\s+SLOT\s+(?P<slot>[\d,]+)\s+(?P<bps>\d+)\s+BPS\s*\]", re.M)
GS_RE = re.compile(r"Ground station ID\s+(?P<gs>.+?)\s+(?:NOT\s+)?SYNCHED", re.I)
ICAO_RE = re.compile(r"\bICAO\s+(?P<icao>[0-9A-F]{6})\b", re.I)
FLIGHT_RE = re.compile(r"\bFlight ID\s*=\s*(?P<flight>[A-Z0-9\-]+)", re.I)
POS_RE = re.compile(r"LAT\s+(\d{1,2})\s+(\d{1,2})\s+(\d{1,2})\s+([NS])\s+LON\s+(\d{1,3})\s+(\d{1,2})\s+(\d{1,2})\s+([EW])", re.I)
FREQ_RE = re.compile(r"^\s*Frequency\s+(?P<freq>\d+(?:\.\d+)?)\(KHz\)", re.I | re.M)
HFNPDU_RE = re.compile(r"\[HFNPDU\s+(?P<kind>[^\]]+)\]", re.I)
LPDU_RE = re.compile(r"\[LPDU\s+(?P<kind>[^\]]+)\]", re.I)
PREAMBLE_RE = re.compile(r"\[Preamble\s+TS\((?P<ts>\d+)\)\s+(?P<bps>\d+)\s+bps.*?FREQ ERR\s+(?P<err>-?\d+(?:\.\d+)?)\s+Hz\s+Mag\s+(?P<mag>\d+)\s+Votes\s+(?P<votes>\d+)", re.I)
HF_TIME_RE = re.compile(r"(?P<time>\d{2}:\d{2}:\d{2})\s+UTC\s+Flight ID", re.I)


def dms(d: str, m: str, s: str, hemi: str) -> float:
    value = float(d) + float(m) / 60 + float(s) / 3600
    return round(-value if hemi.upper() in ("S", "W") else value, 6)


def message_type(block: str) -> str:
    m = HFNPDU_RE.search(block)
    if m:
        return m.group("kind").strip().upper()
    m = LPDU_RE.search(block)
    if m:
        return m.group("kind").strip().upper()
    return "MPDU / CRC" if "[CRC FAIL]" in block else "MPDU"


def parse_block(block: str, source_file: Path | None = None) -> dict | None:
    m = MPDU_RE.search(block)
    if not m:
        return None

    direction = "air_to_ground" if m.group("direction").upper() == "AIR" else "ground_to_air"
    gs_m = GS_RE.search(block)
    gs = gs_m.group("gs").strip() if gs_m else None
    icao_m = ICAO_RE.search(block)
    icao = icao_m.group("icao").upper() if icao_m else None
    flight_m = FLIGHT_RE.search(block)
    callsign = flight_m.group("flight").upper() if flight_m else None
    pos_m = POS_RE.search(block)
    lat = lon = None
    if pos_m:
        lat = dms(pos_m.group(1), pos_m.group(2), pos_m.group(3), pos_m.group(4))
        lon = dms(pos_m.group(5), pos_m.group(6), pos_m.group(7), pos_m.group(8))
    freq_m = FREQ_RE.search(block)
    freq = float(freq_m.group("freq")) if freq_m else None
    hf_time = HF_TIME_RE.search(block)
    air_id = m.group("air_id")

    air = {"type": "aircraft_station", "id": air_id or icao or callsign or "unknown"}
    ground = {"type": "ground_station", "id": gs or "unknown"}
    src, dst = (air, ground) if direction == "air_to_ground" else (ground, air)

    record = {
        "source_protocol": "pc-hfdl-log",
        "decoder": "PC-HFDL",
        "timestamp": hf_time.group("time") if hf_time else m.group("time"),
        "received_at": datetime.now(timezone.utc).isoformat(),
        "direction": direction,
        "message_type": message_type(block),
        "ground_station": gs,
        "icao": icao,
        "callsign": callsign,
        "latitude": lat,
        "longitude": lon,
        "frequency_khz": freq,
        "assigned_aircraft_id": air_id,
        "assigned_ac_id": air_id,
        "slot": m.group("slot"),
        "bitrate": int(m.group("bps")),
        "crc_fail_count": block.count("[CRC FAIL]"),
        "source_file": str(source_file) if source_file else None,
        "raw_text": block.strip(),
        "hfdl": {"lpdu": {"src": src, "dst": dst, "assigned_ac_id": air_id}},
    }
    pre = PREAMBLE_RE.search(block)
    if pre:
        record["freq_error"] = float(pre.group("err"))
        record["decoder_metrics"] = {
            "pc_hfdl_magnitude": int(pre.group("mag")),
            "pc_hfdl_votes": int(pre.group("votes")),
            "pc_hfdl_frequency_error_hz": float(pre.group("err")),
        }
    return {k: v for k, v in record.items() if v is not None}


def parse_file(path: Path) -> list[dict]:
    text = path.read_text(encoding="utf-8", errors="replace")
    matches = list(MPDU_RE.finditer(text))
    out = []
    for i, match in enumerate(matches):
        end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
        record = parse_block(text[match.start():end], path)
        if record:
            out.append(record)
    return out


def split_complete(text: str) -> tuple[list[str], str]:
    matches = list(MPDU_RE.finditer(text))
    if not matches:
        return [], text[-8192:]
    blocks = [text[matches[i].start():matches[i + 1].start()] for i in range(len(matches) - 1)]
    return blocks, text[matches[-1].start():]


@dataclass
class TailState:
    offset: int = 0
    buffer: str = ""
    last_growth: float = field(default_factory=time.monotonic)


class PCHFDLWatcher:
    def __init__(self, paths: list[Path], udp_host: str, udp_port: int, pattern: str = "*.txt", start_at_end: bool = True):
        self.paths = paths
        self.udp_host = udp_host
        self.udp_port = udp_port
        self.pattern = pattern
        self.start_at_end = start_at_end
        self.states: dict[Path, TailState] = {}
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.on_send = None

    def discover(self) -> list[Path]:
        files = []
        for path in self.paths:
            if path.is_file():
                files.append(path)
            elif path.is_dir():
                files.extend(path.glob(self.pattern))
        return sorted(set(p.resolve() for p in files if p.exists()))

    def state_for(self, path: Path) -> TailState:
        state = self.states.get(path)
        if state is None:
            state = TailState(offset=path.stat().st_size if self.start_at_end else 0)
            self.states[path] = state
        return state

    def send(self, record: dict) -> None:
        payload = json.dumps(record, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
        if len(payload) > 65507:
            record = dict(record)
            record["raw_text"] = record.get("raw_text", "")[:30000] + "\n[TRUNCATED]"
            payload = json.dumps(record, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
        self.sock.sendto(payload, (self.udp_host, self.udp_port))
        if self.on_send:
            self.on_send(record)

    def poll_file(self, path: Path) -> int:
        state = self.state_for(path)
        size = path.stat().st_size
        if size < state.offset:
            state.offset = 0
            state.buffer = ""
        sent = 0
        if size > state.offset:
            with path.open("rb") as handle:
                handle.seek(state.offset)
                data = handle.read()
            state.offset = size
            state.last_growth = time.monotonic()
            state.buffer += data.decode("utf-8", errors="replace")
            blocks, state.buffer = split_complete(state.buffer)
            for block in blocks:
                record = parse_block(block, path)
                if record:
                    self.send(record)
                    sent += 1
        if state.buffer and MPDU_RE.search(state.buffer) and time.monotonic() - state.last_growth >= 2.0:
            record = parse_block(state.buffer, path)
            if record:
                self.send(record)
                sent += 1
            state.buffer = ""
        return sent

    def close(self) -> None:
        self.sock.close()
