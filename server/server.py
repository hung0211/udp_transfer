import os, socket, json, base64, hashlib, select
from shared.config import SERVER_IP, SERVER_PORT, CHUNK_SIZE

# Tạo socket UDP và gán (bind) vào địa chỉ IP và cổng chỉ định
server_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
server_socket.bind((SERVER_IP, SERVER_PORT))
print(f"[SERVER] Running on {SERVER_IP}:{SERVER_PORT}")

# Đọc danh sách các file được phép chia sẻ từ file_list.txt
with open("server/file_list.txt") as f:
    allowed_files = [line.strip() for line in f if line.strip()]

# Gửi danh sách các file hợp lệ cho client
def handle_get_list(addr):
    files = os.listdir("server")  # Liệt kê tất cả file trong thư mục server/
    valid_files = [f for f in files if f in allowed_files]  # Lọc ra file hợp lệ
    response = "\n".join(valid_files)
    server_socket.sendto(response.encode(), addr)  # Gửi danh sách file

# Gửi một chunk dữ liệu từ file về cho client
def handle_get_chunk(addr, filename, offset, length):
    filepath = f"server/{filename}"
    
    # Kiểm tra file có nằm trong danh sách hợp lệ và tồn tại không
    if filename not in allowed_files or not os.path.exists(filepath):
        server_socket.sendto(b"__INVALID__", addr)
        return

    with open(filepath, "rb") as f:
        f.seek(offset)  # Di chuyển đến offset chỉ định trong file
        chunk = f.read(length)  # Đọc đoạn dữ liệu có độ dài tương ứng

        # Mã hóa dữ liệu chunk bằng base64 và tạo checksum
        encoded = base64.b64encode(chunk).decode()
        checksum = hashlib.sha256(chunk).hexdigest()

        # Tạo packet chứa dữ liệu và checksum gửi cho client
        packet = {
            "data": encoded,
            "checksum": checksum
        }
        server_socket.sendto(json.dumps(packet).encode(), addr)

        # Chờ nhận ACK từ client (timeout 1 giây)
        rlist, _, _ = select.select([server_socket], [], [], 1.0)
        if rlist:
            ack_data, ack_addr = server_socket.recvfrom(4096)
            try:
                ack_msg = json.loads(ack_data.decode())
                # Nếu cần xử lý logic ACK thì xử lý ở đây (đang tạm thời comment)
                # if (
                #     ack_msg.get("type") == "ACK" and
                #     ack_msg.get("filename") == filename and
                #     ack_msg.get("offset") == offset
                # ):
                #     print(f"[SERVER] ✅ ACK received for {filename} offset {offset} from {ack_addr}")
                pass
            except Exception as e:
                print(f"[SERVER] ⚠️ Failed to parse ACK from {addr}: {e}")

# Gửi kích thước file về cho client
def handle_get_size(addr, filename):
    filepath = f"server/{filename}"
    
    # Kiểm tra file có hợp lệ và tồn tại không
    if filename not in allowed_files or not os.path.exists(filepath):
        server_socket.sendto(b"0", addr)  # Gửi 0 nếu file không tồn tại
        return

    size = os.path.getsize(filepath)
    print(f"[SERVER] ✅ Sent size of file {filename}: {size} bytes")
    server_socket.sendto(str(size).encode(), addr)

# Vòng lặp chính của server
try:
    while True:
        # Dùng select để kiểm tra socket có dữ liệu đến không (timeout 1 giây)
        rlist, _, _ = select.select([server_socket], [], [], 1)
        if rlist:
            data, addr = server_socket.recvfrom(65536)
            try:
                # Parse dữ liệu yêu cầu JSON từ client
                req = json.loads(data.decode())

                # Gọi hàm xử lý tương ứng với loại yêu cầu
                if req["type"] == "GET_LIST":
                    handle_get_list(addr)
                elif req["type"] == "GET_CHUNK":
                    handle_get_chunk(addr, req["filename"], req["offset"], req["length"])
                elif req["type"] == "GET_SIZE":
                    handle_get_size(addr, req["filename"])
            except Exception as e:
                print(f"[SERVER] ❌ Error handling request from {addr}: {e}")

# Bắt tổ hợp phím Ctrl+C để dừng server an toàn
except KeyboardInterrupt:
    print("\n[SERVER] 🛑 Ctrl+C received. Shutting down server...")
    server_socket.close()
