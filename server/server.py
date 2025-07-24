
import socket, os, json, select
from shared.config import SERVER_PORT, CHUNK_SIZE

def handle_get_list(sock, addr):
    if not os.path.exists("data/file_list.txt"):
        sock.sendto(b"ERROR: file_list.txt not found", addr)
        return
    with open("data/file_list.txt", "r") as f:
        content = f.read()
    sock.sendto(content.encode(), addr)

def handle_get_chunk(sock, addr, request):
    fname = request.get("filename")
    offset = request.get("offset", 0)
    length = request.get("length", CHUNK_SIZE)

    fpath = f"data/{fname}"
    if not os.path.exists(fpath):
        sock.sendto(b"ERROR: File not found", addr)
        return

    with open(fpath, "rb") as f:
        f.seek(offset)
        data = f.read(length)
        sock.sendto(data, addr)

def main():
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.bind(('', SERVER_PORT))
    sock.setblocking(False)
    print(f"🟢 Server listening on UDP port {SERVER_PORT}...")

    while True:
        rlist, _, _ = select.select([sock], [], [], 2)
        if sock in rlist:
            data, addr = sock.recvfrom(4096)
            try:
                req = json.loads(data.decode())
                if req["type"] == "GET_LIST":
                    handle_get_list(sock, addr)
                elif req["type"] == "GET_CHUNK":
                    handle_get_chunk(sock, addr, req)
            except Exception as e:
                print(f"❌ Invalid request from {addr}: {e}")

if __name__ == "__main__":
    main()
