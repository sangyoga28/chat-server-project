
let adminSocket = null;
let clientNumber = 0;
const clientSockets = new Map();

const loginScreen = document.getElementById("loginScreen");
const dashboard = document.getElementById("dashboard");
const loginError = document.getElementById("loginError");


function addLog(entry) {
    const container = document.getElementById("activityLogs");
    const empty = container.querySelector(".empty");

    if (empty) empty.remove();

    const item = document.createElement("div");
    item.className = `log-entry ${entry.type || ""}`;

    const time = document.createElement("span");
    time.textContent = `[${entry.time}]`;

    const message = document.createElement("span");
    message.textContent = entry.message;

    item.append(time, message);
    container.prepend(item);
}


function login() {
    const password = document.getElementById("adminPassword").value.trim();

    if (!password) {
        loginError.textContent = "Password harus diisi.";
        return;
    }

    if (adminSocket) {
        adminSocket.disconnect();
    }

    loginError.textContent = "Menghubungkan...";

    adminSocket = io({
        auth: {
            role: "admin",
            password: password
        },
        reconnection: false
    });

    adminSocket.on("admin_authenticated", () => {
        loginError.textContent = "";
        loginScreen.classList.add("hidden");
        dashboard.classList.remove("hidden");
    });

    adminSocket.on("connect_error", () => {
        loginError.textContent = "Login gagal. Periksa password admin.";
        adminSocket.disconnect();
        adminSocket = null;
    });

    adminSocket.on("server_update", updateDashboard);
    adminSocket.on("new_log", addLog);

    adminSocket.on("disconnect", () => {
        dashboard.classList.add("hidden");
        loginScreen.classList.remove("hidden");
    });
}


function updateDashboard(data) {
    const clients = data.clients || [];

    document.getElementById("totalClients").textContent = clients.length;

    document.getElementById("tcpCount").textContent =
        clients.filter(client => client.type === "TCP").length;

    document.getElementById("webCount").textContent =
        clients.filter(client => client.type === "WebSocket").length;

    document.getElementById("connectionCounter").textContent =
        `${clients.length} CLIENTS`;

    const table = document.getElementById("clientTable");
    table.replaceChildren();

    if (clients.length === 0) {
        const row = document.createElement("tr");
        const cell = document.createElement("td");

        cell.colSpan = 6;
        cell.className = "empty";
        cell.textContent = "Belum ada client terhubung.";

        row.appendChild(cell);
        table.appendChild(row);
        return;
    }

    clients.forEach(client => {
        const row = document.createElement("tr");

        [
            client.id,
            client.name,
            client.type,
            client.address,
            client.status
        ].forEach(value => {
            const cell = document.createElement("td");
            cell.textContent = value;
            row.appendChild(cell);
        });

        const actionCell = document.createElement("td");
        const button = document.createElement("button");

        button.textContent = "Disconnect";
        button.className = "danger-button";

        button.addEventListener("click", () => {
            if (!adminSocket?.connected) return;

            button.disabled = true;
            button.textContent = "Memutus...";

            adminSocket.emit("admin_disconnect_client", {
                id: client.id
            });
        });

        actionCell.appendChild(button);
        row.appendChild(actionCell);
        table.appendChild(row);
    });
}


function addClient() {
    if (!adminSocket?.connected) {
        alert("Admin belum terhubung ke server.");
        return;
    }

    clientNumber++;

    const name = `Browser-Client-${clientNumber}`;

    const socket = io({
        autoConnect: false,
        auth: {
            role: "client",
            name: name
        }
    });

    const panel = document.createElement("div");
    panel.className = "client-card";

    const heading = document.createElement("div");
    heading.className = "client-heading";

    const title = document.createElement("strong");
    title.textContent = name;

    const status = document.createElement("span");
    status.className = "client-status";
    status.textContent = "Connecting...";

    heading.append(title, status);

    const messages = document.createElement("div");
    messages.className = "client-messages";
    messages.textContent = "Menghubungkan ke server...";

    const form = document.createElement("form");
    form.className = "client-form";

    const input = document.createElement("input");
    input.placeholder = "Ketik pesan...";
    input.maxLength = 2000;

    const sendButton = document.createElement("button");
    sendButton.textContent = "Kirim";

    form.append(input, sendButton);
    panel.append(heading, messages, form);

    document.getElementById("clientPanels").appendChild(panel);

    function showMessage(data) {
        if (messages.textContent === "Menghubungkan ke server...") {
            messages.textContent = "";
        }

        const line = document.createElement("p");
        line.textContent =
            `[${data.time}] ${data.sender}: ${data.message}`;

        messages.appendChild(line);
        messages.scrollTop = messages.scrollHeight;
    }

    function setDisconnected(reason) {
        status.textContent = "Disconnected";
        status.classList.remove("connected");
        status.classList.add("disconnected");

        input.disabled = true;
        sendButton.disabled = true;

        if (reason) {
            showMessage({
                time: new Date().toLocaleTimeString(),
                sender: "SERVER",
                message: reason
            });
        }

        socket.disconnect();
    }

    socket.on("connect", () => {
        status.textContent = "Connected";
        status.classList.add("connected");
        status.classList.remove("disconnected");
        messages.textContent = "Terhubung. Siap mengirim pesan.";
    });

    socket.on("connect_error", () => {
        setDisconnected("Gagal terhubung ke server.");
    });

    socket.on("client_authenticated", () => {
        status.textContent = "Connected";
    });

    socket.on("chat_message", showMessage);

    socket.on("server_notice", data => {
        setDisconnected(data.message || "Koneksi diputus oleh server.");
    });

    socket.on("disconnect", () => {
        status.textContent = "Disconnected";
        status.classList.remove("connected");
        status.classList.add("disconnected");

        input.disabled = true;
        sendButton.disabled = true;
    });

    form.addEventListener("submit", event => {
        event.preventDefault();

        const message = input.value.trim();

        if (!message || !socket.connected) return;

        socket.emit("send_message", { message });
        input.value = "";
    });

    clientSockets.set(name, socket);
    socket.connect();
}


document.getElementById("loginButton").addEventListener("click", login);

document.getElementById("adminPassword").addEventListener("keydown", event => {
    if (event.key === "Enter") login();
});


document.getElementById("addClientButton").addEventListener("click", addClient);


document.getElementById("broadcastForm").addEventListener("submit", event => {
    event.preventDefault();

    const input = document.getElementById("broadcastInput");
    const message = input.value.trim();

    if (!message || !adminSocket?.connected) return;

    adminSocket.emit("admin_broadcast", { message });
    input.value = "";
});


document.getElementById("logoutButton").addEventListener("click", () => {
    clientSockets.forEach(socket => socket.disconnect());
    clientSockets.clear();

    if (adminSocket) {
        adminSocket.disconnect();
        adminSocket = null;
    }

    dashboard.classList.add("hidden");
    loginScreen.classList.remove("hidden");
});
