"""Credential-free protocol probes with bounded socket I/O for a selected proxy."""

from __future__ import annotations

import ipaddress
import socket
import ssl
from typing import Any


PROBE_TIMEOUT_SECONDS = 3.0
MAX_STATUS_LINE_BYTES = 512


def _read_status_line(connection: socket.socket) -> bytes:
    data = bytearray()
    while len(data) < MAX_STATUS_LINE_BYTES:
        chunk = connection.recv(min(128, MAX_STATUS_LINE_BYTES - len(data)))
        if not chunk:
            break
        data.extend(chunk)
        if b"\r\n" in data:
            return bytes(data.split(b"\r\n", 1)[0])
    raise EOFError("invalid_or_missing_status_line")


def _recv_exact(connection: socket.socket, length: int) -> bytes:
    data = bytearray()
    while len(data) < length:
        chunk = connection.recv(length - len(data))
        if not chunk:
            break
        data.extend(chunk)
    return bytes(data)


def _normalized_host(value: str) -> str | None:
    host = value.strip()
    if not host or "%" in host or any(ord(char) < 32 or ord(char) == 127 for char in host):
        return None
    if host.startswith("[") and host.endswith("]"):
        host = host[1:-1]
    try:
        return str(ipaddress.ip_address(host))
    except ValueError:
        pass
    if any(char in host for char in "/\\@?#[]:"):
        return None
    try:
        ascii_host = host.encode("idna").decode("ascii").rstrip(".").lower()
    except UnicodeError:
        return None
    labels = ascii_host.split(".")
    if (len(ascii_host) > 253 or
            any(not label or len(label) > 63 or label.startswith("-") or label.endswith("-") or
                not all(char.isascii() and (char.isalnum() or char == "-") for char in label)
                for label in labels)):
        return None
    return ascii_host


def diagnose_proxy(proxy: dict[str, Any]) -> tuple[bool, str]:
    """Check TCP and perform a no-auth service handshake; never check forwarding.

    The selected endpoint is contacted only after a user starts the check. Hostname
    resolution uses the OS resolver. No stored credential is read, no URL/site is
    contacted, and the result must not be presented as proof that browsing works.
    """
    scheme = str(proxy.get("scheme", "")).lower()
    host = _normalized_host(str(proxy.get("host", "")))
    try:
        port = int(proxy.get("port", 0))
    except (TypeError, ValueError):
        return False, "Проверка остановлена: неверный порт proxy."
    if scheme not in {"http", "https", "socks5"} or not host or not 1 <= port <= 65535:
        return False, "Проверка остановлена: неверные параметры proxy."

    tcp_connected = False
    try:
        with socket.create_connection((host, port), timeout=PROBE_TIMEOUT_SECONDS) as raw:
            tcp_connected = True
            raw.settimeout(PROBE_TIMEOUT_SECONDS)
            if scheme == "socks5":
                # Offer only no-auth (RFC 1928 method 0x00). Never offer username/password.
                raw.sendall(b"\x05\x01\x00")
                reply = _recv_exact(raw, 2)
                if len(reply) != 2 or reply[0] != 5:
                    return False, "TCP доступен, но корректный ответ SOCKS5 не получен."
                if reply[1] == 0:
                    return True, "Ответ SOCKS5 получен; выбран режим без авторизации. Маршрут до сайта не проверялся."
                if reply[1] == 2:
                    return False, "SOCKS5 требует авторизацию; логин и пароль не отправлялись. Chromium SOCKS5-аутентификацию не поддерживает."
                if reply[1] == 255:
                    return False, "SOCKS5 не принимает режим без авторизации; учётные данные не отправлялись."
                return False, "Получен неподдерживаемый ответ SOCKS5; учётные данные не отправлялись."

            connection: socket.socket = raw
            if scheme == "https":
                context = ssl.create_default_context()
                # Keep normal CA and hostname validation enabled; never ignore TLS errors.
                connection = context.wrap_socket(raw, server_hostname=host)

            with connection:
                # OPTIONS * probes only whether an HTTP endpoint responds. It does
                # not request a tunnel, contact a destination, or include credentials.
                host_authority = f"[{host}]" if ":" in host else host
                request = (
                    f"OPTIONS * HTTP/1.1\r\nHost: {host_authority}:{port}\r\n"
                    "Connection: close\r\n\r\n"
                ).encode("ascii")
                connection.sendall(request)
                status_line = _read_status_line(connection)
                fields = status_line.split(None, 2)
                if len(fields) < 2 or fields[0] not in {b"HTTP/1.0", b"HTTP/1.1"} or not fields[1].isdigit():
                    return False, "TCP доступен, но корректный HTTP-ответ proxy не получен."
                status_code = int(fields[1])
                if status_code == 407:
                    tls_note = " TLS-сертификат проверен." if scheme == "https" else ""
                    return False, f"HTTP proxy требует авторизацию; сохранённые данные не отправлялись.{tls_note}"
                if status_code == 401:
                    tls_note = " TLS-сертификат проверен." if scheme == "https" else ""
                    return False, f"Получен HTTP 401, а не стандартный proxy challenge 407.{tls_note} Учётные данные не отправлялись."
                tls_note = " TLS-сертификат проверен." if scheme == "https" else ""
                if status_code >= 400:
                    return False, (
                        f"HTTP endpoint ответил кодом {status_code} на OPTIONS *.{tls_note} "
                        "Проба отклонена; поддержку CONNECT она не проверяла."
                    )
                return True, (
                    f"HTTP-ответ получен (код {status_code}).{tls_note} "
                    "Поддержка CONNECT и маршрут до сайта не проверялись."
                )
    except ssl.SSLCertVerificationError:
        return False, "TLS-сертификат HTTPS proxy не прошёл проверку."
    except ssl.SSLError:
        return False, "TLS-соединение с HTTPS proxy не установлено."
    except EOFError:
        return False, "TCP доступен, но корректный ответ proxy не получен."
    except TimeoutError:
        if tcp_connected:
            return False, "TCP доступен, но proxy не ответил на протокольную пробу за отведённое время."
        return False, "TCP-подключение к proxy не установлено за отведённое время."
    except OSError as exc:
        # Use only a stable, non-sensitive class marker; don't log the endpoint or OS text.
        if tcp_connected:
            return False, "TCP доступен, но proxy прервал протокольный обмен."
        if isinstance(exc, ConnectionRefusedError):
            return False, "TCP-подключение отклонено proxy."
        return False, "Не удалось установить TCP-соединение с proxy."
