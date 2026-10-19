import pytest
from email_lists.services.parser import CsvFormatError, parse_freeform, parse_outlook_csv


def test_parse_freeform_splits_dedupes_and_ignores_tokens_without_at():
    batch = parse_freeform("A@X.com; a@x.com, sem-email\nb@x.com\n\n@invalido")

    assert batch.accepted == ["a@x.com", "b@x.com"]
    assert batch.duplicates == 1
    assert batch.invalid == ["sem-email", "@invalido"]


def test_parse_outlook_csv_windows_1252():
    raw = "Name,E-mail Address\nJosé,Ana@Claro.com.br\n".encode("windows-1252")

    batch = parse_outlook_csv(raw)

    assert batch.accepted == ["ana@claro.com.br"]
    assert batch.ignored == 0


def test_parse_outlook_csv_utf8_and_semicolon():
    raw = "Nome;E-mail Address\nAna;ana@claro.com.br\n".encode("utf-8")

    batch = parse_outlook_csv(raw)

    assert batch.accepted == ["ana@claro.com.br"]


def test_parse_outlook_csv_requires_email_column():
    raw = "Nome,Email\nAna,ana@claro.com.br\n".encode("utf-8")

    with pytest.raises(CsvFormatError, match="E-mail Address"):
        parse_outlook_csv(raw)
