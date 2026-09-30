from invoke import task

from tasks.config import CONTAINER_NAME


def _cache_shell(c, code: str) -> None:
    """Run a one-shot Django shell snippet inside the app container."""
    escaped = code.replace('"', '\\"')
    cmd = f'docker exec {CONTAINER_NAME} python /code/manage.py shell -c "{escaped}"'
    c.run(cmd)


@task
def cache_clear(c):
    """Clear the entire Django default cache (Redis db used by CACHES)."""
    _cache_shell(c, "from django.core.cache import cache; cache.clear(); print('cache cleared')")


@task
def cache_info(c):
    """Show cache backend and Redis location."""
    _cache_shell(
        c,
        "from django.conf import settings; c=settings.CACHES['default']; "
        "print(c['BACKEND']); print(c.get('LOCATION', ''))",
    )
