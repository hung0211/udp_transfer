
import socket, json, os, select
from shared.config import SERVER_IP, SERVER_PORT, CHUNK_SIZE

def request_file_list(sock):
    req = { "type": "GET_LIST" }
    sock.sendto(json.dumps(req).encode(), (SERVER_IP, SERVER_PORT))
    rlist, _, _ = select.select([sock], [], [], 2)
    if rlist:
        data, _ = sock.recvfrom(4096)
        print("📄 Danh sách file từ server:")
        print(data.decode())
    else:
        print("❌ Không nhận được phản hồi từ server.")

def request_chunk(sock, filename, offset=0, length=CHUNK_SIZE):
    req = {
        "type": "GET_CHUNK",
        "filename": filename,
        "offset": offset,
        "length": length
    }
    sock.sendto(json.dumps(req).encode(), (SERVER_IP, SERVER_PORT))
    rlist, _, _ = select.select([sock], [], [], 2)
    if rlist:
        data, _ = sock.recvfrom(4096)
        with open(f"{filename}.part1", "wb") as f:
            f.write(data)
        print(f"✅ Đã nhận chunk đầu tiên và lưu vào {filename}.part1")
    else:
        print("❌ Không nhận được chunk từ server.")

def main():
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.setblocking(False)

    print("1. Nhận danh sách file từ server")
    request_file_list(sock)

    print("\n2. Gửi yêu cầu nhận chunk đầu tiên")
    filename = input("Nhập tên file cần tải (phải khớp file_list.txt): ").strip()
    request_chunk(sock, filename)

if __name__ == "__main__":
    main()
