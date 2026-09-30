# Full Check (pos-check) guide

How to run Claro RF Check Full Check (also called pos-check) for **5G NR**, **4G**, **3G**, and **2G**.

Full Check validates site and cell parameters from a Gerência MML return against the imported EP. It lives in the `poscheck` Django app, with technology-specific engines for each supported radio technology.

## When to use it

Use Full Check when you need a broader validation than Pre-check:

| Technology | Full Check | Pre-check |
|------------|------------|-----------|
| 5G NR | Yes | Yes (separate module) |
| 4G | Yes | Not available |
| 3G | Yes | Not available |
| 2G | Yes | Not available |

On 5G you can select Pre-check, Full Check, or both. On 4G, 3G, and 2G only Full Check is available.

## 1. Prepare the analysis

1. In the sidebar, select **5G NR**, **4G**, **3G**, or **2G**.
2. Import a valid EP.
3. Select the site and at least one cell.
4. In **Check types**, select **Full Check** (and optionally **Pre-check** on 5G).
5. Click **Generate scripts**.

## 2. Review the scripts

The Full Check script is technology-specific:

- **5G**: approved Claro command list (`DSP NRDUCELL`, `LST NRCELL`, `LST GNODEBFUNCTION`, …).
- **4G**: site-wide LTE commands (`LST CELL`, `LST ENODEBFUNCTION`, `LST CNOPERATORTA`, …) with `ENODEBID` on neighbor lists.
- **3G**: site commands (`LST UCELL`, `LST UCNOPERATOR`, …) plus per-cell commands with the EP `CELL ID`.
- **2G**: site and per-cell GSM commands with BSC/BTS/CELL identifiers.

Copy or download the script, then run it in Gerência without editing the return.

## 3. Import the return

1. Open **Import results**.
2. Upload the Full Check return (`.txt` / `.log`, max 10 MB).
3. If Pre-check was also selected, upload that return in its own field.
4. Click **Process analysis**.

## 4. Read the result

The Full Check result lists validations such as:

### 5G

- `gNodeB ID` and Tracking Area Code vs EP
- Per selected cell: Cell ID, Frequency Band, Physical Cell ID, Downlink NARFCN
- Cell Activate State (`Activated`) and NR DU Cell State (`Normal`)
- Each Full Check command with `RETCODE=0`

### 4G

- eNodeB ID and TAC vs EP
- Per selected cell: Cell Name, Cell ID, PCI
- Site-wide Full Check commands with `RETCODE=0`

### 3G

- RNC ID, Cell Name, Cell ID vs EP
- Site and per-cell commands with `RETCODE=0`

### 2G

- BSC, BTS, and per-cell identifiers vs EP
- Site and per-cell commands with `RETCODE=0`

Statuses:

- **Completed** — all validations consistent
- **Inconsistent** — at least one value differs from the EP
- **Execution failure** — missing command, empty return, or parse failure

Completed and inconsistent results can be exported as Excel or shared as an Outlook draft from the result page. The file uses the same consolidated validations shown in the table.

## Combined RF Check (multi-technology)

Use **Combined RF check** in the sidebar (or the Home card) when you need to validate more than one technology in a single flow.

1. Select at least two technologies (2G / 3G / 4G / 5G NR).
2. Import an EP and select one or more sites. All cells for the chosen technologies at each site are included.
3. Generate and run the aggregated Pre-check (5G only) and Full Check scripts in Gerência.
4. Import the return files and process. Results are consolidated with filters by technology.

Under the hood, the app creates one `CheckAnalysis` per technology × site and reuses the existing Pre-check / Full Check engines.

## Combined 5G Pre-check + Full Check

When both are selected:

1. Both returns are required before processing.
2. Pre-check runs first.
3. If Pre-check fails or is inconsistent, Full Check does not run.
4. If Pre-check completes, Full Check runs and the analysis status is the worse of the two outcomes.

## Architecture

```text
App
 └── poscheck
      ├── 5G (parser + validator)
      ├── 4G (parser + validator)
      ├── 3G (parser + validator)
      ├── 2G (parser + validator)
      └── View (result / failure)
```

Shared selection and return files stay on `CheckAnalysis` / `CheckReturnFile` in the `precheck` app. Full Check outcomes are stored in `PoscheckResult`.
