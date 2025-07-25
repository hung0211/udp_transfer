import os
import socket
import select
import json
from shared.config import SERVER_PORT, CHUNK_SIZE, SERVER_IP

server_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
server_socket.bind((SERVER_IP, SERVER_PORT))
print(f"🟢 Server đang chạy tại {SERVER_IP}:{SERVER_PORT}")

with open("file_list.txt") as f:
    allowed_files = [line.strip() for line in f.readlines() if line.strip()]

def handle_get_list(addr):
    files = os.listdir(".")
    valid_files = [f for f in files if f in allowed_files]
    response = "\n".join(valid_files)
    server_socket.sendto(response.encode(), addr)

def handle_get_chunk(addr, filename, offset, length):
    if filename not in allowed_files:
        server_socket.sendto("❌ File không hợp lệ.".encode(), addr)
        return

    if not os.path.exists(filename):
        server_socket.sendto("❌ File không tồn tại.".encode(), addr)
        return

    with open(filename, "rb") as f:
        f.seek(offset)
        chunk = f.read(length)
        server_socket.sendto(chunk, addr)
        if len(chunk) < length:
            server_socket.sendto(b"__END__", addr)

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
        except Exception as e:
            print("❌ Lỗi xử lý request từ {addr}: {e}".encode())
