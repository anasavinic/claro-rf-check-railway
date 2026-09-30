import os
import subprocess
import sys

from invoke import task

from tasks.config import CODE_DIR, COMPOSE, CONTAINER_NAME
from tasks.database import restore
from tasks.django import migrate


@task
def down(c, volumes=False):
    """Stop and remove the local Docker stack

    :param c: The Invoke context, which is used to run the command.
    """
    _stop_tailwind_on_host()
    cmd = f"{COMPOSE} down {' -v' if volumes else ''}"
    c.run(cmd)


def _stop_tailwind_on_host():
    """Kill detached host Tailwind/postcss watchers left behind by disown."""
    print("Stopping leftover host Tailwind watchers (if any)")
    if sys.platform == "win32":
        ps = (
            "$ErrorActionPreference = 'SilentlyContinue'; "
            "Get-CimInstance Win32_Process | Where-Object { "
            "  $_.CommandLine -and ( "
            "    $_.CommandLine -match 'manage\\.py tailwind start' -or "
            "    $_.CommandLine -match 'static[/\\\\]css[/\\\\]dist[/\\\\]styles\\.css' "
            "  ) "
            "} | ForEach-Object { taskkill /F /T /PID $_.ProcessId | Out-Null }"
        )
        subprocess.run(
            ["powershell", "-NoProfile", "-Command", ps],
            check=False,
            capture_output=True,
        )
        return
    subprocess.run(
        "pkill -f 'manage.py tailwind start' || true; pkill -f 'static/css/dist/styles.css' || true",
        shell=True,
        check=False,
    )


def _start_tailwind_on_host(c):
    """Watch CSS on the host. Docker bind mounts on Windows/WSL delay inotify by many seconds."""
    _stop_tailwind_on_host()
    check = c.run(
        f'"{sys.executable}" -c "import django"',
        warn=True,
        hide=True,
    )
    if not check.ok:
        print(
            "WARNING: Django is not importable from the current Python "
            f"({sys.executable}). Activate the project venv before "
            "`inv docker.run`, or use `--no-tailwind`."
        )
        return

    print("Starting Tailwind watcher on the host (manage.py tailwind start)")
    cmd = f'"{sys.executable}" manage.py tailwind start'
    with c.cd(CODE_DIR):
        if sys.platform == "win32":
            c.run(cmd, pty=False, disown=True, env=dict(os.environ))
        else:
            c.run(f"{cmd} &", disown=True, env=dict(os.environ))


@task(pre=[down])
def run(
    c,
    daemon: bool = False,
    debug: bool = False,
    debug_vscode: bool = False,
    celery: bool = False,
    no_tailwind: bool = False,
) -> None:
    """Run the local Docker stack

    :param c: The Invoke context, which is used to run the command.
    :param daemon: If True, runs the stack in detached mode.
    :param debug: If True, enables PyCharm remote debugging.
    :param debug_vscode: If True, enables VSCode remote debugging.
    :param celery: If True, enables Celery debugging.
    :param no_tailwind: If True, don't start tailwind server
    """
    if debug_vscode:
        os.environ["DEBUG_VSCODE"] = "1"
    elif debug or celery:
        os.environ["DEBUG_PYCHARM"] = "1"
    if celery:
        os.environ["DEBUG_CELERY"] = "1"

    cmd = f"{COMPOSE} up --remove-orphans {'-d' if daemon else ''}"

    if not no_tailwind:
        _start_tailwind_on_host(c)

    c.run(cmd, pty=(sys.platform != "win32"))


@task
def build(c, daemon=False, up=False):
    """Build the local Docker stack

    :param c: The Invoke context, which is used to run the command.
    :param daemon: If True, runs the stack in detached mode.
    :param up: If True, runs `docker-compose up --build` to build and start the stack.
    """
    cmd = f"{COMPOSE} build{' -q' if daemon else ''}"
    c.run(cmd)

    if up:
        run(c, daemon=daemon)


@task
def kill(c):
    """Kill the local Docker stack

    :param c: The Invoke context, which is used to run the command.
    """
    cmd = f"{COMPOSE} kill"
    c.run(cmd)
    _stop_tailwind_on_host()


@task()
def fresh_restart(c, ignore_system_prune=True, backup_file=None):
    """Kill, remove, rebuild, and restart the local Docker stack, and restore the database from a backup.

    :param c: The Invoke context, which is used to run the command.
    :param ignore_system_prune: If False, runs `docker system prune` to clean up unused Docker data
    (affect all Docker data, use with caution).
    :param backup_file: The name of the backup file to restore from (must be inside the `backups` directory).
    """
    print("Stopping existing containers...")
    kill(c)

    if not ignore_system_prune:
        print("Cleaning up unused Docker data...")
        c.run("docker system prune -f")
    else:
        print("Removing Docker containers, images, volumes and networks...")
        c.run(f"{COMPOSE} down --rmi all -v")

    print("Rebuilding the Docker stack...")
    build(c, daemon=True, up=True)

    print("Running Django migrations...")
    migrate(c)

    if backup_file:
        restore(c, backup_file)
    else:
        print("No backup file provided. Skipping database restore.")

    print("Restarting the stack...")
    kill(c)

    print("Fresh restart completed.")


@task
def celery_status(c):
    """Check the status of the Celery worker inside the container

    :param c: The Invoke context, which is used to run the command.
    """
    cmd = f"docker exec claro_rf_check_celery celery -A {CONTAINER_NAME} status"
    c.run(cmd)
