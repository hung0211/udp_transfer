import socket
import select
from shared.config import SERVER_PORT, CHUNK_SIZE, OUTPUT_FILE
from shared.protocol import parse_packet

BUFFER_SIZE = 4096
sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
sock.bind(('0.0.0.0', SERVER_PORT))
sock.setblocking(False)

print(f"[SERVER] Listening on port {SERVER_PORT}...")

chunks = {}

while True:
    readable, _, _ = select.select([sock], [], [], 2)
    if sock in readable:
        data, addr = sock.recvfrom(BUFFER_SIZE)

        if data == b'EOF':
            print("[SERVER] End of file signal received.")
            break

        seq, payload = parse_packet(data)
        chunks[seq] = payload
        print(f"[SERVER] Received chunk {seq} from {addr}")

# Ghi file ra ổ đĩa
with open(OUTPUT_FILE, 'wb') as f:
    for i in sorted(chunks.keys()):
        f.write(chunks[i])

print(f"[SERVER] File written to {OUTPUT_FILE}")
