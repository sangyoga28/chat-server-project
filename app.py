
import os
import socket
import threading
from datetime import datetime

from flask import Flask, render_template, request
from flask_socketio import SocketIO, emit

app = Flask(__name__)
app.config["SECRET_KEY"] = os.environ.get("SECRET_KEY", "dev-secret-change-this")

socketio = SocketIO(app, cors_allowed_origins="*", async_mode="threading")

TCP_HOST = "0.0.0.0"
TCP_PORT = int(os.environ.get("TCP_PORT", 8080))
WEB_PORT = int(os.environ.get("PORT", 5000))
ADMIN_PASSWORD = os.environ.get("ADMIN_PASSWORD", "admin123")

tcp_clients = {}
web_clients = {}
admin_clients = {}
clients_lock = threading.RLock()

logs = []
logs_lock = threading.Lock()


def get_time():
    return datetime.now().strftime("%H:%M:%S")


def add_log(message, event_type="info"):
    entry = {
        "time": get_time(),
        "message": message,
        "type": event_type
    }

    with logs_lock:
        logs.append(entry)
        if len(logs) > 200:
            logs.pop(0)

    print(f"[{entry['time']}] {message}")
    socketio.emit("new_log", entry)


def get_logs():
    with logs_lock:
        return list(logs[-50:])


def get_client_list():
    result = []

    with clients_lock:
        for client_id, data in tcp_clients.items():
            result.append({
                "id": client_id,
                "name": data["name"],
                "type": "TCP",
                "address": data["address"],
                "status": "Connected"
            })

        for client_id, data in web_clients.items():
            result.append({
                "id": client_id,
                "name": data["name"],
                "type": "WebSocket",
                "address": data["address"],
                "status": "Connected"
            })

    return result


def update_admins():
    clients = get_client_list()
    payload = {
        "clients": clients,
        "total": len(clients),
        "logs": get_logs()
    }

    with clients_lock:
        admin_ids = list(admin_clients.keys())

    for admin_id in admin_ids:
        socketio.emit("server_update", payload, to=admin_id)


def send_to_tcp(client_id, message):
    with clients_lock:
        client = tcp_clients.get(client_id)

    if not client:
        return

    try:
        client["socket"].sendall(message.encode("utf-8"))
    except OSError:
        remove_tcp_client(client_id)


def broadcast_message(message, sender_name, sender_id=None):
    payload = {
        "sender": sender_name,
        "message": message,
        "time": get_time()
    }

    formatted = (
        f"\n[{payload['time']}] {sender_name}: {message}\n"
    )

    with clients_lock:
        tcp_snapshot = list(tcp_clients.items())
        web_snapshot = list(web_clients.items())

    for client_id, client in tcp_snapshot:
        if client_id != sender_id:
            send_to_tcp(client_id, formatted)

    for client_id, client in web_snapshot:
        if client_id != sender_id:
            socketio.emit("chat_message", payload, to=client_id)

    add_log(f"Pesan dari {sender_name}: {message}", "message")
    update_admins()


def remove_tcp_client(client_id, notify=True):
    with clients_lock:
        client = tcp_clients.pop(client_id, None)

    if not client:
        return

    try:
        client["socket"].shutdown(socket.SHUT_RDWR)
    except OSError:
        pass

    try:
        client["socket"].close()
    except OSError:
        pass

    if notify:
        add_log(f"{client['name']} terputus dari TCP server", "disconnect")

    update_admins()


def disconnect_web_client(client_id, reason="Koneksi diputus oleh administrator."):
    with clients_lock:
        client = web_clients.get(client_id)

    if not client:
        return False

    # Beri pemberitahuan sebelum koneksi benar-benar ditutup.
    socketio.emit(
        "server_notice",
        {"message": reason},
        to=client_id
    )

    # Tutup koneksi Socket.IO secara nyata.
    socketio.server.disconnect(client_id, namespace="/")

    with clients_lock:
        web_clients.pop(client_id, None)

    add_log(f"{client['name']} diputus oleh administrator", "disconnect")
    update_admins()
    return True


def handle_tcp_client(conn, address):
    client_id = f"TCP-{address[0]}:{address[1]}"
    client_name = client_id

    with clients_lock:
        tcp_clients[client_id] = {
            "socket": conn,
            "name": client_name,
            "address": f"{address[0]}:{address[1]}"
        }

    add_log(f"{client_name} terhubung", "connect")
    update_admins()

    try:
        conn.sendall(
            b"Terhubung ke Chat Server. Ketik pesan dan tekan Enter.\n"
        )

        while True:
            data = conn.recv(4096)

            if not data:
                break

            message = data.decode("utf-8", errors="replace").strip()

            if message:
                broadcast_message(message, client_name, client_id)

    except (ConnectionResetError, OSError):
        pass
    finally:
        remove_tcp_client(client_id)


def tcp_server():
    server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)

    try:
        server.bind((TCP_HOST, TCP_PORT))
        server.listen()

        add_log(f"TCP server berjalan pada port {TCP_PORT}", "system")

        while True:
            conn, address = server.accept()

            thread = threading.Thread(
                target=handle_tcp_client,
                args=(conn, address),
                daemon=True
            )
            thread.start()

    except OSError as error:
        add_log(f"TCP server error: {error}", "error")
    finally:
        server.close()


@app.route("/")
def index():
    return render_template("index.html")


@socketio.on("connect")
def handle_connect(auth=None):
    auth = auth or {}
    role = auth.get("role", "client")

    if role == "admin":
        if auth.get("password") != ADMIN_PASSWORD:
            add_log("Percobaan login admin gagal", "warning")
            return False

        admin_id = request.sid

        with clients_lock:
            admin_clients[admin_id] = {"name": "Administrator"}

        add_log("Administrator masuk ke dashboard", "admin")
        emit("admin_authenticated", {"success": True})
        update_admins()
        return

    client_id = request.sid
    client_name = auth.get("name") or f"WebClient-{client_id[:6]}"

    address = request.remote_addr or "Unknown"
    peer_port = "N/A"

    try:
        ws = request.environ.get("werkzeug.socket")
        if ws:
            peer = ws.getpeername()
            address = peer[0]
            peer_port = peer[1]
    except (AttributeError, OSError, TypeError):
        pass

    with clients_lock:
        web_clients[client_id] = {
            "name": client_name,
            "address": f"{address}:{peer_port}"
        }

    add_log(
        f"{client_name} terhubung melalui WebSocket ({address}:{peer_port})",
        "connect"
    )

    emit("client_authenticated", {"success": True, "id": client_id})
    update_admins()


@socketio.on("disconnect")
def handle_disconnect(reason=None):
    client_id = request.sid

    with clients_lock:
        client = web_clients.pop(client_id, None)
        admin = admin_clients.pop(client_id, None)

    if client:
        add_log(f"{client['name']} terputus", "disconnect")
        update_admins()

    if admin:
        add_log("Administrator keluar dari dashboard", "admin")
        update_admins()


@socketio.on("send_message")
def handle_send_message(data):
    client_id = request.sid

    with clients_lock:
        client = web_clients.get(client_id)

    # Client yang sudah tidak terdaftar tidak boleh mengirim pesan.
    if not client:
        return

    message = str((data or {}).get("message", "")).strip()[:2000]

    if not message:
        return

    payload = {
        "sender": client["name"],
        "message": message,
        "time": get_time()
    }

    # Tampilkan pesan kepada pengirim.
    socketio.emit("chat_message", payload, to=client_id)

    # Broadcast ke client lain.
    broadcast_message(message, client["name"], client_id)


@socketio.on("admin_broadcast")
def handle_admin_broadcast(data):
    admin_id = request.sid

    with clients_lock:
        if admin_id not in admin_clients:
            return

    message = str((data or {}).get("message", "")).strip()[:2000]

    if not message:
        return

    payload = {
        "sender": "ADMIN",
        "message": message,
        "time": get_time()
    }

    with clients_lock:
        tcp_snapshot = list(tcp_clients.items())
        web_snapshot = list(web_clients.items())

    for client_id, client in tcp_snapshot:
        send_to_tcp(
            client_id,
            f"\n[{payload['time']}] ADMIN: {message}\n"
        )

    for client_id, client in web_snapshot:
        socketio.emit("chat_message", payload, to=client_id)

    add_log(f"Admin melakukan broadcast: {message}", "admin")
    update_admins()


@socketio.on("admin_disconnect_client")
def handle_admin_disconnect_client(data):
    admin_id = request.sid

    with clients_lock:
        if admin_id not in admin_clients:
            return

    client_id = (data or {}).get("id")

    with clients_lock:
        is_tcp = client_id in tcp_clients
        is_web = client_id in web_clients

    if is_tcp:
        remove_tcp_client(client_id)
    elif is_web:
        disconnect_web_client(client_id)


if __name__ == "__main__":
    tcp_thread = threading.Thread(target=tcp_server, daemon=True)
    tcp_thread.start()

    add_log("Web server sedang dimulai", "system")

    socketio.run(
        app,
        host="0.0.0.0",
        port=WEB_PORT,
        debug=False,
        allow_unsafe_werkzeug=True
    )
