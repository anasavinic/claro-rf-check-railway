from django.contrib import admin

from email_lists.models import EmailAddress, EmailList


class EmailAddressInline(admin.TabularInline):
    model = EmailAddress
    extra = 0


@admin.register(EmailList)
class EmailListAdmin(admin.ModelAdmin):
    list_display = ("name", "updated_at")
    search_fields = ("name",)
    inlines = [EmailAddressInline]


@admin.register(EmailAddress)
class EmailAddressAdmin(admin.ModelAdmin):
    list_display = ("address", "email_list")
    search_fields = ("address", "email_list__name")
