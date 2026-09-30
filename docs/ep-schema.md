# Claro EP schema v1

Data contract for Claro SRAN Engineering Parameters (EP), inventoried from
`RNP_SRAN_{REGION}_{DATE}.xlsx` files (CO, ES, MG, NE, PRSC, BASE) in Aug 2026.

Legacy reference: the `vivo-rf-check` repository follows the same mental flow
(`import_ep` → sites → cells) with a **completely different Excel layout**.

## Diff vs Vivo RF Check

| Aspect | Vivo | Claro |
|---------|------|-------|
| Format | `.xlsb` (also `.xlsx`) | `.xlsx` only (legacy `.xls` is rejected) |
| Main sheets | `RF_GSM`, `RF_WCDMA`, `RF_LTE`, `RF_NR` | `RNP GSM (2G)`, `RNP UMTS (3G)`, `RNP LTE (4G)`, `RNP NR (5G)` |
| Region | Derived from site name / state | `REGION` column (alias `Region`) plus the file name |
| Legacy persistence | `ep.pkl` | PostgreSQL (`ImportJob` + records) |
| Typical size | Smaller | Regionals ~2–12 MB (UI mentions 10 MB; **technical limit: 50 MB**) |

## Canonical sheets (required)

Only these sheets enter the production parser. Extra regional sheets (`RMV_*`, `SITES 5G 2100`, backups)
are **ignored** (optional warning).

| Tech | Exact sheet name |
|------|------------------|
| 2G | `RNP GSM (2G)` |
| 3G | `RNP UMTS (3G)` |
| 4G | `RNP LTE (4G)` |
| 5G | `RNP NR (5G)` |

## Site / cell keys

| Tech | Site key | Cell key | On-air status |
|------|----------|----------|---------------|
| 2G | `*BTS NAME` (fallback `SINGLE RAN NAME`) | `*GSM CELL NAME` | `ON AIR (U2000)` |
| 3G | `NODEB NAME` (fallback `SINGLE RAN NAME`) | `CELLNAME` | `ON AIR (U2000)` |
| 4G | `ENODEBNAME` (fallback `SINGLE RAN NAME`) | `CELL NAME` | `ON AIR` |
| 5G | `ENODEB NAME` (fallback `SINGLE RAN NAME`) | `CELL NAME` | — (presence; no common on-air column) |

## Minimum required columns (layout gate)

Validation rejects the file if any column below is missing (after alias normalization).

### 2G — `RNP GSM (2G)`

`STATE`, `SINGLE RAN NAME`, `*BTS NAME`, `*GSM CELL NAME`, `*LAC`, `*CI`, `*FREQUENCY OF BCCH`, `BSC`

Aliases: `REGION`↔`Region`; `Responsible`↔`RESPONSIBLE`; `OBS`↔`Obs`↔`CGI` (optional).

### 3G — `RNP UMTS (3G)`

`REGION`, `STATE`, `SINGLE RAN NAME`, `NODEB NAME`, `CELLNAME`, `CELL ID`, `LAC`, `SAC`, `RNC ID`, `RNC NAME`, `PSCRAMBCODE`, `UARFCN DOWNLINK`

### 4G — `RNP LTE (4G)`

`REGION`, `STATE`, `SINGLE RAN NAME`, `ENODEBNAME`, `CELL NAME`, `CELL ID`, `ENODEB ID`, `TAC`, `EARFCN_DL`, `PCI`

### 5G — `RNP NR (5G)`

`REGION`, `STATE`, `SINGLE RAN NAME`, `ENODEB NAME`, `CELL NAME`, `gNBId`, `CellId`, `FrequencyBand`, `PhysicalCellId`, `DlNarfcn`, `Tracking Area ID`

## Known aliases (regional files differ from BASE)

Sheet header aliases stay as they appear in the workbook. Do not translate them.

| Canonical | Observed alternatives |
|----------|-------------------------|
| `REGION` | `Region` |
| `RESPONSIBLE` | `Responsible` |
| `OBS` | `Obs`, `Obs.:`, `obs`, `Comentário` |
| `CGI` | `CONFIRMAÇÃO DE CGI` |

## Region detection from the file name

Regex: `RNP_SRAN_(CO|ES|MG|NE|PRSC|BASE)[_-]`

Priority: `REGION` column value on the rows, then the file name.

## Volume (Aug 2026 sample)

| File | MB | 2G rows | 3G rows | 4G rows | 5G rows |
|---------|----|---------|---------|---------|---------|
| CO | 12.3 | ~8k | ~21k | ~34k | ~6k |
| ES | 1.8 | ~1.5k | — | — | ~1k |
| MG | 12.2 | ~8k | — | — | ~3.7k |
| NE | 9.9 | ~7k | — | — | ~5k |
| PRSC | 7.9 | ~7k | — | — | ~4k |
| BASE | 4.5 | ~3k | — | — | ~2k |

Regional imports must run **asynchronously (Celery)**.

## Output contract for checks

```json
{
  "import_job_id": "uuid",
  "filename": "RNP_SRAN_CO_20260813.xlsx",
  "region": "CO",
  "technology": "5G",
  "sites": ["ES02ACEPT02", "..."],
  "cells_by_site": {
    "ES02ACEPT02": [
      {"cell_name": "52S02ACEPT0201", "raw": { }, "checked": false}
    ]
  },
  "counts": {"2G": 0, "3G": 0, "4G": 0, "5G": 6328}
}
```

Cell selection happens in the analysis flow. Import exposes `sites`, normalized cells,
and the `raw` payload for each technology.

### `raw` contract (JSON)

Excel values are coerced to JSON-safe types before `raw` is stored:

| openpyxl type | Stored in `raw` |
|---------------|---------------------|
| `datetime` | ISO string (`2026-08-13T14:30:00`) |
| `date` | ISO string (`2026-08-13`) |
| `time` | ISO string (`14:30:00`) |
| `Decimal` | `int` when integral, otherwise `float` |
| `timedelta` | total seconds (`float`) |

Columns such as `LAST UPDATE` therefore arrive as an ISO string in `EpCell.raw`, not as a `datetime` object.

## Import rules

- Only `.xlsx` is accepted. The upload is checked as an Office Open XML package, not only by extension.
- A data row missing site or cell fails the whole file. No cells are stored.
- `(technology, site, cell)` must be unique in the job. The database enforces the same rule.
- The stored file, job, cells, and linked analyses are removed 15 days after import
  (`EP_IMPORT_RETENTION_DAYS`). `expires_at` is set at job creation and is **not**
  renewed when a new analysis runs or when a Gerência return is replaced.
