import socket, json, os, select
from shared.config import SERVER_IP, SERVER_PORT, CHUNK_SIZE, TIMEOUT
import threading
import hashlib
import base64
import time
from tqdm import tqdm

def request_file_list(sock):
    req = {"type": "GET_LIST"}
    sock.sendto(json.dumps(req).encode(), (SERVER_IP, SERVER_PORT))
    rlist, _, _ = select.select([sock], [], [], TIMEOUT)
    if rlist:
        data, _ = sock.recvfrom(4096)
        file_list = data.decode().splitlines()
        print("[CLIENT] File list from server:")
        for f in file_list:
            print(f)
        return set(file_list)
    else:
        print("[CLIENT] ❌ No response from server.")
        return set()

def get_file_size(sock, filename):
    req = {"type": "GET_SIZE", "filename": filename}
    sock.sendto(json.dumps(req).encode(), (SERVER_IP, SERVER_PORT))
    rlist, _, _ = select.select([sock], [], [], TIMEOUT)
    if rlist:
        data, _ = sock.recvfrom(4096)
        try:
            size = int(data.decode())
            return size if size > 0 else None
        except:
            return None
    return None

def download_chunks(sock, filename, indices, result_dict, lock, result_array):
    for index in indices:
        offset = (index - 1) * CHUNK_SIZE
        req = {
            "type": "GET_CHUNK",
            "filename": filename,
            "offset": offset,
            "length": CHUNK_SIZE
        }
        sock.sendto(json.dumps(req).encode(), (SERVER_IP, SERVER_PORT))
        ready, _, _ = select.select([sock], [], [], TIMEOUT)
        if ready:
            try:
                data, server_addr = sock.recvfrom(65536)
                if data == b"__INVALID__":
                    print(f"[CLIENT] ❌ Invalid request for {filename} offset {offset}")
                    continue
                packet = json.loads(data.decode())
                chunk_data = base64.b64decode(packet["data"])
                checksum = packet["checksum"]
                if hashlib.sha256(chunk_data).hexdigest() != checksum:
                    raise ValueError("Checksum mismatch")
                ack_msg = json.dumps({"type": "ACK", "filename": filename, "offset": offset})
                sock.sendto(ack_msg.encode(), server_addr)
                with lock:
                    result_dict[index] = chunk_data
                    result_array[index - 1] = True
            except Exception as e:
                print(f"[CLIENT] ⚠️ Error on chunk {index}: {e}")

def request_all_chunks_parallel(sock_main, filename):
    filesize = get_file_size(sock_main, filename)
    if filesize is None:
        print("❌ Cannot get file size.")
        return

    num_chunks = (filesize + CHUNK_SIZE - 1) // CHUNK_SIZE
    result_dict = {}
    result_array = [False] * num_chunks
    lock = threading.Lock()

    indices = list(range(1, num_chunks + 1))
    parts = [indices[i::4] for i in range(4)]

    sockets = [socket.socket(socket.AF_INET, socket.SOCK_DGRAM) for _ in range(4)]
    threads = []

    for i in range(4):
        t = threading.Thread(target=download_chunks, args=(sockets[i], filename, parts[i], result_dict, lock, result_array))
        threads.append(t)
        t.start()

    pbar = tqdm(total=num_chunks, desc=f"📥 Downloading {filename}", unit="chunk")
    prev_count = 0
    while any(t.is_alive() for t in threads):
        count = sum(result_array)
        pbar.update(count - prev_count)
        prev_count = count
        time.sleep(0.3)
    pbar.update(sum(result_array) - prev_count)
    pbar.close()

    for t in threads: t.join()
    for s in sockets: s.close()

    if len(result_dict) != num_chunks:
        print("❌ Incomplete file.")
        return

    with open(f"received_{filename}", "wb") as f:
        for i in range(1, num_chunks + 1):
            f.write(result_dict[i])

    print(f"✅ Downloaded file: received_{filename}")

def download_files_from_input(sock, idle_timeout=10):
    downloaded = set()
    idle_time = 0
    poll_interval = 2
    print(f"[CLIENT] Monitoring input.txt for up to {idle_timeout} seconds idle.")

    available_files = request_file_list(sock)

    while True:
        try:
            with open("client/input.txt") as f:
                filenames = [line.strip() for line in f if line.strip()]
        except:
            time.sleep(poll_interval)
            idle_time += poll_interval
            if idle_time >= idle_timeout:
                break
            continue

        new_files = [fn for fn in filenames if fn not in downloaded]
        if new_files:
            idle_time = 0
            for filename in new_files:
                if filename not in available_files:
                    print(f"[CLIENT] ❌ {filename} not found on server")
                    downloaded.add(filename)
                    continue
                request_all_chunks_parallel(sock, filename)
                downloaded.add(filename)
        else:
            idle_time += poll_interval
            if idle_time >= idle_timeout:
                break
        time.sleep(poll_interval)

def main():
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.setblocking(False)
    download_files_from_input(sock)

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n[CLIENT] 🛑 Stopped.")
