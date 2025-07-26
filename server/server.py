import os, socket, json, base64, hashlib, select
from shared.config import SERVER_IP, SERVER_PORT, CHUNK_SIZE

server_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
server_socket.bind((SERVER_IP, SERVER_PORT))
print(f"[SERVER] Đang chạy tại {SERVER_IP}:{SERVER_PORT}")

# Danh sách file hợp lệ
with open("server/file_list.txt") as f:
    allowed_files = [line.strip() for line in f if line.strip()]

def handle_get_list(addr):
    files = os.listdir("server")
    valid_files = [f for f in files if f in allowed_files]
    response = "\n".join(valid_files)
    server_socket.sendto(response.encode(), addr)

def handle_get_chunk(addr, filename, offset, length):
    filepath = f"server/{filename}"
    if filename not in allowed_files or not os.path.exists(filepath):
        server_socket.sendto(b"__INVALID__", addr)
        return

    with open(filepath, "rb") as f:
        f.seek(offset)
        chunk = f.read(length)

        encoded = base64.b64encode(chunk).decode()
        checksum = hashlib.sha256(chunk).hexdigest()

        packet = {
            "data": encoded,
            "checksum": checksum
        }
        server_socket.sendto(json.dumps(packet).encode(), addr)

def handle_get_size(addr, filename):
    filepath = f"server/{filename}"
    if filename not in allowed_files or not os.path.exists(filepath):
        server_socket.sendto(b"0", addr)
        return
    size = os.path.getsize(filepath)
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
                elif req["type"] == "GET_SIZE":
                    handle_get_size(addr, req["filename"])
            except Exception as e:
                print(f"[SERVER] ❌ Lỗi khi xử lý request từ {addr}: {e}")
except KeyboardInterrupt:
    print("\n[SERVER] 🛑 Đã nhận tín hiệu Ctrl+C. Đang tắt server...")
    server_socket.close()
