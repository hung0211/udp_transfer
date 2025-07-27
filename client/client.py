import socket, json, os, select
from shared.config import SERVER_IP, SERVER_PORT, CHUNK_SIZE, TIMEOUT, MAX_RETRIES
import threading
import hashlib
import base64
import time
from tqdm import tqdm

# Gửi yêu cầu lấy danh sách file từ server
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

# Gửi yêu cầu lấy kích thước file từ server
def get_file_size(sock, filename):
    req = {"type": "GET_SIZE", "filename": filename}
    sock.sendto(json.dumps(req).encode(), (SERVER_IP, SERVER_PORT))

    rlist, _, _ = select.select([sock], [], [], TIMEOUT)
    if rlist:
        data, _ = sock.recvfrom(4096)
        try:
            size = int(data.decode())
            if size <= 0:
                return None
            return size
        except:
            print("[CLIENT] ❌ Unable to parse server response.")
            print(f"[CLIENT] 📦 Server response (raw): {data}")
            return None
    return None

# Tải 1 chunk đơn lẻ với retry
def download_chunk(sock, filename, index, offset, length, result_dict, lock, result_array, retries=0):
    req = {
        "type": "GET_CHUNK",
        "filename": filename,
        "offset": offset,
        "length": length
    }

    sock.sendto(json.dumps(req).encode(), (SERVER_IP, SERVER_PORT))
    ready, _, _ = select.select([sock], [], [], TIMEOUT)

    if ready:
        try:
            data, server_addr = sock.recvfrom(65536)
            if data == b"__INVALID__":
                print(f"[CLIENT] ❌ Invalid request for {filename} offset {offset}. Skipping chunk {index}.")
                return

            packet = json.loads(data.decode())
            chunk_data = base64.b64decode(packet["data"])
            checksum = packet["checksum"]

            if hashlib.sha256(chunk_data).hexdigest() != checksum:
                raise ValueError("Checksum mismatch")

            # Gửi ACK
            ack_msg = json.dumps({"type": "ACK", "filename": filename, "offset": offset})
            sock.sendto(ack_msg.encode(), server_addr)

            with lock:
                result_dict[index] = chunk_data
                result_array[index - 1] = True

            percent = len(chunk_data) / length * 100
            print(f"[CLIENT] Downloading {filename} chunk {index}... {percent:.2f}%")
        except Exception as e:
            print(f"[CLIENT] ⚠️ Error chunk {index}: {e}")
            if retries < MAX_RETRIES:
                time.sleep(0.2)
                download_chunk(sock, filename, index, offset, length, result_dict, lock, result_array, retries + 1)
    else:
        if retries < MAX_RETRIES:
            time.sleep(0.2)
            download_chunk(sock, filename, index, offset, length, result_dict, lock, result_array, retries + 1)

# Tải toàn bộ file với đúng 4 kết nối song song
def request_all_chunks_parallel(sock_main, filename):
    filesize = get_file_size(sock_main, filename)
    if filesize is None:
        print("❌ Unable to get file size.")
        return

    num_chunks = (filesize + CHUNK_SIZE - 1) // CHUNK_SIZE
    result_dict = {}
    result_array = [False] * num_chunks
    lock = threading.Lock()

    indices = list(range(1, num_chunks + 1))
    parts = [indices[i::4] for i in range(4)]  # chia đều cho 4 phần

    sockets = [socket.socket(socket.AF_INET, socket.SOCK_DGRAM) for _ in range(4)]
    threads = []

    def worker(sock, assigned_chunks):
        for index in assigned_chunks:
            offset = (index - 1) * CHUNK_SIZE
            download_chunk(sock, filename, index, offset, CHUNK_SIZE, result_dict, lock, result_array)

    for i in range(4):
        t = threading.Thread(target=worker, args=(sockets[i], parts[i]))
        threads.append(t)
        t.start()

    pbar = tqdm(total=num_chunks, desc=f"📥 Downloading {filename}", unit="chunk")
    prev_count = 0
    while any(t.is_alive() for t in threads):
        count = sum(result_array)
        pbar.update(count - prev_count)
        prev_count = count
        time.sleep(0.5)
    pbar.update(sum(result_array) - prev_count)
    pbar.close()

    for t in threads: t.join()
    for s in sockets: s.close()

    if len(result_dict) != num_chunks:
        print(f"❌ Still missing {num_chunks - len(result_dict)} chunk(s). Cannot assemble complete file.")
        return

    with open(f"received_{filename}", "wb") as f:
        for i in range(1, num_chunks + 1):
            f.write(result_dict[i])
    print(f"✅ Successfully downloaded file: received_{filename}")

# Theo dõi file input.txt định kỳ để tải file mới
def download_files_from_input(sock, idle_timeout=10):
    downloaded = set()
    idle_time = 0
    poll_interval = 2
    print(f"[CLIENT] Monitoring input.txt. Will stop if no new file in {idle_timeout} seconds.")

    available_files = request_file_list(sock)

    while True:
        try:
            with open("client/input.txt") as f:
                filenames = [line.strip() for line in f.readlines() if line.strip()]
        except:
            print("[CLIENT] ❌ Unable to read input.txt")
            time.sleep(poll_interval)
            idle_time += poll_interval
            if idle_time >= idle_timeout:
                print("[CLIENT] ⏹ No activity. Stopping client.")
                break
            continue

        new_files = [fn for fn in filenames if fn not in downloaded]
        if new_files:
            idle_time = 0
            for filename in new_files:
                if filename not in available_files:
                    print(f"[CLIENT] ❌ File '{filename}' not found on server. Skipping.")
                    downloaded.add(filename)
                    continue
                print(f"\n🚀 Starting download: {filename}")
                request_all_chunks_parallel(sock, filename)
                downloaded.add(filename)
        else:
            idle_time += poll_interval
            if idle_time >= idle_timeout:
                print(f"[CLIENT] ⏹ No new file in {idle_timeout} seconds. Stopping client.")
                break
        time.sleep(poll_interval)

# Hàm main
def main():
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.setblocking(False)
    download_files_from_input(sock)

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n[CLIENT] 🛑 Client stopped.")
        
