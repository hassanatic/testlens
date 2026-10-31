import pytest

from sut.framing import MAX_PAYLOAD, Decoder, crc16_ccitt, encode


def test_crc_matches_the_standard_check_value():
    # CRC-16/CCITT-FALSE check value for "123456789"
    assert crc16_ccitt(b"123456789") == 0x29B1


@pytest.mark.parametrize("payload", [b"", b"\x01", b"hello", bytes(range(MAX_PAYLOAD))])
def test_round_trip(payload):
    assert Decoder().feed(encode(payload)) == [payload]


def test_frames_split_across_reads_are_reassembled():
    d = Decoder()
    wire = encode(b"abc") + encode(b"defg")
    out = []
    for i in range(len(wire)):
        out += d.feed(wire[i:i + 1])
    assert out == [b"abc", b"defg"]


def test_garbage_before_a_frame_is_dropped_and_counted():
    d = Decoder()
    assert d.feed(b"\x00\x11\x22" + encode(b"ok")) == [b"ok"]
    assert d.dropped_bytes == 3


def test_corrupt_frame_is_skipped_and_the_next_one_still_decodes():
    bad = bytearray(encode(b"broken"))
    bad[4] ^= 0xFF
    d = Decoder()
    assert d.feed(bytes(bad) + encode(b"next")) == [b"next"]
    assert d.crc_errors == 1


def test_start_byte_inside_a_payload_does_not_confuse_resync():
    d = Decoder()
    assert d.feed(encode(b"\x7e\x7e") + encode(b"z")) == [b"\x7e\x7e", b"z"]


def test_oversized_payload_is_refused():
    with pytest.raises(ValueError):
        encode(bytes(MAX_PAYLOAD + 1))
