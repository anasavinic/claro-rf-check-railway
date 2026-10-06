"""Script generation for Claro checks."""

from __future__ import annotations

import os
from typing import Final, Sequence

PRECHECK_5G_COMMANDS: Final[tuple[str, ...]] = (
    "LST GNODEBFUNCTION:;",
    "LST GNBTRACKINGAREA:;",
)

FULL_CHECK_5G_COMMANDS: Final[tuple[str, ...]] = (
    "DSP NRDUCELL:;",
    "DSP NRCELLUENUMBER:;",
    "LST NRCELL:;",
    "LST NRDUCELL:;",
    "LST GNODEBFUNCTION:;",
    "LST GNBTRACKINGAREA:;",
    "LST GNBOPERATOR:;",
    "LST NRDUCELLTRPBEAM:;",
    "LST NRDUCELLTRP:;",
    "LST GNBX2SONCONFIG:;",
    "LST NCELLPLMNLIST:;",
    "LST NRMFBIFREQ:;",
    "LST NSADCALGOPARAM:;",
    "LST GNBOAMPARAM:;",
    "LST NRDUCELLPDSCH:;",
    "LST NRDUCELLPUSCH:;",
    "LST FTPSCLT:;",
    "LST GNBCAFREQUENCY:;",
    "LST NRCELLALGOSWITCH:;",
    "LST NRCELLRELATION:;",
    "LST NRCELLEUTRANNFREQ:;",
    "LST NRCELLEUTRANRELATION:;",
    "LST GNBEUTRAEXTERNALCELL:;",
    "LST NRCELLFREQRELATION:;",
    "LST NREXTERNALNCELL:;",
    "LST RRU:;",
    "DSP BRDMFRINFO:;",
    "LST ALMAF:;",
    "CHK DATA2LIC:FUNCTIONTYPE=gNodeB;",
)

# Site-level 3G full-check (pos-check) commands.
FULL_CHECK_3G_SITE_COMMANDS: Final[tuple[str, ...]] = (
    "LST UCELL",
    "LST UCNOPERATOR",
    "LST UCNOPERGROUP",
)

# Per-cell 3G full-check commands (CellId substituted dynamically).
FULL_CHECK_3G_PER_CELL_COMMANDS: Final[tuple[str, ...]] = (
    "LST UINTRAFREQNCELL",
    "LST UINTERFREQNCELL",
    "LST U2GNCELL",
    "LST UCELLNFREQPRIOINFO",
    "LST UCELLHSDPA",
    "LST UCELLHSUPA",
    "LST UPCPICH",
)

# Site-level 4G full-check (pos-check) commands (RETCODE validation names).
FULL_CHECK_4G_SITE_COMMANDS: Final[tuple[str, ...]] = (
    "LST ENODEBFUNCTION",
    "LST CNOPERATOR",
    "LST CNOPERATORTA",
    "LST TWAMPRESPONDER",
    "LST SCTPHOST",
    "LST EUTRANINTRAFREQNCELL",
    "LST EUTRANINTERFREQNCELL",
    "LST UTRANEXTERNALCELLPLMN",
    "LST GERANEXTERNALCELL",
    "LST PCCFREQCFG",
    "LST SCCFREQCFG",
    "DSP RETSUBUNIT",
    "LST SECTORSPLITCELL",
    "LST CSFALLBACKBLINDHOCFG",
    "DSP CELL",
    "LST ALMAF",
    "LST NREXTERNALCELL",
    "CHK DATA2LIC",
    "LST NCELLPLMNLIST",
    "LST NRMFBIFREQ",
    "LST GLOBALPROCSWITCH",
    "LST NRSCGFREQCONFIG",
    "LST CELLEMERGENCYAREA",
    "LST RRU",
    "LST RHUB",
    "LST PRB",
    "DSP BRDMFRINFO",
    "LST ENODEBRESMODEALGO",
    "LST CELLPREALLOCGROUP",
    "DSP LICINFO",
)

# Cell-table 4G full-check commands (site-wide MML; returns rows per Local Cell ID).
FULL_CHECK_4G_PER_CELL_COMMANDS: Final[tuple[str, ...]] = (
    "LST CELL",
    "LST CELLOP",
    "LST EUTRANINTERNFREQ",
    "LST UTRANNFREQ",
    "LST GERANNFREQGROUP",
    "LST GERANNFREQGROUPARFCN",
    "LST GERANNCELL",
    "LST CAGROUPSCELLCFG",
    "LST CAMGTCFG",
    "LST CELLALGOSWITCH",
    "LST CELLHOPARACFG",
    "LST NRNRELATIONSHIP",
    "LST NRNFREQ",
    "LST NSADCMGMTCONFIG",
    "LST CELLSIMAP",
    "LST CELLRACHCECFG",
    "LST CELLDLSCHALGO",
    "LST EUCELLSECTOREQM",
    "LST CELLRESEL",
)

FULL_CHECK_ONLY_TECHNOLOGIES: Final[frozenset[str]] = frozenset({"2G", "3G", "4G"})

# Site-level 2G full-check (pos-check) commands. Identifiers: BTS (and BSC for NE).
FULL_CHECK_2G_SITE_COMMANDS: Final[tuple[str, ...]] = (
    "LST GCELL",
    "LST GCELLPSCHM",
    "LST GCELLCHMGAD",
    "LST GCELLBASICPARA",
    "LST GCELLFREQ",
    "LST GCELLMAGRP",
    "LST GCELLHOPTP",
    "LST PTPBVC",
    "LST GTRXDEV",
    "LST GTRX",
    "LST GCELLGPRS",
    "DSP GCELLSTAT",
)

# Per-cell 2G full-check commands (Cell name substituted dynamically).
FULL_CHECK_2G_PER_CELL_COMMANDS: Final[tuple[str, ...]] = (
    "LST G2GNCELL",
    "LST G3GNCELL",
    "LST GLTENCELL",
    "LST GTRXHOP",
    "LST GTRXCHAN",
    "LST GCELLMAIOPLAN",
)

_IDENTIFIER_KEYS: Final[tuple[str, ...]] = ("BSC", "BTS", "CELL", "CELLID")
CELL_ID_EP_FIELDS: Final[dict[str, tuple[str, ...]]] = {
    "2G": ("*CI", "CI", "CELL ID"),
    "3G": ("CELL ID",),
    "4G": ("CELL ID",),
    "5G": ("CellId",),
}


def generate_precheck_5g_script() -> str:
    """Return the approved Claro 5G pre-check commands in execution order."""
    return "\n".join(PRECHECK_5G_COMMANDS) + "\n"


def generate_full_check_5g_script() -> str:
    """Return the approved Claro 5G full-check commands in execution order."""
    return "\n".join(FULL_CHECK_5G_COMMANDS) + "\n"


def umts_cellname_filter(site_name: str, cell_names: Sequence[str]) -> str:
    """Build the CELLNAME token used by Claro UMTS LST UCELL commands."""
    names = [str(name).strip() for name in cell_names if str(name).strip()]
    site = (site_name or "").strip()
    if site and names:
        for index in range(len(site)):
            token = site[index:]
            if len(token) >= 4 and all(token in name for name in names):
                return token
    if len(names) >= 2:
        prefix = os.path.commonprefix(names)
        if len(prefix) >= 4:
            return prefix
    if names:
        return names[0]
    return site


def generate_full_check_3g_script(
    *,
    site_name: str = "",
    cell_names: Sequence[str] | None = None,
    cell_ids: Sequence[str] | None = None,
) -> str:
    """Return Claro 3G full-check (pos-check) commands with dynamic identifiers."""
    token = umts_cellname_filter(site_name, cell_names or ())
    if not token:
        token = "SITE"
    lines = [
        f'LST UCELL:LSTTYPE=ByCellName,CELLNAME="{token}";',
        "LST UCNOPERATOR:;",
        "LST UCNOPERGROUP:;",
    ]
    for cell_id in cell_ids or ():
        cid = str(cell_id).strip()
        if not cid:
            continue
        lines.extend(
            [
                f"LST UINTRAFREQNCELL:CELLID={cid};",
                f"LST UINTERFREQNCELL:CELLID={cid};",
                f"LST U2GNCELL:CELLID={cid};",
                f"LST UCELLNFREQPRIOINFO:CELLID={cid},LSTFORMAT=HORIZONTAL;",
                f"LST UCELLHSDPA:LSTTYPE=ByCellId,CELLID={cid};",
                f"LST UCELLHSUPA:LSTTYPE=ByCellId,CELLID={cid};",
                f"LST UPCPICH:CELLID={cid};",
            ]
        )
    lines.append("LST UCNOPERATOR:LSTFORMAT=HORIZONTAL;")
    return "\n".join(lines) + "\n"


def generate_full_check_4g_script(*, enodeb_id: str = "") -> str:
    """Return Claro 4G full-check (pos-check) commands in Gerencia execution order.

    Unlike 3G, LTE commands are site-wide (`COMMAND:;`). Cell details come back as
    table rows (Local Cell ID). Neighbor-cell lists take ENODEBID when available.
    """
    enb = str(enodeb_id or "").strip()
    if not enb:
        enb = "0000"
    elif enb.endswith(".0"):
        enb = enb[:-2]

    lines = [
        "LST CELL:;",
        "LST ENODEBFUNCTION:;",
        "LST CNOPERATOR:;",
        "LST CELLOP:;",
        "LST CNOPERATORTA:;",
        "LST TWAMPRESPONDER:;",
        "LST SCTPHOST:;",
        "LST EUTRANINTERNFREQ:;",
        f"LST EUTRANINTRAFREQNCELL:ENODEBID={enb};",
        f"LST EUTRANINTERFREQNCELL:ENODEBID={enb};",
        "LST UTRANNFREQ:;",
        "LST UTRANEXTERNALCELLPLMN:;",
        "LST GERANNFREQGROUP:;",
        "LST GERANNFREQGROUPARFCN:;",
        "LST GERANEXTERNALCELL:;",
        "LST GERANNCELL:;",
        "LST PCCFREQCFG:;",
        "LST SCCFREQCFG:;",
        "LST CAGROUPSCELLCFG:;",
        "LST CAMGTCFG:;",
        "DSP RETSUBUNIT:;",
        "LST SECTORSPLITCELL:;",
        "LST CELLALGOSWITCH:;",
        "LST CELLHOPARACFG:;",
        "LST CSFALLBACKBLINDHOCFG:;",
        "DSP CELL:;",
        "LST ALMAF:;",
        "LST NREXTERNALCELL:;",
        "LST NRNRELATIONSHIP:;",
        "CHK DATA2LIC:FUNCTIONTYPE=eNodeB;",
        "CHK DATA2LIC:FUNCTIONTYPE=gNodeB;",
        "LST NCELLPLMNLIST:;",
        "LST NRMFBIFREQ:;",
        "LST NRNFREQ:;",
        "LST GLOBALPROCSWITCH:;",
        "LST NRSCGFREQCONFIG:;",
        "LST NSADCMGMTCONFIG:;",
        "LST CELLEMERGENCYAREA:;",
        "LST CELLSIMAP:;",
        "LST CELLRACHCECFG:;",
        "LST RRU:;",
        "LST RHUB:;",
        "LST PRB:;",
        "LST CELLDLSCHALGO:;",
        "DSP BRDMFRINFO:CN=0,SRN=0,SN=7;",
        "LST ENODEBRESMODEALGO:;",
        "LST EUCELLSECTOREQM:;",
        "LST CELLPREALLOCGROUP:;",
        "DSP LICINFO:FUNCTIONTYPE=eNodeB;",
        "LST CELLRESEL:;",
    ]
    return "\n".join(lines) + "\n"


def apply_identifier_substitutions(template: str, identifiers: dict[str, str]) -> str:
    """Replace ``{BSC}``, ``{BTS}``, ``{CELL}``, ``{CELLID}`` (and ``%KEY%``) tokens."""
    rendered = template
    for key in _IDENTIFIER_KEYS:
        value = str(identifiers.get(key, "") or "")
        rendered = rendered.replace(f"{{{key}}}", value)
        rendered = rendered.replace(f"%{key}%", value)
    return rendered


def normalize_ep_cell_id(value: object) -> str:
    """Normalize an EP CellId / CI value for script substitution."""
    if value is None or value == "":
        return ""
    text = str(value).strip()
    if text.endswith(".0"):
        text = text[:-2]
    return text


def ep_cell_id_from_raw(raw: dict | None, technology: str) -> str:
    """Resolve CellId from an EP row using the technology field map."""
    payload = raw or {}
    for field in CELL_ID_EP_FIELDS.get(technology, ("CELL ID",)):
        value = normalize_ep_cell_id(payload.get(field))
        if value:
            return value
    return ""


def generate_full_check_2g_script(
    *,
    bsc: str = "",
    bts: str = "",
    site_name: str = "",
    cell_names: Sequence[str] | None = None,
    cell_ids: Sequence[str] | None = None,
) -> str:
    """Return Claro 2G full-check (pos-check) commands with dynamic identifiers."""
    bts_name = (bts or site_name or "").strip() or "BTS"
    bsc_name = (bsc or "").strip()
    cells = [str(name).strip() for name in (cell_names or ()) if str(name).strip()]
    ids = [normalize_ep_cell_id(cell_id) for cell_id in (cell_ids or ())]
    while len(ids) < len(cells):
        ids.append("")

    def _ids(cell: str, cell_id: str) -> dict[str, str]:
        return {"BSC": bsc_name, "BTS": bts_name, "CELL": cell, "CELLID": cell_id}

    site = _ids("", "")
    lines = [
        apply_identifier_substitutions('LST GCELL:IDTYPE=BYNAME,BTSNAME="{BTS}";', site),
    ]
    for cell, cell_id in zip(cells, ids, strict=False):
        lines.append(
            apply_identifier_substitutions(
                'LST G2GNCELL:IDTYPE=BYNAME,SRC2GNCELLNAME="{CELL}";',
                _ids(cell, cell_id),
            )
        )
    for cell, cell_id in zip(cells, ids, strict=False):
        lines.append(
            apply_identifier_substitutions(
                'LST G3GNCELL:IDTYPE=BYNAME,SRC3GNCELLNAME="{CELL}";',
                _ids(cell, cell_id),
            )
        )
    for cell, cell_id in zip(cells, ids, strict=False):
        lines.append(
            apply_identifier_substitutions(
                'LST GLTENCELL:IDTYPE=BYNAME,SRCLTENCELLNAME="{CELL}";',
                _ids(cell, cell_id),
            )
        )
    lines.extend(
        [
            apply_identifier_substitutions('LST GCELLPSCHM:IDTYPE=BYNAME,BTSNAME="{BTS}";', site),
            apply_identifier_substitutions('LST GCELLCHMGAD:IDTYPE=BYNAME,BTSNAME="{BTS}";', site),
            apply_identifier_substitutions('LST GCELLBASICPARA:IDTYPE=BYNAME,BTSNAME="{BTS}";', site),
            apply_identifier_substitutions('LST GCELLFREQ:IDTYPE=BYNAME,BTSNAME="{BTS}";', site),
            apply_identifier_substitutions('LST GCELLMAGRP:IDTYPE=BYNAME,BTSNAME="{BTS}";', site),
        ]
    )
    for cell, cell_id in zip(cells, ids, strict=False):
        lines.append(
            apply_identifier_substitutions(
                'LST GTRXHOP:IDTYPE=BYNAME,CELLNAME="{CELL}",TRXIDTYPE=BYID;',
                _ids(cell, cell_id),
            )
        )
    lines.extend(
        [
            apply_identifier_substitutions('LST GCELLHOPTP:IDTYPE=BYNAME,BTSNAME="{BTS}";', site),
            apply_identifier_substitutions("LST PTPBVC:;", site),
        ]
    )
    for cell, cell_id in zip(cells, ids, strict=False):
        lines.append(
            apply_identifier_substitutions(
                'LST GTRXDEV:IDTYPE=BYNAME,CELLNAME="{CELL}",TRXIDTYPE=BYID;',
                _ids(cell, cell_id),
            )
        )
    lines.append(apply_identifier_substitutions('LST GTRX:IDTYPE=BYNAME,BTSNAME="{BTS}";', site))
    for cell, cell_id in zip(cells, ids, strict=False):
        lines.append(
            apply_identifier_substitutions(
                'LST GTRXCHAN:IDTYPE=BYNAME,CELLNAME="{CELL}",TRXIDTYPE=BYID;',
                _ids(cell, cell_id),
            )
        )
    lines.extend(
        [
            apply_identifier_substitutions('LST GCELLGPRS:IDTYPE=BYNAME,BTSNAME="{BTS}";', site),
            apply_identifier_substitutions('DSP GCELLSTAT:IDTYPE=BYNAME,BTSNAMELST="{BTS}";', site),
        ]
    )
    for cell, cell_id in zip(cells, ids, strict=False):
        lines.append(
            apply_identifier_substitutions(
                'LST GCELLMAIOPLAN:IDTYPE=BYNAME,CELLNAME="{CELL}";',
                _ids(cell, cell_id),
            )
        )
    return "\n".join(lines) + "\n"


def gerencia_script(body: str, *, technology: str, site_name: str) -> str:
    """Format a script so Gerência can run it.

    The first line must start with ``//``. Each command carries the selected
    site as ``{SITE}``.
    """
    site = site_name.strip()
    label = {"2G": "2G", "3G": "3G", "4G": "4G LTE", "5G": "5G NR"}.get(technology, technology)
    header = f"//# --- {label} · {site} ---"
    suffix = f"{{{site}}}"
    lines = [header]
    for line in body.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or stripped.startswith("//"):
            continue
        if f"{{{site}}}" not in stripped:
            stripped = f"{stripped}{suffix}"
        lines.append(stripped)
    return "\n".join(lines) + "\n"


def _with_site(body: str, *, technology: str, site_name: str) -> str:
    site = (site_name or "").strip()
    if not site or not body.strip():
        return body
    return gerencia_script(body, technology=technology, site_name=site)


def generate_precheck_script(
    technology: str,
    *,
    site_name: str = "",
    cell_names: Sequence[str] | None = None,
) -> str:
    """Dispatch pre-check script generation by technology (5G only)."""
    if technology != "5G":
        return ""
    return _with_site(generate_precheck_5g_script(), technology=technology, site_name=site_name)


def generate_full_check_script(
    technology: str,
    *,
    site_name: str = "",
    cell_names: Sequence[str] | None = None,
    cell_ids: Sequence[str] | None = None,
    bsc: str = "",
    bts: str = "",
    enodeb_id: str = "",
) -> str:
    """Dispatch full-check (pos-check) script generation by technology."""
    if technology == "5G":
        body = generate_full_check_5g_script()
    elif technology == "4G":
        body = generate_full_check_4g_script(enodeb_id=enodeb_id)
    elif technology == "3G":
        body = generate_full_check_3g_script(
            site_name=site_name,
            cell_names=cell_names,
            cell_ids=cell_ids,
        )
    elif technology == "2G":
        body = generate_full_check_2g_script(
            bsc=bsc,
            bts=bts or site_name,
            site_name=site_name,
            cell_names=cell_names,
            cell_ids=cell_ids,
        )
    else:
        return ""
    return _with_site(body, technology=technology, site_name=site_name or bts)
