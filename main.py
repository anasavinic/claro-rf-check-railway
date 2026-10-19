"""Desktop entrypoint. Opens a local window, like Vivo RF Check."""

import os
import socket
import sys
import threading
import time
from pathlib import Path


def _root() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys._MEIPASS)
    return Path(__file__).resolve().parent


ROOT = _root()
CODE = ROOT if getattr(sys, "frozen", False) else ROOT / "code"
if str(CODE) not in sys.path:
    sys.path.insert(0, str(CODE))

# Force desktop settings. setdefault would keep a dev/Postgres config if the
# machine already has DJANGO_SETTINGS_MODULE, and the server would never listen.
os.environ["DJANGO_SETTINGS_MODULE"] = "claro_rf_check.settings.desktop"
os.environ.setdefault("SECRET_KEY", "claro-rf-check-desktop")
os.environ["CELERY_BROKER_URL"] = "memory://"
os.environ["CELERY_RESULT_BACKEND"] = "cache+memory://"


def _log_dir() -> Path:
    base = Path(os.environ.get("LOCALAPPDATA") or Path.home())
    folder = base / "Claro RF Check" / "logs"
    folder.mkdir(parents=True, exist_ok=True)
    return folder


def _capture_frozen_output() -> None:
    if not getattr(sys, "frozen", False):
        return
    handle = open(_log_dir() / "app.log", "a", encoding="utf-8", buffering=1)
    sys.stdout = handle
    sys.stderr = handle


_log_lock = threading.Lock()
_server_error: list[str] = []


def _startup_log(message: str) -> None:
    line = f"{time.strftime('%Y-%m-%d %H:%M:%S')} {message}\n"
    try:
        with _log_lock:
            with open(_log_dir() / "startup.log", "a", encoding="utf-8") as handle:
                handle.write(line)
    except OSError:
        return


def _startup_log_tail() -> str:
    try:
        text = (_log_dir() / "startup.log").read_text(encoding="utf-8")
    except OSError:
        return ""
    return "\n".join(text.splitlines()[-40:])


def _bound_loopback_socket() -> socket.socket:
    """Bind 127.0.0.1 once and keep the socket.

    The previous approach asked Windows for port 0, closed that socket, and
    bound the same port again. On PCs with Hyper-V, WSL, or Docker the second
    bind fails: those features reserve blocks of high ports, and closing the
    first socket gives the port back to that reserved range (WinError 10013).
    """
    last_error: OSError | None = None
    for port in range(17640, 17740):
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        try:
            sock.bind(("127.0.0.1", port))
        except OSError as exc:
            last_error = exc
            sock.close()
            continue
        return sock
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        sock.bind(("127.0.0.1", 0))
    except OSError as exc:
        sock.close()
        detail = last_error or exc
        raise RuntimeError(
            "Nao foi possivel reservar uma porta em 127.0.0.1. "
            "Libere o ClaroRFCheck no antivirus e no firewall do Windows. "
            f"Ultimo erro: {detail}"
        ) from exc
    return sock


def _patch_waitress_trigger() -> None:
    """The Windows wake-up socket inside waitress uses the same port-0 bind."""
    if os.name == "posix":
        return
    import errno

    from waitress.trigger import trigger

    original = trigger.__init__

    def resilient_init(self, map):
        last_error: OSError | None = None
        for _ in range(30):
            try:
                return original(self, map)
            except OSError as exc:
                last_error = exc
                if getattr(exc, "winerror", None) not in {errno.WSAEADDRINUSE, errno.WSAEACCES}:
                    raise
        raise RuntimeError(
            f"O Windows bloqueou a porta interna do servidor local (Hyper-V, WSL ou Docker). Erro: {last_error}"
        )

    trigger.__init__ = resilient_init


def _wait_until_open(port: int) -> None:
    deadline = time.time() + 180
    while time.time() < deadline:
        if _server_error:
            raise RuntimeError(_server_error[0])
        with socket.socket() as probe:
            probe.settimeout(0.3)
            if probe.connect_ex(("127.0.0.1", port)) == 0:
                return
        time.sleep(0.1)
    if _server_error:
        raise RuntimeError(_server_error[0])
    log_path = _log_dir() / "startup.log"
    tail = _startup_log_tail()
    message = (
        f"O servidor local nao respondeu em 127.0.0.1:{port}. "
        "Na primeira abertura o antivirus pode segurar o programa por mais de um minuto; "
        "se continuar, libere o ClaroRFCheck no antivirus e no firewall. "
        f"Log: {log_path}"
    )
    if tail:
        message = f"{message}\n\n{tail}"
    raise RuntimeError(message)


def _serve(sock: socket.socket) -> None:
    import traceback

    _startup_log("thread do servidor iniciou")
    try:
        _startup_log("carregando o Django")
        import django
        from django.core.management import call_command
        from waitress import serve

        _patch_waitress_trigger()
        django.setup()
        _startup_log("aplicando migracoes")
        call_command("migrate", interactive=False, verbosity=1)
        _startup_log("usuario local")
        call_command("ensure_desktop_user")
        from claro_rf_check.wsgi import application

        port = sock.getsockname()[1]
        _startup_log(f"escutando em 127.0.0.1:{port}")
        serve(application, sockets=[sock], threads=8)
    except Exception:
        _server_error.append(traceback.format_exc())
        _startup_log(_server_error[0])
        raise


def main() -> None:
    _capture_frozen_output()
    _startup_log("abrindo o programa")
    import webview

    # The window is Edge WebView2. It ignores blob downloads from script, and
    # pywebview cancels every other download unless this is turned on. Report
    # and email links then open the normal Save dialog.
    webview.settings["ALLOW_DOWNLOADS"] = True

    sock = _bound_loopback_socket()
    port = sock.getsockname()[1]
    _startup_log(f"porta reservada {port}")
    threading.Thread(target=_serve, args=(sock,), name="claro-rf-server", daemon=True).start()
    _wait_until_open(port)
    webview.create_window(
        "CLARO RF CHECK",
        f"http://127.0.0.1:{port}/",
        min_size=(1240, 600),
        maximized=True,
        text_select=True,
    )
    webview.start()
    os._exit(0)


if __name__ == "__main__":
    main()
