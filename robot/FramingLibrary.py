"""Robot Framework keyword library over the framing module."""

from sut.framing import Decoder, encode


class FramingLibrary:
    ROBOT_LIBRARY_SCOPE = "TEST"

    def __init__(self):
        self.decoder = Decoder()
        self.received = []

    def send_frame(self, text):
        self.received += self.decoder.feed(encode(text.encode()))

    def send_raw_bytes(self, hex_string):
        self.received += self.decoder.feed(bytes.fromhex(hex_string))

    def send_corrupted_frame(self, text):
        wire = bytearray(encode(text.encode()))
        wire[-1] ^= 0xFF
        self.received += self.decoder.feed(bytes(wire))

    def received_frames_should_be(self, *expected):
        got = [f.decode() for f in self.received]
        if got != list(expected):
            raise AssertionError(f"expected {list(expected)}, got {got}")

    def crc_error_count_should_be(self, count):
        if self.decoder.crc_errors != int(count):
            raise AssertionError(f"expected {count} CRC errors, got {self.decoder.crc_errors}")
