from django.db import transaction
from django.utils import timezone

from email_lists.models import EmailAddress, EmailList
from email_lists.services.parser import AddressBatch


def apply_batch(email_list: EmailList, batch: AddressBatch) -> tuple[int, int, int]:
    """Insert new addresses. Returns added, duplicates, ignored."""
    existing = set(email_list.addresses.values_list("address", flat=True))
    to_create: list[EmailAddress] = []
    duplicates = batch.duplicates
    for address in batch.accepted:
        if address in existing:
            duplicates += 1
            continue
        existing.add(address)
        to_create.append(EmailAddress(email_list=email_list, address=address))

    if to_create:
        with transaction.atomic():
            EmailAddress.objects.bulk_create(to_create)
            EmailList.objects.filter(pk=email_list.pk).update(updated_at=timezone.now())
    return len(to_create), duplicates, batch.ignored
