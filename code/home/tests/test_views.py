import pytest
from django.contrib.auth import get_user_model
from django.urls import reverse


@pytest.mark.django_db
def test_home_index_redirects_anonymous_to_sso(client):
    response = client.get(reverse("home:index"))
    assert response.status_code == 302
    assert response["Location"].endswith("/claro-rf/sso/login/")


@pytest.mark.django_db
def test_home_index_authenticated(client):
    User = get_user_model()
    user = User.objects.create_user(username="tester", email="tester@example.com", password="x")
    client.force_login(user)
    response = client.get(reverse("home:index"))
    assert response.status_code == 200
    assert b"Claro RF Check" in response.content or b"Claro RF check" in response.content
    assert b"Dashboard" in response.content
    assert b"RF check by technology" in response.content
    assert b"layers-active.svg" in response.content
    assert b"Monitoring" not in response.content


def test_healthz_does_not_need_the_database(client):
    response = client.get("/healthz")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


@pytest.mark.django_db
def test_readyz_checks_the_database(client):
    response = client.get("/readyz")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
