
import socket
import threading
import os

# Konfigurasi server
HOST = "127.0.0.1"
PORT = int(os.environ.get("PORT", 8080))

# Connection Pool
clients = {}
clients_lock = threading.Lock()


def log(message):
    print(message, flush=True)


def broadcast(message, sender=None):
    """Mengirim pesan ke semua client kecuali pengirim."""
    with clients_lock:
        recipients = [
            (client, info)
            for client, info in clients.items()
            if client != sender
        ]

    for client, info in recipients:
        try:
            with info["send_lock"]:
                client.sendall((message + "\n").encode("utf-8"))
        except OSError:
            disconnect_client(client)


def disconnect_client(client):
    """Menghapus client dan memberi notifikasi kepada client lain."""
    with clients_lock:
        info = clients.pop(client, None)

    # Jika sudah dihapus oleh thread lain, abaikan.
    if info is None:
        return

    ip, port = info["address"]

    log(f"[DISCONNECTED] Klien {ip}:{port} memutuskan koneksi")

    try:
        client.shutdown(socket.SHUT_RDWR)
    except OSError:
        pass

    client.close()

    notification = (
        f"*** SISTEM: Klien {ip}:{port} telah meninggalkan obrolan ***"
    )

    broadcast(notification)


def handle_client(client, address):
    ip, port = address
    buffer = ""

    log(f"[CONNECTED] Klien terhubung dari {ip}:{port}")

    try:
        while True:
            data = client.recv(4096)

            if not data:
                break

            buffer += data.decode("utf-8", errors="replace")

            # Memisahkan pesan berdasarkan newline
            while "\n" in buffer:
                message, buffer = buffer.split("\n", 1)
                message = message.rstrip("\r")

                if not message:
                    continue

                log(f"[MESSAGE] Dari {ip}:{port}: {message}")

                formatted_message = f"[{ip}:{port}]: {message}"

                # Broadcast ke client lainnya
                broadcast(formatted_message, sender=client)

    except (ConnectionError, OSError) as error:
        log(f"[INFO] Koneksi {ip}:{port} berakhir: {error}")

    finally:
        disconnect_client(client)


def start_server():
    server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)

    server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)

    try:
        server.bind((HOST, PORT))
        server.listen()

        log("=" * 50)
        log("       TCP CHAT SERVER")
        log("=" * 50)
        log(f"[RUNNING] Server berjalan di {HOST}:{PORT}")
        log("[INFO] Menunggu koneksi client...")
        log("=" * 50)

        while True:
            client, address = server.accept()

            info = {
                "address": address,
                "send_lock": threading.Lock()
            }

            with clients_lock:
                clients[client] = info

            # Setiap client ditangani oleh thread terpisah
            thread = threading.Thread(
                target=handle_client,
                args=(client, address),
                daemon=True
            )
            thread.start()

    except KeyboardInterrupt:
        log("\n[STOPPING] Server sedang dimatikan...")

    finally:
        server.close()

        with clients_lock:
            active_clients = list(clients.keys())

        for client in active_clients:
            disconnect_client(client)

        log("[STOPPED] Server berhasil dihentikan.")


if __name__ == "__main__":
    start_server()
