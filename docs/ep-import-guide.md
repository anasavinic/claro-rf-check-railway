# Claro EP import guide

How to import an Engineering Parameters (EP) workbook, find a site, and select the cells to analyze in Claro RF Check.

## Before you start

Prepare a Claro operations EP workbook:

- accepted format: `.xlsx` (legacy `.xls` is not supported);
- maximum size: 50 MB;
- use the regional or BASE file that matches the site;
- do not rename sheets or headers before import.

The file must contain these sheets:

- `RNP GSM (2G)`;
- `RNP UMTS (3G)`;
- `RNP LTE (4G)`;
- `RNP NR (5G)`.

Extra sheets are ignored. Required fields are listed in the [Claro EP schema](ep-schema.md).

## Open the selection

1. In the sidebar, select the technology.
2. Continue to **Site and cells**.
3. Find the **EP file** card.

Pre-check is available only when the selected technology is **5G NR**.

## Import the file

1. Drag the workbook onto the upload area or click to select it.
2. Wait until processing finishes.
3. Do not close or refresh the page while the file is uploading.

The screen shows that the EP is being analyzed. The application validates the format, sheets, and headers before the data is available.

## Confirm the import

When import succeeds:

- the file name appears on the **EP file** card;
- the detected region is shown;
- the cell count for the selected technology is shown;
- the **Sites found** list is filled.

Use **Replace file** to swap the workbook. A new import clears the current site and cell selection.

## Select the site

1. Search **Sites found** if needed.
2. Click the site to analyze.
3. Check technology, cell count, and status.

Selecting a site loads the **Site cells** panel automatically.

## Select the cells

1. Mark each cell that should be analyzed.
2. Use **Select all** for the visible cells.
3. Use **Clear** to remove the selection.
4. Check the count in **Selection summary**.

Changing the site clears the previous cell selection.

## Choose the check type

In **Check types**:

- **Pre-check**: initial validation, **5G NR only**;
- **Full Check**: full analysis for **5G NR** and **3G** (see [Full Check guide](poscheck-guide.md));
- both can be selected together on the 5G flow;
- on **3G**, only Full Check is available.

Continue is enabled only when there is:

- an EP processed successfully;
- a selected site;
- at least one selected cell;
- at least one check type.

## Review the summary

The side panel shows:

- technology;
- EP file;
- selected site;
- cell count;
- check types;
- next step.

Review those values before continuing.

## Common problems

### Invalid format

Use only `.xlsx`. A `.xls` file, or a file renamed to `.xlsx`, is rejected before processing starts.

### File larger than the limit

The limit is 50 MB. Request a regional or reduced workbook without changing its structure.

### Required sheet missing

Use a complete Claro EP with the four canonical sheets. Renaming a sheet is not enough if the expected fields are also missing.

### Required column missing

Compare the workbook with the [Claro EP schema](ep-schema.md) and get an updated file from the official source.

### Corrupt file

Open the workbook in Excel, confirm it is intact, and save it again in a supported format.

### Missing site or cell

Every data row needs both a site and a cell. The import fails as a whole and lists the sheet, row, and column. Nothing from that file is saved.

### Duplicate cell

The same technology, site, and cell should not appear twice. The import keeps the first occurrence, ignores later duplicates, and shows a warning so you can clean the workbook if needed.

### No sites found

Confirm:

- processing finished successfully;
- the correct technology is selected;
- the workbook contains rows for that technology;
- the search box is empty.

### Cells do not appear

Select a site and confirm that cells of the chosen technology are associated with it.

## Expected result

At the end of this flow, Claro RF Check keeps:

- the imported EP file;
- the region;
- the technology;
- the site;
- the selected cells;
- the parameters required by the next steps.
