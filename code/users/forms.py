from django import forms
from django.contrib.auth.models import Group

from users.models import User
from users.permissions import assignable_permissions_queryset


def _setup_rbac_fields(form, *, can_edit_rbac: bool):
    """Attach Roles + Extra permissions only for manage_roles editors."""
    form.can_edit_rbac = can_edit_rbac
    if not can_edit_rbac:
        form.fields.pop("groups", None)
        form.fields.pop("user_permissions", None)
        return

    form.fields["groups"] = forms.ModelMultipleChoiceField(
        queryset=Group.objects.order_by("name"),
        required=False,
        label="Roles",
    )
    form.fields["user_permissions"] = forms.ModelMultipleChoiceField(
        queryset=assignable_permissions_queryset(),
        required=False,
        label="Extra permissions",
        widget=forms.MultipleHiddenInput,
    )
    if form.instance.pk:
        form.fields["groups"].initial = [g.pk for g in form.instance.groups.all()]
        form.fields["user_permissions"].initial = [p.pk for p in form.instance.user_permissions.all()]


class UserRbacForm(forms.ModelForm):
    """Edit profile fields that are safe locally + optional RBAC assignment."""

    class Meta:
        model = User
        fields = ("first_name", "last_name", "email", "is_active")

    def __init__(self, *args, can_edit_rbac: bool = False, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["email"].disabled = True
        self.fields["email"].required = False
        for name in ("first_name", "last_name", "email"):
            self.fields[name].widget.attrs.update({"class": "input input-editable w-full"})
        self.fields["is_active"].widget.attrs.update(
            {"class": "size-4 rounded border-input-border text-primary accent-primary"}
        )
        _setup_rbac_fields(self, can_edit_rbac=can_edit_rbac)

    def clean_email(self):
        return self.instance.email

    def save(self, commit=True):
        user = super().save(commit=False)
        user.email = self.instance.email
        if commit:
            user.save()
            self.save_m2m()
            # groups / user_permissions are attached in __init__, not Meta.fields,
            # so ModelForm.save_m2m skips them — set explicitly (Core Connect pattern).
            if getattr(self, "can_edit_rbac", False):
                if "groups" in self.cleaned_data:
                    user.groups.set(self.cleaned_data["groups"])
                if "user_permissions" in self.cleaned_data:
                    user.user_permissions.set(self.cleaned_data["user_permissions"])
        return user
