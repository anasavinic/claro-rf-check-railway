import csv
import io
import re
from urllib.parse import quote

from django.contrib import messages
from django.db import IntegrityError, transaction
from django.db.models import Count
from django.http import HttpRequest, HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.http import require_GET, require_POST

from email_lists.forms import ImportCsvForm
from email_lists.models import EmailAddress, EmailList
from email_lists.services.guide_pdf import build_guide_pdf
from email_lists.services.parser import (
    CsvFormatError,
    combine_batches,
    format_stats,
    invalid_address_message,
    parse_freeform,
    parse_outlook_csv,
)
from email_lists.services.store import apply_batch

TECH_NAV = [
    ("2G", "2G"),
    ("3G", "3G"),
    ("4G", "4G"),
    ("5G", "5G NR"),
]


def _first_error(form) -> str:
    if form.non_field_errors():
        return str(form.non_field_errors()[0])
    for errors in form.errors.values():
        if errors:
            return str(errors[0])
    return "Não foi possível salvar."


def _redirect_to(email_list: EmailList | None = None) -> HttpResponse:
    url = reverse("email_lists:index")
    if email_list is not None:
        return redirect(f"{url}?list={email_list.pk}")
    return redirect(url)


def _selected_list(request: HttpRequest) -> EmailList | None:
    raw = request.GET.get("list") or ""
    if not raw.isdigit():
        return None
    return EmailList.objects.filter(pk=int(raw)).first()


def _existing_target(form: ImportCsvForm) -> EmailList | None:
    if form.cleaned_data.get("mode") != ImportCsvForm.MODE_EXISTING:
        return None
    target = form.cleaned_data.get("email_list")
    return target if isinstance(target, EmailList) else None


def _panel_context(request: HttpRequest, selected: EmailList | None = None) -> dict:
    lists = EmailList.objects.annotate(address_count=Count("addresses"))
    if selected is None:
        selected = _selected_list(request)
    addresses = selected.addresses.all() if selected else EmailAddress.objects.none()
    return {
        "active_nav": "email_lists",
        "tech_nav": TECH_NAV,
        "lists": lists,
        "selected": selected,
        "addresses": addresses,
    }


def _finish(request: HttpRequest, email_list: EmailList | None = None, *, refresh_lists: bool = False) -> HttpResponse:
    if getattr(request, "htmx", False):
        context = _panel_context(request, selected=email_list)
        context["refresh_lists"] = refresh_lists
        return render(request, "email_lists/partials/import_feedback.html", context)
    return _redirect_to(email_list)


@require_GET
def index(request: HttpRequest) -> HttpResponse:
    return render(request, "email_lists/index.html", _panel_context(request))


@require_GET
def panel(request: HttpRequest) -> HttpResponse:
    return render(request, "email_lists/partials/saved_lists.html", _panel_context(request))


@require_GET
def guide(request: HttpRequest) -> HttpResponse:
    pdf = build_guide_pdf()
    response = HttpResponse(pdf, content_type="application/pdf")
    response["Content-Disposition"] = 'attachment; filename="guide-listas-de-email.pdf"'
    return response


@require_GET
def export_csv(request: HttpRequest, list_id: int) -> HttpResponse:
    email_list = get_object_or_404(EmailList, pk=list_id)
    buffer = io.StringIO()
    writer = csv.writer(buffer)
    writer.writerow(["E-mail Address"])
    for address in email_list.addresses.order_by("address"):
        writer.writerow([address.address])
    filename = _csv_filename(email_list.name)
    response = HttpResponse(buffer.getvalue().encode("utf-8-sig"), content_type="text/csv; charset=utf-8")
    response["Content-Disposition"] = f"attachment; filename=\"{filename}\"; filename*=UTF-8''{quote(filename)}"
    return response


def _csv_filename(name: str) -> str:
    slug = re.sub(r"[^A-Za-z0-9._-]+", "-", name).strip("-") or "lista"
    return f"{slug}.csv"


@require_POST
def remove_address(request: HttpRequest, list_id: int, address_id: int) -> HttpResponse:
    email_list = get_object_or_404(EmailList, pk=list_id)
    address = get_object_or_404(EmailAddress, pk=address_id, email_list=email_list)
    address.delete()
    EmailList.objects.filter(pk=email_list.pk).update(updated_at=timezone.now())
    messages.success(request, f"{address.address} removido.")
    return _finish(request, email_list, refresh_lists=True)


@require_POST
def delete_list(request: HttpRequest, list_id: int) -> HttpResponse:
    email_list = get_object_or_404(EmailList, pk=list_id)
    name = email_list.name
    email_list.delete()
    messages.success(request, f"Lista {name} excluída.")
    return _finish(request, refresh_lists=True)


@require_POST
def import_csv(request: HttpRequest) -> HttpResponse:
    form = ImportCsvForm(request.POST, request.FILES)
    if not form.is_valid():
        messages.error(request, _first_error(form))
        selected = form.cleaned_data.get("email_list") if form.is_bound else None
        return _finish(request, selected if isinstance(selected, EmailList) else None)

    manual = parse_freeform(form.cleaned_data.get("addresses") or "")
    uploaded = form.cleaned_data.get("file")
    if uploaded:
        try:
            csv_batch = parse_outlook_csv(uploaded.read())
        except CsvFormatError as exc:
            messages.error(request, exc.message)
            return _finish(request, _existing_target(form))
        batch = combine_batches(csv_batch, manual)
    else:
        batch = manual

    if batch.invalid:
        messages.error(request, invalid_address_message(batch.invalid))

    if not batch.accepted:
        return _finish(request, _existing_target(form))

    created = False
    try:
        with transaction.atomic():
            if form.cleaned_data["mode"] == ImportCsvForm.MODE_NEW:
                email_list = EmailList.objects.create(name=form.cleaned_data["name"])
                created = True
            else:
                email_list = form.cleaned_data["email_list"]
            added, duplicates, _ignored = apply_batch(email_list, batch)
    except IntegrityError:
        messages.error(request, "Já existe uma lista com esse nome.")
        return _finish(request)

    prefix = f"Lista {email_list.name} criada. " if created else ""
    messages.success(request, prefix + format_stats(added, duplicates))
    return _finish(request, email_list, refresh_lists=True)
