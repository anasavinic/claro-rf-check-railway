import pytest
from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.urls import reverse
from email_lists.models import EmailAddress, EmailList


@pytest.mark.django_db
def test_index_shows_help_button_without_action(client):
    response = client.get(reverse("email_lists:index"))

    assert response.status_code == 200
    assert b"Listas de e-mail" in response.content
    assert b"Cadastrar" not in response.content
    assert b"Guide" in response.content
    assert reverse("email_lists:guide").encode() in response.content
    assert b'name="addresses"' in response.content


@pytest.mark.django_db
def test_home_links_to_email_lists(client):
    user = get_user_model().objects.create_user(username="tester", password="x")
    client.force_login(user)

    response = client.get(reverse("home:index"))

    assert response.status_code == 200
    assert reverse("email_lists:index").encode() in response.content
    assert b"Listas de e-mail" in response.content


@pytest.mark.django_db
def test_manual_addresses_create_list_and_report_missing_at(client):
    response = client.post(
        reverse("email_lists:import_csv"),
        {"mode": "new", "name": "CO", "addresses": "a@claro.com; A@claro.com\nsem-arroba"},
        follow=True,
    )

    email_list = EmailList.objects.get()
    body = response.content.decode()
    assert response.status_code == 200
    assert email_list.name == "CO"
    assert list(email_list.addresses.values_list("address", flat=True)) == ["a@claro.com"]
    assert "1 endereço adicionado" in body
    assert "1 repetido" in body
    assert "Endereço inválido: sem-arroba" in body
    assert "Informe um e-mail com @." in body


@pytest.mark.django_db
def test_address_without_at_does_not_create_list(client):
    response = client.post(
        reverse("email_lists:import_csv"),
        {"mode": "new", "name": "Vazia", "addresses": "sem-arroba"},
        follow=True,
    )

    assert EmailList.objects.count() == 0
    assert "Endereço inválido: sem-arroba" in response.content.decode()


@pytest.mark.django_db
def test_import_csv_creates_list_and_appends_without_duplicates(client):
    csv_body = "Name,E-mail Address\nJosé,ana@claro.com.br\n,sem-email\n".encode("windows-1252")
    created = client.post(
        reverse("email_lists:import_csv"),
        {
            "mode": "new",
            "name": "Regional",
            "file": SimpleUploadedFile("contatos.csv", csv_body, content_type="text/csv"),
        },
        follow=True,
    )
    email_list = EmailList.objects.get(name="Regional")
    assert EmailAddress.objects.filter(email_list=email_list).count() == 1
    created_body = created.content.decode()
    assert "Lista Regional criada" in created_body
    assert "Endereço inválido: sem-email" in created_body

    again = "E-mail Address\nana@claro.com.br\nnovo@claro.com.br\n".encode("utf-8")
    appended = client.post(
        reverse("email_lists:import_csv"),
        {
            "mode": "existing",
            "email_list": email_list.pk,
            "file": SimpleUploadedFile("mais.csv", again, content_type="text/csv"),
        },
        follow=True,
    )

    assert list(email_list.addresses.order_by("address").values_list("address", flat=True)) == [
        "ana@claro.com.br",
        "novo@claro.com.br",
    ]
    body = appended.content.decode()
    assert "1 endereço adicionado" in body
    assert "1 repetido" in body


@pytest.mark.django_db
def test_import_rejects_csv_without_column(client):
    response = client.post(
        reverse("email_lists:import_csv"),
        {
            "mode": "new",
            "name": "Ruim",
            "file": SimpleUploadedFile("ruim.csv", b"Nome,Email\nA,a@x.com\n", content_type="text/csv"),
        },
        follow=True,
    )

    assert EmailList.objects.count() == 0
    assert "E-mail Address" in response.content.decode()


@pytest.mark.django_db
def test_htmx_error_keeps_response_on_the_form(client):
    response = client.post(
        reverse("email_lists:import_csv"),
        {"mode": "new", "name": "Vazia", "addresses": "sem-arroba"},
        HTTP_HX_REQUEST="true",
    )

    assert response.status_code == 200
    body = response.content.decode()
    assert "Endereço inválido: sem-arroba" in body
    assert "Listas de e-mail" not in body
    assert EmailList.objects.count() == 0


@pytest.mark.django_db
def test_panel_returns_only_the_saved_list(client):
    email_list = EmailList.objects.create(name="Temp")
    EmailAddress.objects.create(email_list=email_list, address="a@claro.com")

    response = client.get(f"{reverse('email_lists:panel')}?list={email_list.pk}")

    assert response.status_code == 200
    body = response.content.decode()
    assert "Temp" in body
    assert "a@claro.com" in body
    assert "<!DOCTYPE" not in body
    assert "Adicionar endereços" not in body


@pytest.mark.django_db
def test_export_selected_list_as_csv(client):
    email_list = EmailList.objects.create(name="Regional CO")
    EmailAddress.objects.create(email_list=email_list, address="ana@claro.com.br")

    response = client.get(reverse("email_lists:export", args=[email_list.pk]))

    assert response.status_code == 200
    assert "text/csv" in response["Content-Type"]
    assert "attachment" in response["Content-Disposition"]
    body = response.content.decode("utf-8-sig")
    assert "E-mail Address" in body
    assert "ana@claro.com.br" in body


@pytest.mark.django_db
def test_guide_downloads_pdf(client):
    response = client.get(reverse("email_lists:guide"))

    assert response.status_code == 200
    assert response["Content-Type"] == "application/pdf"
    assert response.content.startswith(b"%PDF")
    assert 'filename="guide-listas-de-email.pdf"' in response["Content-Disposition"]
    assert "Exportar CSV" in response.content.decode("latin-1")


@pytest.mark.django_db
def test_selected_list_panel_offers_export(client):
    email_list = EmailList.objects.create(name="Temp")
    response = client.get(f"{reverse('email_lists:panel')}?list={email_list.pk}")

    assert reverse("email_lists:export", args=[email_list.pk]).encode() in response.content
    assert b"Exportar CSV" in response.content


@pytest.mark.django_db
def test_remove_address_and_delete_list(client):
    email_list = EmailList.objects.create(name="Temp")
    address = EmailAddress.objects.create(email_list=email_list, address="a@claro.com")

    removed = client.post(
        reverse("email_lists:remove", args=[email_list.pk, address.pk]),
        follow=True,
    )
    assert removed.status_code == 200
    assert email_list.addresses.count() == 0

    deleted = client.post(reverse("email_lists:delete", args=[email_list.pk]), follow=True)
    assert deleted.status_code == 200
    assert EmailList.objects.count() == 0
