
import socket
import threading

HOST = "127.0.0.1"
PORT = 8080


def receive_messages(client):
    """Menerima pesan dari server secara bersamaan."""
    try:
        buffer = ""

        while True:
            data = client.recv(4096)

            if not data:
                print("\n[INFO] Koneksi ke server terputus.")
                break

            buffer += data.decode("utf-8", errors="replace")

            while "\n" in buffer:
                message, buffer = buffer.split("\n", 1)
                print(f"\n{message}")

    except OSError:
        pass


def start_client():
    client = socket.socket(socket.AF_INET, socket.SOCK_STREAM)

    try:
        client.connect((HOST, PORT))

        print("=" * 40)
        print("       TCP CHAT CLIENT")
        print("=" * 40)
        print(f"[CONNECTED] Server: {HOST}:{PORT}")
        print("[INFO] Ketik pesan untuk mengirim.")
        print("[INFO] Tekan Ctrl+C untuk keluar.")
        print("=" * 40)

        receiver = threading.Thread(
            target=receive_messages,
            args=(client,),
            daemon=True
        )
        receiver.start()

        while True:
            message = input("Pesan: ")

            if not message.strip():
                continue

            client.sendall((message + "\n").encode("utf-8"))

    except KeyboardInterrupt:
        print("\n[INFO] Client sedang keluar...")

    except ConnectionRefusedError:
        print("[ERROR] Server belum berjalan.")

    except OSError as error:
        print(f"[ERROR] {error}")

    finally:
        try:
            client.shutdown(socket.SHUT_RDWR)
        except OSError:
            pass

        client.close()
        print("[DISCONNECTED] Client ditutup.")


if __name__ == "__main__":
    start_client()
