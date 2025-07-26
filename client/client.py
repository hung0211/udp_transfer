import socket, json, os, select
from shared.config import SERVER_IP, SERVER_PORT, CHUNK_SIZE, TIMEOUT, MAX_RETRIES
import threading
import hashlib
import base64
import time
from queue import Queue
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
            if size <= 0:
                return None
            return size
        except:
            print("[CLIENT] ❌ Unable to parse server response.")
            print(f"[CLIENT] 📦 Server response (raw): {data}")
            return None
    return None

def request_chunk_async(sock, filename, index, offset, length, result_dict, lock, result_array, num_chunks, log_per_chunk, retries=0):
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
            data, _ = sock.recvfrom(65536)
            if data == b"__END__":
                return

            packet = json.loads(data.decode())
            chunk_data = base64.b64decode(packet["data"])
            checksum = packet["checksum"]

            if hashlib.sha256(chunk_data).hexdigest() != checksum:
                raise ValueError("Checksum mismatch")

            with lock:
                result_dict[index] = chunk_data
                result_array[index - 1] = True

            if log_per_chunk:
                chunk_percent = (len(chunk_data) / length) * 100
                print(f"[CLIENT] 🍰 Downloading {filename} chunk {index}... {chunk_percent:.1f}%")
        except Exception:
            if retries < MAX_RETRIES:
                time.sleep(0.2)
                request_chunk_async(sock, filename, index, offset, length, result_dict, lock, result_array, num_chunks, log_per_chunk, retries + 1)
    else:
        if retries < MAX_RETRIES:
            time.sleep(0.2)
            request_chunk_async(sock, filename, index, offset, length, result_dict, lock, result_array, num_chunks, log_per_chunk, retries + 1)

def request_all_chunks_parallel(sock, filename):
    filesize = get_file_size(sock, filename)
    if filesize is None:
        print("❌ Unable to get file size.")
        return

    num_chunks = (filesize + CHUNK_SIZE - 1) // CHUNK_SIZE
    result_dict = {}
    result_array = [False] * num_chunks
    lock = threading.Lock()
    log_per_chunk = num_chunks > 1

    task_queue = Queue()
    for i in range(num_chunks):
        offset = i * CHUNK_SIZE
        task_queue.put((i + 1, offset, CHUNK_SIZE))

    if filesize > 100 * 1024 * 1024:
        num_worker_threads = 50
    elif filesize > 10 * 1024 * 1024:
        num_worker_threads = 30
    else:
        num_worker_threads = 10

    pbar = tqdm(total=num_chunks, desc=f"📥 Downloading {filename}", unit="chunk")

    def worker():
        while not task_queue.empty():
            try:
                index, offset, length = task_queue.get_nowait()
                request_chunk_async(sock, filename, index, offset, length, result_dict, lock, result_array, num_chunks, log_per_chunk)
                pbar.update(1)
            except:
                break
            finally:
                task_queue.task_done()

    threads = [threading.Thread(target=worker) for _ in range(num_worker_threads)]
    for t in threads: t.start()
    for t in threads: t.join()

    pbar.close()

    missing_chunks = [i for i in range(1, num_chunks + 1) if i not in result_dict]
    if missing_chunks:
        print(f"⚠️ Missing {len(missing_chunks)} chunk(s): {missing_chunks}. Retrying...")
        for i in missing_chunks:
            offset = (i - 1) * CHUNK_SIZE
            request_chunk_async(sock, filename, i, offset, CHUNK_SIZE, result_dict, lock, result_array, num_chunks, log_per_chunk)

    if len(result_dict) != num_chunks:
        print(f"❌ Still missing {num_chunks - len(result_dict)} chunk(s). Cannot assemble complete file.")
        return

    with open(f"received_{filename}", "wb") as f:
        for i in range(1, num_chunks + 1):
            f.write(result_dict[i])

    print(f"✅ Successfully downloaded file: received_{filename}")

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

def main():
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.setblocking(False)

    download_files_from_input(sock)

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n[CLIENT] 🛑 Client stopped.")
