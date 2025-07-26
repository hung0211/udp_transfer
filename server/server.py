import os
import socket
import select
import json
from shared.config import SERVER_PORT, CHUNK_SIZE, SERVER_IP
import hashlib
import base64

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
    file_path = os.path.join("server", filename)
    if filename not in allowed_files or not os.path.exists(file_path):
        server_socket.sendto(b"__INVALID__", addr)
        return

    try:
        with open(file_path, "rb") as f:
            f.seek(offset)
            chunk = f.read(length)

            checksum = hashlib.sha256(chunk).hexdigest()
            packet = {
                "data": base64.b64encode(chunk).decode(),
                "checksum": checksum
            }
            server_socket.sendto(json.dumps(packet).encode(), addr)
    except Exception as e:
        print(f"[SERVER] ❌ Lỗi khi gửi chunk: {e}")

def handle_get_size(addr, filename):
    full_path = os.path.join("server", filename)

    if filename not in allowed_files:
        print(f"[SERVER] ❌ File không được phép: {filename}")
        server_socket.sendto(b"__INVALID__", addr)
        return

    if not os.path.exists(full_path):
        print(f"[SERVER] ❌ File không tồn tại: {full_path}")
        server_socket.sendto(b"__INVALID__", addr)
        return

    size = os.path.getsize(full_path)
    print(f"[SERVER] ✅ Trả kích thước file {filename}: {size} bytes")
    server_socket.sendto(str(size).encode(), addr)

try:
    while True:
        rlist, _, _ = select.select([server_socket], [], [], 1)
        if rlist:
            data, addr = server_socket.recvfrom(65536)
            try:
                req = json.loads(data.decode())
                if req["type"] == "GET_LIST":
                    handle_get_list(addr)
                elif req["type"] == "GET_CHUNK":
                    handle_get_chunk(addr, req["filename"], req["offset"], req["length"])
                # elif req["type"] == "GET_SIZE":
                    # handle_get_size(addr, req["filename"])
                elif req["type"] == "GET_SIZE":
                    print(f"[SERVER] GET_SIZE request: {req['filename']} from {addr}")
                    handle_get_size(addr, req["filename"])
            except Exception as e:
                print(f"❌ Lỗi xử lý request từ {addr}: {e}")
except KeyboardInterrupt:
    print("\n[SERVER] 🛑 Dừng server theo yêu cầu.")
    server_socket.close()
