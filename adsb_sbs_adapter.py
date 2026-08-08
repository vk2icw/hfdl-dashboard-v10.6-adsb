from __future__ import annotations

import json
import socket
import threading
from datetime import datetime, timezone


def _text(parts: list[str], index: int) -> str | None:
    if index >= len(parts):
        return None
    value = parts[index].strip()
    return value or None


def _int(parts: list[str], index: int) -> int | None:
    value = _text(parts, index)
    if value is None:
        return None
    try:
        return int(float(value))
    except ValueError:
        return None


def _float(parts: list[str], index: int) -> float | None:
    value = _text(parts, index)
    if value is None:
        return None
    try:
        return float(value)
    except ValueError:
        return None


def _bool(parts: list[str], index: int) -> bool | None:
    value = _text(parts, index)
    if value is None:
        return None
    if value in ("1", "true", "True"):
        return True
    if value in ("0", "false", "False"):
        return False
    return None


def _local_timezone():
    """Return the timezone currently configured on the Windows decoder PC."""
    return datetime.now().astimezone().tzinfo


def _sbs_datetime(date_value: str | None, time_value: str | None) -> tuple[str | None, str | None]:
    """Parse an SBS/BaseStation timestamp as decoder-PC local time.

    SBS MSG timestamps contain no timezone designator. SDRuno and the dashboard run
    on the same Windows PC in our supported configuration, so the only defensible
    interpretation for live timing is the Windows local timezone. The original
    timezone-less value is retained separately for diagnostics, while comparisons
    use an explicit UTC ISO timestamp.
    """
    if not date_value or not time_value:
        return None, None

    raw = f"{date_value} {time_value}"
    for fmt in ("%Y/%m/%d %H:%M:%S.%f", "%Y/%m/%d %H:%M:%S"):
        try:
            naive = datetime.strptime(raw, fmt)
            local_dt = naive.replace(tzinfo=_local_timezone())
            utc_dt = local_dt.astimezone(timezone.utc)
            return (
                utc_dt.isoformat(timespec="milliseconds"),
                local_dt.isoformat(timespec="milliseconds"),
            )
        except ValueError:
            pass

    # Unknown timestamp format: preserve the source text, but do not pretend it is
    # timezone-normalised. This prevents invalid stale-message calculations.
    return None, raw


def parse_sbs_line(line: str) -> dict | None:
    """Parse one SBS/BaseStation MSG record.

    Field positions follow the common 22-column SBS/BaseStation MSG layout.
    Missing values are preserved as missing rather than guessed.
    """
    raw = line.strip()
    if not raw:
        return None
    parts = raw.split(",")
    if len(parts) < 10 or parts[0].upper() != "MSG":
        return None

    transmission_type = _int(parts, 1)
    icao = (_text(parts, 4) or "").upper() or None
    callsign = (_text(parts, 10) or "").upper() or None

    generated_utc, generated_local = _sbs_datetime(_text(parts, 6), _text(parts, 7))
    logged_utc, logged_local = _sbs_datetime(_text(parts, 8), _text(parts, 9))
    received_utc = datetime.now(timezone.utc).isoformat(timespec="milliseconds")

    record = {
        "source_protocol": "adsb-sbs",
        "decoder": "SDRuno ADS-B Plugin",
        "message_type": f"ADSB SBS MSG {transmission_type}" if transmission_type is not None else "ADSB SBS MSG",
        "sbs_transmission_type": transmission_type,
        "icao": icao,
        "callsign": callsign,
        "altitude_ft": _int(parts, 11),
        "altitude": _int(parts, 11),
        "ground_speed_knots": _float(parts, 12),
        "speed": _float(parts, 12),
        "track_deg": _float(parts, 13),
        "heading": _float(parts, 13),
        "latitude": _float(parts, 14),
        "longitude": _float(parts, 15),
        "vertical_rate_fpm": _int(parts, 16),
        "squawk": _text(parts, 17),
        "alert": _bool(parts, 18),
        "emergency": _bool(parts, 19),
        "spi": _bool(parts, 20),
        "on_ground": _bool(parts, 21),
        # UTC values are the canonical timestamps used for comparisons.
        "source_generated_at": generated_utc,
        "source_logged_at": logged_utc,
        "timestamp": logged_utc or generated_utc,
        "received_at": received_utc,
        # Preserve decoder-local values so the UI/debug logs can show exactly what
        # SDRuno/BaseStation emitted after timezone interpretation.
        "source_generated_local": generated_local,
        "source_logged_local": logged_local,
        "source_timezone_basis": "decoder-pc-local",
        "raw_text": raw,
    }
    return {key: value for key, value in record.items() if value is not None}


class SBSClient:
    """Read a TCP SBS/BaseStation feed and forward records as UDP JSON."""

    def __init__(
        self,
        sbs_host: str,
        sbs_port: int,
        udp_host: str,
        udp_port: int,
        reconnect_delay: float = 2.0,
    ) -> None:
        self.sbs_host = sbs_host
        self.sbs_port = sbs_port
        self.udp_host = udp_host
        self.udp_port = udp_port
        self.reconnect_delay = reconnect_delay
        self.stop_event = threading.Event()
        self.tcp: socket.socket | None = None
        self.udp = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.on_record = None
        self.on_status = None

    def _status(self, text: str) -> None:
        if self.on_status:
            self.on_status(text)

    def stop(self) -> None:
        self.stop_event.set()
        if self.tcp is not None:
            try:
                self.tcp.shutdown(socket.SHUT_RDWR)
            except OSError:
                pass
            try:
                self.tcp.close()
            except OSError:
                pass
            self.tcp = None

    def close(self) -> None:
        self.stop()
        try:
            self.udp.close()
        except OSError:
            pass

    def send(self, record: dict) -> None:
        payload = json.dumps(record, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
        self.udp.sendto(payload, (self.udp_host, self.udp_port))
        if self.on_record:
            self.on_record(record)

    def run(self) -> None:
        while not self.stop_event.is_set():
            try:
                self._status(f"Connecting to {self.sbs_host}:{self.sbs_port}…")
                tcp = socket.create_connection((self.sbs_host, self.sbs_port), timeout=5)
                tcp.settimeout(1.0)
                self.tcp = tcp
                self._status("Connected")
                buffer = b""
                while not self.stop_event.is_set():
                    try:
                        chunk = tcp.recv(8192)
                    except socket.timeout:
                        continue
                    if not chunk:
                        raise ConnectionError("SBS connection closed")
                    buffer += chunk
                    while b"\n" in buffer:
                        raw_line, buffer = buffer.split(b"\n", 1)
                        line = raw_line.decode("utf-8", errors="replace").rstrip("\r")
                        record = parse_sbs_line(line)
                        if record:
                            self.send(record)
            except Exception as exc:
                if self.stop_event.is_set():
                    break
                self._status(f"Disconnected: {exc}; retrying…")
                self.stop_event.wait(self.reconnect_delay)
            finally:
                if self.tcp is not None:
                    try:
                        self.tcp.close()
                    except OSError:
                        pass
                    self.tcp = None
        self._status("Stopped")
