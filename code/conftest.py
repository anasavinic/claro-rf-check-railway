import pytest


@pytest.fixture(scope="session", autouse=True)
def _django_db_setup():
    pass
