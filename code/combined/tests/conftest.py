import pytest
from django.contrib.auth import get_user_model


@pytest.fixture
def user(db):
    return get_user_model().objects.create_user(
        username="combined-user",
        password="pass",  # pragma: allowlist secret
        is_staff=True,
    )


@pytest.fixture
def auth_client(client, user):
    client.force_login(user)
    client.user = user
    return client
