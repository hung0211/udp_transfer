# shared/protocol.py

def build_packet(seq: int, data: bytes) -> bytes:
    seq_bytes = seq.to_bytes(4, byteorder='big')
    return seq_bytes + data

def parse_packet(packet: bytes):
    seq = int.from_bytes(packet[:4], byteorder='big')
    payload = packet[4:]
    return seq, payload
