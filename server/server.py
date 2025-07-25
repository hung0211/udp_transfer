import os
import socket
import select
import json
import hashlib
import base64
from shared.config import SERVER_PORT, CHUNK_SIZE, SERVER_IP

server_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
server_socket.bind((SERVER_IP, SERVER_PORT))
print(f"[SERVER] Đang chạy tại {SERVER_IP}:{SERVER_PORT}")

try:
    with open("server/file_list.txt") as f:
        allowed_files = [line.strip() for line in f.readlines() if line.strip()]
except FileNotFoundError:
    print("❌ Không tìm thấy file_list.txt trong thư mục server/")
    allowed_files = []

def handle_get_list(addr):
    files = os.listdir("server")
    valid_files = [f for f in files if f in allowed_files]
    response = "\n".join(valid_files)
    server_socket.sendto(response.encode(), addr)

def handle_get_chunk(addr, filename, offset, length):
    filepath = os.path.join("server", filename)
    if filename not in allowed_files or not os.path.exists(filepath):
        server_socket.sendto("__INVALID__".encode(), addr)
        return

    with open(filepath, "rb") as f:
        f.seek(offset)
        chunk = f.read(length)

        checksum = hashlib.sha256(chunk).hexdigest()
        packet = {
            "data": base64.b64encode(chunk).decode(),  # Encode để truyền an toàn
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

try:
    while True:
        rlist, _, _ = select.select([server_socket], [], [], 1)
        if rlist:
            data, addr = server_socket.recvfrom(4096)
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
    print("\n[SERVER] 🛑 Đã dừng server bằng Ctrl+C.")
    server_socket.close()

