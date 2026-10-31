"""A small framed serial protocol, used as the system under test.

Frame: 0x7E | length (1 byte) | payload | CRC-16/CCITT-FALSE over length and payload
(2 bytes, big-endian). The decoder is fed bytes as they arrive, keeps partial frames
between reads, and resynchronises on the next start byte after a corrupt frame.
"""

from __future__ import annotations

START = 0x7E
MAX_PAYLOAD = 64


def crc16_ccitt(data: bytes, crc: int = 0xFFFF) -> int:
    for b in data:
        crc ^= b << 8
        for _ in range(8):
            crc = ((crc << 1) ^ 0x1021) if crc & 0x8000 else (crc << 1)
            crc &= 0xFFFF
    return crc


def encode(payload: bytes) -> bytes:
    if len(payload) > MAX_PAYLOAD:
        raise ValueError(f"payload of {len(payload)} bytes exceeds {MAX_PAYLOAD}")
    body = bytes([len(payload)]) + payload
    return bytes([START]) + body + crc16_ccitt(body).to_bytes(2, "big")


class Decoder:
    def __init__(self) -> None:
        self.buffer = bytearray()
        self.crc_errors = 0
        self.dropped_bytes = 0

    def feed(self, data: bytes) -> list[bytes]:
        self.buffer.extend(data)
        frames = []
        while True:
            start = self.buffer.find(START)
            if start < 0:
                self.dropped_bytes += len(self.buffer)
                self.buffer.clear()
                return frames
            if start:
                self.dropped_bytes += start
                del self.buffer[:start]
            if len(self.buffer) < 2:
                return frames
            length = self.buffer[1]
            if length > MAX_PAYLOAD:
                # not a real frame: skip this start byte and look for the next one
                self.dropped_bytes += 1
                del self.buffer[0]
                continue
            total = 1 + 1 + length + 2
            if len(self.buffer) < total:
                return frames
            body = bytes(self.buffer[1:2 + length])
            crc = int.from_bytes(self.buffer[2 + length:total], "big")
            if crc16_ccitt(body) == crc:
                frames.append(body[1:])
                del self.buffer[:total]
            else:
                self.crc_errors += 1
                self.dropped_bytes += 1
                del self.buffer[0]
