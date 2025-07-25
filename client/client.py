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

def request_all_chunks(sock, filename):
    offset = 0
    part = 1
    chunk_files = []
    while True:
        req = {
            "type": "GET_CHUNK",
            "filename": filename,
            "offset": offset,
            "length": CHUNK_SIZE
        }
        sock.sendto(json.dumps(req).encode(), (SERVER_IP, SERVER_PORT))
        rlist, _, _ = select.select([sock], [], [], 3)
        if not rlist:
            print("❌ Mất kết nối tới server hoặc timeout.")
            break

        data, _ = sock.recvfrom(4096)
        if data == b"__END__":
            print("✅ Hoàn tất tải file.")
            break

        part_file = f"{filename}.part{part}"
        with open(part_file, "wb") as f:
            f.write(data)
        print(f"✅ Nhận chunk {part}, ghi vào {part_file}")
        chunk_files.append(part_file)
        offset += len(data)
        part += 1

    # Gộp file
    with open(f"received_{filename}", "wb") as outfile:
        for pf in chunk_files:
            with open(pf, "rb") as f:
                outfile.write(f.read())
    print(f"📦 Đã ghép thành công file: received_{filename}")

def main():
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.setblocking(False)

    print("1. Nhận danh sách file từ server")
    request_file_list(sock)

    print("\n2. Tải file đầy đủ từ server")
    filename = input("Nhập tên file cần tải (phải khớp file_list.txt): ").strip()
    request_all_chunks(sock, filename)

if __name__ == "__main__":
    main()
