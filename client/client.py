import socket
import os
from shared.config import SERVER_IP, SERVER_PORT, CHUNK_SIZE
from shared.protocol import build_packet

def send_file(file_path: str):
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)

    filesize = os.path.getsize(file_path)
    total_chunks = (filesize + CHUNK_SIZE - 1) // CHUNK_SIZE

    with open(file_path, 'rb') as f:
        for seq in range(total_chunks):
            chunk = f.read(CHUNK_SIZE)
            packet = build_packet(seq, chunk)
            sock.sendto(packet, (SERVER_IP, SERVER_PORT))
            print(f"[CLIENT] Sent chunk {seq}")

    # Gửi gói cuối để báo kết thúc
    sock.sendto(b'EOF', (SERVER_IP, SERVER_PORT))
    sock.close()
    print("[CLIENT] File sent completely.")

if __name__ == "__main__":
    send_file("test_files/sample.txt")
