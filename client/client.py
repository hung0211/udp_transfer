import os
import socket
import select
import json
from shared.config import SERVER_PORT, CHUNK_SIZE, OUTPUT_FILE, SERVER_HOST

def request_all_chunks(sock, filename):
    offset = 0
    part_number = 1
    while True:
        req = {
            "type": "GET_CHUNK",
            "filename": filename,
            "offset": offset,
            "length": CHUNK_SIZE
        }
        sock.sendto(json.dumps(req).encode(), (SERVER_HOST, SERVER_PORT))

        ready, _, _ = select.select([sock], [], [], 2)
        if ready:
            data, _ = sock.recvfrom(CHUNK_SIZE + 1024)
            if data == b"__END__":
                print("\n✅ Đã nhận đủ tất cả các phần của file.")
                break
            part_filename = f"{filename}.part{part_number}"
            with open(part_filename, "wb") as f:
                f.write(data)
            print(f"📥 Đã nhận chunk {part_number} (offset {offset}) và lưu vào {part_filename}")
            offset += CHUNK_SIZE
            part_number += 1
        else:
            print(f"❌ Không nhận được phản hồi từ server tại offset {offset}")
            break

def merge_chunks(filename):
    print(f"\n🛠 Bắt đầu ghép file '{filename}' từ các phần...")
    with open(OUTPUT_FILE, "wb") as out:
        part = 1
        while True:
            part_file = f"{filename}.part{part}"
            if not os.path.exists(part_file):
                break
            with open(part_file, "rb") as pf:
                out.write(pf.read())
            print(f"✅ Đã ghép {part_file}")
            part += 1
    print(f"\n🎉 File hoàn chỉnh đã được lưu thành công vào: {OUTPUT_FILE}")

def request_file_list(sock):
    req = { "type": "GET_LIST" }
    sock.sendto(json.dumps(req).encode(), (SERVER_HOST, SERVER_PORT))
    rlist, _, _ = select.select([sock], [], [], 2)
    if rlist:
        data, _ = sock.recvfrom(4096)
        print("📄 Danh sách file từ server:")
        print(data.decode())
    else:
        print("❌ Không nhận được phản hồi từ server.")

def main():
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.setblocking(False)

    print("1. Nhận danh sách file từ server")
    request_file_list(sock)

    print("\n2. Tải toàn bộ file từng phần")
    filename = input("Nhập tên file cần tải (phải khớp file_list.txt): ").strip()
    request_all_chunks(sock, filename)
    merge_chunks(filename)

if __name__ == "__main__":
    main()
