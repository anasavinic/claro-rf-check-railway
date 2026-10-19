from django import forms
from django.contrib.auth.models import Group, Permission
from users.permissions import assignable_permissions_queryset


class RoleForm(forms.ModelForm):
    permissions = forms.ModelMultipleChoiceField(
        queryset=Permission.objects.none(),
        required=False,
        widget=forms.MultipleHiddenInput,
    )

    class Meta:
        model = Group
        fields = ["name", "permissions"]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["permissions"].queryset = assignable_permissions_queryset()
        self.fields["name"].widget.attrs.update(
            {
                "class": "input input-editable w-full",
                "placeholder": "Role name",
            }
        )
