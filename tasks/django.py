from invoke import task

from tasks.config import CONTAINER_NAME


@task
def makemigrations(c):
    """Run Django makemigrations inside the container

    :param c: The Invoke context, which is used to run the command.
    """
    cmd = f"docker exec {CONTAINER_NAME} python /code/manage.py makemigrations"
    c.run(cmd)


@task
def migrate(c):
    """Apply Django migrations inside the container

    :param c: The Invoke context, which is used to run the command.
    """
    cmd = f"docker exec {CONTAINER_NAME} python /code/manage.py migrate"
    c.run(cmd)
