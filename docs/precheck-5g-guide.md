# 5G pre-check guide

How to run the Claro RF Check 5G pre-check, from data selection through the result.

Pre-check validates `gNodeB ID` and `Tracking Area Code` against the network using the commands authorized for Claro operations.

## When to use it

Run pre-check before other 5G analyses to confirm that basic network data matches the EP.

Pre-check:

- is available only for **5G NR**;
- uses a Claro EP that imported and processed successfully;
- requires a site and at least one cell;
- processes only the commands defined for this validation;
- blocks the next step when it finds a failure or inconsistency.

It does not run monitoring or 2G/4G analysis. Full Check for 5G and 3G is documented in the [Full Check (pos-check) guide](poscheck-guide.md).

## 1. Prepare the analysis

1. In the sidebar, select **5G NR**.
2. Import a valid EP.
3. Select the site.
4. Mark the cells to analyze.
5. In **Check types**, select **Pre-check**.
6. Review **Selection summary**.
7. Click **Generate scripts**.

See the [EP import guide](ep-import-guide.md) for upload and selection details.

## 2. Review the scripts

On **Generated scripts**, the stepper shows:

- Technology completed;
- Site and cells completed;
- Script active;
- Result pending.

The pre-check script contains only:

```text
LST GNODEBFUNCTION:;
LST GNBTRACKINGAREA:;
```

Use:

- **Copy script** to put the content on the clipboard;
- **Download script** to save the file locally.

Do not add Full Check commands to the pre-check return.

## 3. Run the script in Gerência

1. Run the script in the Gerência system that owns the selected site.
2. Wait until both commands finish.
3. Confirm that the return contains the commands and their results.
4. Save the return file without editing headers or values.

The return must identify:

- `gNodeB ID` in `LST GNODEBFUNCTION`;
- `Tracking Area Code` in `LST GNBTRACKINGAREA`;
- the execution status of each command.

## 4. Import the return

1. Return to Claro RF Check.
2. In **Import results**, find **Pre-check result**.
3. Drag the file or click the upload area.
4. Wait for file validation.
5. Click **Process analysis**.

The button stays disabled until the required return is available.

If Full Check was also selected, import each result in its own field. The monitoring return is not required for pre-check.

## 5. Follow processing

While processing, the application:

1. reads the file;
2. locates both commands;
3. checks execution status;
4. interprets the returned values;
5. compares those values with the EP;
6. consolidates the result.

Do not upload the same file again while the analysis is processing.

## 6. Read the result

On the **Result** step, check:

- overall status;
- validation count;
- consistent items;
- inconsistencies;
- failures;
- expected EP value;
- value found on the network;
- the note for each validation.

The validations are:

### gNodeB ID

Compares EP `gNBId` with `gNodeB ID` from `LST GNODEBFUNCTION`.

### Tracking Area Code

Compares EP `Tracking Area ID` with `Tracking Area Code` from `LST GNBTRACKINGAREA`.

Use status filters and search to find a specific validation.

## 7. Export or share the result

When the analysis is **Completed** or **Inconsistent**, use the cards at the bottom of the result page:

- **Export Report** downloads an Excel workbook with the same summary, validations, OK, warnings, and NOK shown on screen.
- **Prepare Email** downloads an Outlook draft (`.eml`) with that summary in the body and the Excel file attached.

Execution failures cannot be exported. Both actions use the consolidated result stored for the analysis, including Full Check when it is part of the same run.

## Status meanings

### Completed

The file was interpreted and every expected value is consistent. The data can be used by later steps.

### Inconsistent

The file was processed, but at least one network value differs from the EP. The table shows expected, found, and the note.

The next step stays blocked until the cause is fixed and pre-check is run again.

### Execution failure

Processing could not finish. Examples:

- unreadable file;
- unrecognized return format;
- missing command;
- command executed with an error;
- return with no records;
- required field missing.

## Run again after a failure

On the failure screen:

1. check **Run information**;
2. read the **Reason**;
3. open **View technical details** if needed;
4. use **Run again** to repeat processing;
5. use **Back to configuration** if you need to change the selection or the files.

The EP and valid files stay attached to the analysis so you do not have to configure it again.

## Fix an inconsistency

1. Identify the validation that diverges.
2. Compare **Expected value** and **Found value**.
3. Confirm that the imported EP is the correct version.
4. Validate the site configuration in Gerência.
5. Correct the right source according to the operational process.
6. Generate or run the commands again.
7. Import the new return and reprocess the analysis.

Do not edit the return file to force the values to match.

## Common problems

### Pre-check is missing

Confirm that the selected technology is **5G NR**.

### Generate scripts is disabled

Confirm that:

- the EP was processed;
- a site is selected;
- at least one cell is marked;
- Pre-check is selected.

### Process analysis is disabled

Import a file in **Pre-check result** and wait for upload validation.

### Missing command

Run the full script again. The file must contain the returns for `LST GNODEBFUNCTION` and `LST GNBTRACKINGAREA`.

### Return has no records

Confirm that the script ran in Gerência against the correct site.

### Wrong site

Go back to configuration, select the site that matches the return, and generate a new script.

## Good practice

- always use the latest official EP;
- do not change the generated script;
- keep the original Gerência return;
- check the site before running the commands;
- do not mix returns from different sites;
- do not use a Full Check return as a pre-check return;
- rerun the analysis after any correction.

## Expected result

At the end, the user can see whether:

- the commands were processed;
- `gNodeB ID` is consistent;
- `Tracking Area Code` is consistent;
- failures block validation;
- the analysis is released for the next modules.
