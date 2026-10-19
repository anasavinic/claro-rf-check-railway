from django.db import models
from django.db.models.functions import Lower


class EmailList(models.Model):
    name = models.CharField(max_length=120)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ("name",)
        constraints = [
            models.UniqueConstraint(Lower("name"), name="uniq_email_list_name_ci"),
        ]

    def __str__(self) -> str:
        return self.name


class EmailAddress(models.Model):
    email_list = models.ForeignKey(EmailList, on_delete=models.CASCADE, related_name="addresses")
    address = models.CharField(max_length=254)

    class Meta:
        ordering = ("address",)
        constraints = [
            models.UniqueConstraint(fields=["email_list", "address"], name="uniq_address_per_list"),
        ]

    def __str__(self) -> str:
        return self.address
