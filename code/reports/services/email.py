"""Outlook-compatible email draft built from consolidated results."""

from __future__ import annotations

from email.message import EmailMessage
from email.policy import SMTP

from msgforge import Message

from reports.services.payload import ExportPayload, ValidationRow
from reports.services.xlsx import render_xlsx, report_basename

EML_CONTENT_TYPE = "message/rfc822"
MSG_CONTENT_TYPE = "application/vnd.ms-outlook"


def render_email(payload: ExportPayload, *, from_address: str = "") -> bytes:
    """Build an unsent .eml so Outlook opens an editable draft with the Excel attached."""
    message = EmailMessage(policy=SMTP)
    message["Subject"] = _subject(payload)
    if from_address:
        message["From"] = from_address
    message["To"] = ""
    message["X-Unsent"] = "1"
    message.set_content(_body(payload))

    xlsx_name = f"{report_basename(payload)}.xlsx"
    message.add_attachment(
        render_xlsx(payload),
        maintype="application",
        subtype="vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        filename=xlsx_name,
    )
    return message.as_bytes()


def render_msg(payload: ExportPayload, *, from_address: str = "") -> bytes:
    """Build an unsent Outlook .msg draft with the Excel report attached."""
    message = Message(
        subject=_subject(payload),
        text_body=_body(payload),
        sender=from_address or None,
        sent=False,
    )
    xlsx_name = f"{report_basename(payload)}.xlsx"
    message.attach_bytes(
        xlsx_name,
        render_xlsx(payload),
        mime_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )
    return message.as_bytes()


def _subject(payload: ExportPayload) -> str:
    return f"Claro RF Check — {payload.tech_label} {payload.site} ({payload.analysis_status_label})"


def _body(payload: ExportPayload) -> str:
    lines = [
        "Claro RF Check — Analysis results",
        "",
        f"Status: {payload.analysis_status_label}",
        f"Technology: {payload.tech_label}",
        f"Site: {payload.site}",
        f"Type: {payload.check_types_label}",
        f"Date: {payload.processed_at}",
        f"Cells: {len(payload.cells)} ({', '.join(payload.cells) or '—'})",
        f"Overall Score: {payload.score}%" if payload.score is not None else "Overall Score: —",
        (
            f"Total: {payload.counts['total']} | "
            f"OK: {payload.counts['consistent']} | "
            f"Warnings: {payload.counts['failed']} | "
            f"NOK: {payload.counts['inconsistent']}"
        ),
        "",
    ]
    for section in payload.sections:
        lines.append(f"== {section.check_type} ({section.status_label}) ==")
        lines.append(
            f"Total: {section.counts['total']} | "
            f"OK: {section.counts['consistent']} | "
            f"Warnings: {section.counts['failed']} | "
            f"NOK: {section.counts['inconsistent']}"
        )
        lines.append("Parameter | Expected Value | Found Value | Status | Notes")
        for row in section.validations:
            lines.append(_row_line(row))
        lines.append("")
    lines.append("The Excel report is attached with the same consolidated results.")
    return "\n".join(lines).rstrip() + "\n"


def _row_line(row: ValidationRow) -> str:
    return f"{row.label} | {row.expected} | {row.found} | {row.status_label} | {row.note}"
