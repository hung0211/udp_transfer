import os
import socket
import json
import select
import hashlib
from shared.config import SERVER_IP, SERVER_PORT

server_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
server_socket.bind((SERVER_IP, SERVER_PORT))
print(f"[SERVER] Đang chạy tại {SERVER_IP}:{SERVER_PORT}")

with open("server/file_list.txt") as f:
    allowed_files = [line.strip() for line in f.readlines() if line.strip()]

def handle_get_list(addr):
    files = os.listdir("server")
    valid_files = [f for f in files if f in allowed_files]
    response = "\n".join(valid_files)
    server_socket.sendto(response.encode(), addr)

def handle_get_chunk(addr, filename, offset, length):
    path = os.path.join("server", filename)
    if filename not in allowed_files or not os.path.exists(path):
        server_socket.sendto("__INVALID__".encode(), addr)
        return

    with open(path, "rb") as f:
        f.seek(offset)
        chunk = f.read(length)

        checksum = hashlib.sha256(chunk).hexdigest()
        packet = {
            "data": base64.b64encode(chunk).decode(),
            "checksum": checksum
        }
        server_socket.sendto(json.dumps(packet).encode(), addr)

def handle_get_size(addr, filename):
    filepath = os.path.join("server", filename)
    if filename not in allowed_files or not os.path.exists(filepath):
        server_socket.sendto(b"0", addr)
    else:
        size = os.path.getsize(filepath)
        server_socket.sendto(str(size).encode(), addr)

def base64_encode(data):
    import base64
    return base64.b64encode(data).decode()

try:
    while True:
        rlist, _, _ = select.select([server_socket], [], [], 1)
        if rlist:
            data, addr = server_socket.recvfrom(8192)
            try:
                req = json.loads(data.decode())
                if req["type"] == "GET_LIST":
                    handle_get_list(addr)
                elif req["type"] == "GET_CHUNK":
                    handle_get_chunk(addr, req["filename"], req["offset"], req["length"])
                elif req["type"] == "GET_SIZE":
                    handle_get_size(addr, req["filename"])
            except Exception as e:
                print(f"❌ Lỗi xử lý request từ {addr}: {e}")
except KeyboardInterrupt:
    print("\n[SERVER] 🛑 Dừng server.")
