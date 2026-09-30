from django import forms

from precheck.services.returns import validate_return_upload


class PoscheckReturnUploadForm(forms.Form):
    file = forms.FileField()

    def clean_file(self):
        uploaded = self.cleaned_data["file"]
        issues = validate_return_upload(uploaded)
        if issues:
            raise forms.ValidationError(issues[0].message)
        return uploaded
