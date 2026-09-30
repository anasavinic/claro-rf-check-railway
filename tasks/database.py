import os
from datetime import datetime

from invoke import task

from tasks.config import BACKUP_DIR, DB_CONTAINER, DB_NAME, DB_USER


@task
def backup(c, clear=True):
    """Create a backup of the database

    :param c: The Invoke context, which is used to run the command.
    :param clear: If True, deletes the backup file from the container after copying it.
    """
    os.makedirs(BACKUP_DIR, exist_ok=True)

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_file = f"{BACKUP_DIR}/backup_{timestamp}.bkp"
    container_backup_path = "/var/lib/postgresql/backup.bkp"

    print(f"Creating backup: {backup_file}")

    cmd = (
        f"docker exec -u {DB_USER} {DB_CONTAINER} pg_dump -F c -d {DB_NAME} -f {container_backup_path} && "
        f"docker cp {DB_CONTAINER}:{container_backup_path} {backup_file}"
    )

    if clear:
        cmd += f" && docker exec -u {DB_USER} {DB_CONTAINER} rm {container_backup_path}"

    c.run(cmd)
    print("Backup completed.")


@task
def restore(c, file_name, clear=True):
    """Restore the database from a backup file

    :param c: The Invoke context, which is used to run the command.
    :param file_name: The name of the backup file to restore (must be inside the `backups` directory).
    :param clear: If True, deletes the restore file from the container after restoring it.
    """
    backup_path = os.path.join(BACKUP_DIR, file_name)
    container_restore_path = "/var/lib/postgresql/restore.bkp"

    if not os.path.exists(backup_path):
        print(f"Backup file not found: {backup_path}")
        return

    print(f"Restoring database from: {backup_path}")

    c.run(f"docker cp {backup_path} {DB_CONTAINER}:{container_restore_path}")

    cmd = (
        f"docker exec -u {DB_USER} {DB_CONTAINER} pg_restore -d {DB_NAME} --clean --if-exists {container_restore_path}"
    )

    if clear:
        cmd += f" && docker exec -u {DB_USER} {DB_CONTAINER} rm {container_restore_path}"

    c.run(cmd)
    print("Restore completed.")
