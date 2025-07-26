import socket, json, os, select
from shared.config import SERVER_IP, SERVER_PORT, CHUNK_SIZE, TIMEOUT, MAX_RETRIES
import threading
import hashlib
import base64
import time

def request_file_list(sock):
    req = {"type": "GET_LIST"}
    sock.sendto(json.dumps(req).encode(), (SERVER_IP, SERVER_PORT))
    rlist, _, _ = select.select([sock], [], [], TIMEOUT)
    if rlist:
        data, _ = sock.recvfrom(4096)
        print("[CLIENT] Danh sách file từ server:")
        print(data.decode())
    else:
        print("[CLIENT] ❌ Không nhận được phản hồi từ server.")

def get_file_size(sock, filename):
    req = {"type": "GET_SIZE", "filename": filename}
    sock.sendto(json.dumps(req).encode(), (SERVER_IP, SERVER_PORT))
    rlist, _, _ = select.select([sock], [], [], TIMEOUT)
    if rlist:
        data, _ = sock.recvfrom(4096)
        print(f"[CLIENT] 📦 Phản hồi server (raw): {repr(data)}")  
        try:
            size = int(data.decode())
            if size <= 0:
                print(f"[CLIENT] ❌ Kích thước không hợp lệ hoặc bị từ chối: {size}")
                return None
            return size
        except Exception as e:
            print(f"[CLIENT] ❌ Không thể phân tích phản hồi từ server: {e}")
            return None
    else:
        print("[CLIENT] ❌ Timeout khi chờ kích thước.")
        return None

def request_chunk_async(sock, filename, index, offset, length, result_dict, lock, result_array, num_chunks, retries=0):
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
                print(f"[CLIENT] ✅ Chunk {index} nhận xong (EOF)")
                return

            packet = json.loads(data.decode())
            chunk_data = base64.b64decode(packet["data"])
            checksum = packet["checksum"]

            if hashlib.sha256(chunk_data).hexdigest() != checksum:
                raise ValueError("Checksum mismatch")

            with lock:
                result_dict[index] = chunk_data
                result_array[index - 1] = True
                completed = sum(1 for x in result_array if x)
                percent = (completed / num_chunks) * 100
                print(f"[CLIENT] ✅ Chunk {index} nhận thành công ({len(chunk_data)} bytes)")
                print(f"[CLIENT] 🟡 Tiến độ: {completed}/{num_chunks} chunks ({percent:.2f}%)")

        except Exception as e:
            print(f"[CLIENT] ❌ Lỗi khi nhận chunk {index}: {e}")
            if retries < MAX_RETRIES:
                print(f"[CLIENT] 🔁 Thử lại chunk {index} ({retries + 1}/{MAX_RETRIES})...")
                time.sleep(0.2)
                request_chunk_async(sock, filename, index, offset, length, result_dict, lock, result_array, num_chunks, retries + 1)
            else:
                print(f"[CLIENT] ❌ Chunk {index} thất bại sau {MAX_RETRIES} lần thử.")
    else:
        if retries < MAX_RETRIES:
            print(f"[CLIENT] ⚠️ Chunk {index} timeout, thử lại ({retries + 1})...")
            time.sleep(0.2)
            request_chunk_async(sock, filename, index, offset, length, result_dict, lock, result_array, num_chunks, retries + 1)
        else:
            print(f"[CLIENT] ❌ Chunk {index} thất bại sau {MAX_RETRIES} lần thử.")

def request_all_chunks_parallel(sock, filename):
    filesize = get_file_size(sock, filename)
    if filesize is None:
        print("❌ Không thể lấy kích thước file.")
        return

    num_chunks = (filesize + CHUNK_SIZE - 1) // CHUNK_SIZE
    result_dict = {}
    result_array = [False] * num_chunks
    threads = []
    lock = threading.Lock()

    for i in range(num_chunks):
        offset = i * CHUNK_SIZE
        t = threading.Thread(target=request_chunk_async, args=(sock, filename, i + 1, offset, CHUNK_SIZE, result_dict, lock, result_array, num_chunks))
        t.start()
        threads.append(t)

    for t in threads:
        t.join()

    missing_chunks = [i for i in range(1, num_chunks + 1) if i not in result_dict]
    if missing_chunks:
        print(f"⚠️ Thiếu {len(missing_chunks)} chunk(s): {missing_chunks}. Thử tải lại...")
        for i in missing_chunks:
            offset = (i - 1) * CHUNK_SIZE
            request_chunk_async(sock, filename, i, offset, CHUNK_SIZE, result_dict, lock, result_array, num_chunks)

    if len(result_dict) != num_chunks:
        print(f"❌ Vẫn còn thiếu {num_chunks - len(result_dict)} chunk(s). Không thể ghép file đầy đủ.")
        return

    with open(f"received_{filename}", "wb") as f:
        for i in range(1, num_chunks + 1):
            f.write(result_dict[i])

    print(f"✅ Đã tải xong song song file: received_{filename}")

def download_files_from_input(sock, idle_timeout=10):
    downloaded = set()
    idle_time = 0
    poll_interval = 2

    print(f"[CLIENT] Theo dõi input.txt. Dừng nếu không có file mới trong {idle_timeout} giây.")
    while True:
        try:
            with open("client/input.txt") as f:
                filenames = [line.strip() for line in f.readlines() if line.strip()]
        except:
            print("[CLIENT] ❌ Không thể đọc input.txt")
            time.sleep(poll_interval)
            idle_time += poll_interval
            if idle_time >= idle_timeout:
                print("[CLIENT] ⏹ Không có hoạt động. Dừng client.")
                break
            continue

        new_files = [fn for fn in filenames if fn not in downloaded]
        if new_files:
            idle_time = 0
            for filename in new_files:
                print(f"\n🚀 Bắt đầu tải file: {filename}")
                request_all_chunks_parallel(sock, filename)
                downloaded.add(filename)
        else:
            idle_time += poll_interval
            if idle_time >= idle_timeout:
                print(f"[CLIENT] ⏹ Không có file mới trong {idle_timeout} giây. Dừng client.")
                break

        time.sleep(poll_interval)

def main():
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.setblocking(False)

    request_file_list(sock)
    download_files_from_input(sock)

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n[CLIENT] 🛑 Kết thúc client.")
