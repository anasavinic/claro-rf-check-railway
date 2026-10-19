from django import forms

from email_lists.models import EmailList
from email_lists.services.parser import MAX_CSV_BYTES

MAX_PASTE_CHARS = 500_000


class ImportCsvForm(forms.Form):
    MODE_NEW = "new"
    MODE_EXISTING = "existing"

    mode = forms.ChoiceField(
        choices=[(MODE_NEW, "Nova lista"), (MODE_EXISTING, "Lista existente")],
        error_messages={"required": "Escolha nova lista ou lista existente."},
    )
    name = forms.CharField(max_length=120, required=False, strip=True)
    email_list = forms.ModelChoiceField(
        queryset=EmailList.objects.none(),
        required=False,
        error_messages={"invalid_choice": "Selecione uma lista."},
    )
    addresses = forms.CharField(required=False, strip=False)
    file = forms.FileField(required=False)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["email_list"].queryset = EmailList.objects.all()

    def clean_addresses(self):
        text = self.cleaned_data.get("addresses") or ""
        if len(text) > MAX_PASTE_CHARS:
            raise forms.ValidationError("Texto grande demais.")
        return text

    def clean_file(self):
        uploaded = self.cleaned_data.get("file")
        if not uploaded:
            return None
        name = (getattr(uploaded, "name", "") or "").lower()
        if not name.endswith(".csv"):
            raise forms.ValidationError("Formatos aceitos: .csv.")
        if uploaded.size and uploaded.size > MAX_CSV_BYTES:
            raise forms.ValidationError("Arquivo excede o limite de 5 MB.")
        return uploaded

    def clean(self):
        cleaned = super().clean()
        mode = cleaned.get("mode")
        name = (cleaned.get("name") or "").strip()
        email_list = cleaned.get("email_list")
        addresses = (cleaned.get("addresses") or "").strip()
        uploaded = cleaned.get("file")

        if not uploaded and not addresses and "file" not in self.errors and "addresses" not in self.errors:
            raise forms.ValidationError("Envie um CSV ou informe ao menos um endereço.")

        if mode == self.MODE_NEW:
            if not name:
                self.add_error("name", "Informe o nome da lista.")
            elif EmailList.objects.filter(name__iexact=name).exists():
                self.add_error("name", "Já existe uma lista com esse nome.")
            else:
                cleaned["name"] = name
        elif mode == self.MODE_EXISTING and email_list is None:
            self.add_error("email_list", "Selecione uma lista.")
        return cleaned
