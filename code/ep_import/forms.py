from django import forms

from ep_import.schema import Technology
from ep_import.services.content import validate_upload_file


class EpUploadForm(forms.Form):
    file = forms.FileField()
    technology = forms.ChoiceField(
        choices=[(t.value, t.value) for t in Technology],
        required=False,
        initial=Technology.G5.value,
    )

    def clean_file(self):
        uploaded = self.cleaned_data["file"]
        issues = validate_upload_file(uploaded)
        if issues:
            raise forms.ValidationError(issues[0].message)
        return uploaded
