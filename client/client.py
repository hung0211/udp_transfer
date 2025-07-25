import socket, json, os, select
from shared.config import SERVER_IP, SERVER_PORT, CHUNK_SIZE, TIMEOUT, MAX_RETRIES
import threading
import hashlib
import base64

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
    rlist, _, _ = select.select([sock], [], [], 2)
    if rlist:
        data, _ = sock.recvfrom(4096)
        try:
            return int(data.decode())
        except:
            return None
    return None

def request_chunk_async(sock, filename, index, offset, length, result_dict, lock, num_chunks, retries=0):
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
            data, _ = sock.recvfrom(4096)
            if data == b"__END__":
                print(f"[CLIENT] ✅ Chunk {index} nhận xong (EOF)")
                return

            part_file = f"{filename}.part{index}"
            with open(part_file, "wb") as f:
                f.write(data)

            with lock:
                result_dict[index] = part_file
                completed = len(result_dict)
                percent = (completed / num_chunks) * 100
                print(f"[CLIENT] 🟡 Tiến độ: {completed}/{num_chunks} chunks ({percent:.2f}%)")

            print(f"[CLIENT] ✅ Chunk {index} nhận thành công ({len(data)} bytes)")
        except Exception as e:
            print(f"[CLIENT] ❌ Lỗi khi nhận chunk {index}: {e}")
    else:
        if retries < MAX_RETRIES:
            print(f"[CLIENT] ⚠️ Chunk {index} timeout, thử lại ({retries + 1})...")
            request_chunk_async(sock, filename, index, offset, length, result_dict, lock, num_chunks, retries + 1)
        else:
            print(f"[CLIENT] ❌ Chunk {index} thất bại sau {MAX_RETRIES} lần thử.")

def request_all_chunks_parallel(sock, filename):
    filesize = get_file_size(sock, filename)
    if filesize is None:
        print("❌ Không thể lấy kích thước file.")
        return

    num_chunks = (filesize + CHUNK_SIZE - 1) // CHUNK_SIZE
    result_dict = {}
    threads = []
    lock = threading.Lock()

    for i in range(num_chunks):
        offset = i * CHUNK_SIZE
        t = threading.Thread(target=request_chunk_async, args=(sock, filename, i + 1, offset, CHUNK_SIZE, result_dict, lock, num_chunks))
        t.start()
        threads.append(t)

    for t in threads:
        t.join()

    with open(f"received_{filename}", "wb") as f:
        for i in range(1, num_chunks + 1):
            part_file = result_dict.get(i)
            if part_file:
                with open(part_file, "rb") as pf:
                    f.write(pf.read())
            else:
                print(f"❌ Thiếu chunk {i}, không thể ghép file đầy đủ.")
                return

    print(f"✅ Đã tải xong song song file: received_{filename}")

def request_chunk_with_retry(sock, filename, offset, length, retries=3):
    for attempt in range(1, retries + 1):
        req = {
            "type": "GET_CHUNK",
            "filename": filename,
            "offset": offset,
            "length": length
        }
        sock.sendto(json.dumps(req).encode(), (SERVER_IP, SERVER_PORT))
        rlist, _, _ = select.select([sock], [], [], 2)

        if not rlist:
            print(f"⚠️ [Retry {attempt}/{retries}] Timeout khi nhận phản hồi từ server (offset={offset})")
            continue

        try:
            data, _ = sock.recvfrom(4096)
            packet = json.loads(data.decode())
            chunk_data = base64.b64decode(packet["data"])
            checksum = packet["checksum"]

            if hashlib.sha256(chunk_data).hexdigest() == checksum:
                return chunk_data
            else:
                print(f"⚠️ [Retry {attempt}/{retries}] Checksum không khớp, thử lại (offset={offset})")
        except Exception as e:
            print(f"⚠️ [Retry {attempt}/{retries}] Lỗi xử lý dữ liệu: {e}")
            continue

    print(f"❌ Không thể nhận chunk tại offset {offset} sau {retries} lần.")
    return None

def download_chunk_threaded(sock, filename, offset, length, part_file, status_dict, index):
    chunk_data = request_chunk_with_retry(sock, filename, offset, length)
    if chunk_data:
        with open(part_file, "wb") as f:
            f.write(chunk_data)
        print(f"✅ [Chunk {index}] Ghi vào {part_file}")
        status_dict[index] = True
    else:
        print(f"❌ [Chunk {index}] Thất bại.")
        status_dict[index] = False

def request_all_chunks(sock, filename):
    file_size = get_file_size(sock, filename)
    if not file_size:
        print("❌ Không thể lấy kích thước file.")
        return

    num_chunks = (file_size + CHUNK_SIZE - 1) // CHUNK_SIZE
    threads = []
    status = {}
    chunk_files = []

    for i in range(num_chunks):
        offset = i * CHUNK_SIZE
        part_file = f"{filename}.part{i + 1}"
        chunk_files.append(part_file)
        t = threading.Thread(target=download_chunk_threaded,
                             args=(sock, filename, offset, CHUNK_SIZE, part_file, status, i + 1))
        threads.append(t)
        t.start()

    for t in threads:
        t.join()

    if all(status.get(i + 1) for i in range(num_chunks)):
        with open(f"received_{filename}", "wb") as f:
            for pf in chunk_files:
                with open(pf, "rb") as part:
                    f.write(part.read())
        print(f"📦 File đã ghép thành công: received_{filename}")
    else:
        print("❌ Một số chunk bị lỗi. Không thể ghép file.")

def download_files_from_input(sock):
    try:
        with open("client/input.txt") as f:
            filenames = [line.strip() for line in f.readlines() if line.strip()]
    except:
        print("[CLIENT] ❌ Không thể đọc input.txt")
        return
    for filename in filenames:
        print(f"\n🚀 Bắt đầu tải file song song: {filename}")
        request_all_chunks_parallel(sock, filename)

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
