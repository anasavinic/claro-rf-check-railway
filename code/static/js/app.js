document.addEventListener("alpine:init", () => {
    async function parseJsonResponse(response) {
        const text = await response.text();
        try {
            return text ? JSON.parse(text) : {};
        } catch (error) {
            return {
                type: "Error",
                title: "Request failed",
                message: "The server returned an unexpected error. Refresh and try again.",
            };
        }
    }

    async function pollCheckExecution(statusUrl, csrfToken) {
        const maxAttempts = 300;
        let consecutiveFailures = 0;
        for (let attempt = 0; attempt < maxAttempts; attempt += 1) {
            await new Promise((resolve) => setTimeout(resolve, 1000));
            let response;
            try {
                response = await fetch(statusUrl, {
                    method: "GET",
                    headers: {
                        Accept: "application/json",
                        "X-CSRFToken": csrfToken,
                        "X-Requested-With": "XMLHttpRequest",
                    },
                });
            } catch (error) {
                consecutiveFailures += 1;
                if (consecutiveFailures >= 5) {
                    return {
                        type: "Error",
                        title: "Could not process",
                        message: "The server did not respond. Try again.",
                    };
                }
                continue;
            }
            const data = await parseJsonResponse(response);
            if (!response.ok || data.type === "Error") {
                consecutiveFailures += 1;
                if (consecutiveFailures >= 5) {
                    return data.type === "Error"
                        ? data
                        : {
                              type: "Error",
                              title: "Could not process",
                              message: data.message || "Processing failed.",
                          };
                }
                continue;
            }
            consecutiveFailures = 0;
            const status = data.execution?.status;
            if (status === "success" || status === "failed") {
                return data;
            }
            if (data.finished) {
                return data;
            }
        }
        return {
            type: "Error",
            title: "Could not process",
            message: "Processing is taking longer than expected. Refresh and try again.",
        };
    }

    async function processCheckRequest(processUrl, csrfToken) {
        const response = await fetch(processUrl, {
            method: "POST",
            headers: {
                Accept: "application/json",
                "X-CSRFToken": csrfToken,
                "X-Requested-With": "XMLHttpRequest",
            },
        });
        let data = await parseJsonResponse(response);
        if (response.status === 202 && data.status_url) {
            data = await pollCheckExecution(data.status_url, csrfToken);
            const status = data.execution?.status;
            const ok =
                data.type !== "Error" &&
                (status === "success" ||
                    status === "failed" ||
                    Boolean(data.redirect_url) ||
                    Boolean(data.finished));
            return { response, data, ok };
        }
        return { response, data, ok: response.ok };
    }

    Alpine.data("toast", () => ({
        visible: false,
        type: "info",
        title: "",
        message: "",
        timer: null,

        get toastDotClass() {
            if (this.type === "success") return "bg-green";
            if (this.type === "error") return "bg-danger";
            return "bg-blue";
        },

        show(event) {
            const detail = event?.detail || {};
            this.type = detail.type || "info";
            this.title = detail.title || "";
            this.message = detail.message || "";
            this.visible = true;
            clearTimeout(this.timer);
            this.timer = setTimeout(() => (this.visible = false), 5000);
        },
    }));

    Alpine.data("epSiteCells", () => ({
        technology: "5G",
        techLabel: "5G NR",
        uploadUrl: "",
        generateScriptsUrl: "",
        jobId: "",
        epFileName: "",
        csrfToken: "",
        selectedSite: "",
        selectedCells: [],
        allCellNames: [],
        preCheck: false,
        fullCheck: false,
        uploading: false,
        generating: false,

        init() {
            const el = this.$el;
            this.technology = el.dataset.technology || "5G";
            this.techLabel = el.dataset.techLabel || "5G NR";
            this.uploadUrl = el.dataset.uploadUrl || "";
            this.generateScriptsUrl = el.dataset.generateScriptsUrl || "";
            this.jobId = el.dataset.jobId || "";
            this.epFileName = el.dataset.epFileName || "";
            this.csrfToken = el.dataset.csrfToken || "";
            if (this.technology !== "5G") {
                this.preCheck = false;
            }
        },

        get hasCheckSelection() {
            if (this.technology === "5G") {
                return this.preCheck || this.fullCheck;
            }
            return this.fullCheck;
        },

        get canContinue() {
            return Boolean(
                this.jobId &&
                    this.selectedSite &&
                    this.selectedCells.length &&
                    this.hasCheckSelection
            );
        },

        get cannotContinue() {
            return !this.canContinue || this.generating;
        },

        get continueButtonClass() {
            return this.canContinue && !this.generating
                ? "bg-primary text-white cursor-pointer"
                : "bg-disabled text-disabled-text cursor-not-allowed";
        },

        get continueButtonLabel() {
            if (this.generating) return "Generating...";
            return this.canContinue ? "Generate scripts" : "Continue";
        },

        get nextStepLabel() {
            if (!this.epFileName) return "Waiting for EP file";
            if (!this.selectedSite) return "Select a site";
            if (!this.selectedCells.length) return "Select the cells";
            if (!this.hasCheckSelection) return "Choose the check type";
            return "Generate script";
        },

        get epFileNameDisplay() {
            return this.epFileName || "--";
        },

        get epFileNameClass() {
            return this.epFileName ? "text-dark-blue" : "text-muted";
        },

        get selectedSiteDisplay() {
            return this.selectedSite || "--";
        },

        get selectedSiteClass() {
            return this.selectedSite ? "text-dark-blue" : "text-muted";
        },

        get selectedCellsLabel() {
            if (!this.selectedCells.length) return "--";
            return this.selectedCells.length + " selected";
        },

        get selectedCellsClass() {
            return this.selectedCells.length ? "text-dark-blue" : "text-muted";
        },

        get showCheckSummary() {
            return this.hasCheckSelection;
        },

        get showPreCheckBadge() {
            return this.technology === "5G" && this.preCheck;
        },

        get showBothCheckSeparator() {
            return this.technology === "5G" && this.preCheck && this.fullCheck;
        },

        get showFullCheckBadge() {
            return this.fullCheck;
        },

        onDrop(event) {
            const file = event.dataTransfer?.files?.[0];
            if (file) this.uploadFile(file);
        },

        onFileSelected(event) {
            const file = event.target.files?.[0];
            if (file) this.uploadFile(file);
            event.target.value = "";
        },

        pickFile() {
            this.$refs.fileInput?.click();
        },

        async uploadFile(file) {
            if (this.uploading) return;
            this.uploading = true;
            const formData = new FormData();
            formData.append("file", file);
            formData.append("technology", this.technology);

            try {
                const response = await fetch(this.uploadUrl, {
                    method: "POST",
                    headers: {
                        Accept: "application/json",
                        "X-Requested-With": "XMLHttpRequest",
                        "X-CSRFToken": this.csrfToken,
                    },
                    body: formData,
                });
                const data = await parseJsonResponse(response);
                if (!response.ok || data.type === "Error") {
                    window.dispatchEvent(
                        new CustomEvent("notify", {
                            detail: {
                                type: "error",
                                title: data.title || "Upload error",
                                message: data.message || "Failed to upload the EP file.",
                            },
                        })
                    );
                    return;
                }
                this.jobId = data.job?.id || "";
                this.epFileName = data.job?.filename || file.name;
                this.selectedSite = "";
                this.selectedCells = [];
                window.dispatchEvent(
                    new CustomEvent("notify", {
                        detail: {
                            type: "success",
                            title: data.title || "EP imported",
                            message: data.message || "File processed successfully.",
                        },
                    })
                );
                if (data.redirect_url) {
                    window.location.href = data.redirect_url;
                }
            } catch (error) {
                window.dispatchEvent(
                    new CustomEvent("notify", {
                        detail: {
                            type: "error",
                            title: "Upload error",
                            message: String(error),
                        },
                    })
                );
            } finally {
                this.uploading = false;
            }
        },

        selectSite(event) {
            this.selectedSite = event.currentTarget.dataset.site || "";
            this.selectedCells = [];
            this.allCellNames = [];
        },

        toggleCell(event) {
            const cellName = event.currentTarget.dataset.cell;
            if (!cellName) return;
            if (this.selectedCells.includes(cellName)) {
                this.selectedCells = this.selectedCells.filter((c) => c !== cellName);
            } else {
                this.selectedCells = [...this.selectedCells, cellName];
            }
        },

        selectAllCells() {
            const names = [
                ...document.querySelectorAll("#cells-panel .cell-row"),
            ]
                .map((row) => row.dataset.cell || row.querySelector("td:nth-child(2)")?.textContent?.trim())
                .filter(Boolean);
            this.selectedCells = names;
            this.allCellNames = names;
            this.syncCellCheckboxes();
        },

        clearCells() {
            this.selectedCells = [];
            this.syncCellCheckboxes();
        },

        async generateScripts() {
            if (!this.canContinue || this.generating) return;
            this.generating = true;

            try {
                const response = await fetch(this.generateScriptsUrl, {
                    method: "POST",
                    headers: {
                        Accept: "application/json",
                        "Content-Type": "application/json",
                        "X-CSRFToken": this.csrfToken,
                    },
                    body: JSON.stringify({
                        job_id: this.jobId,
                        technology: this.technology,
                        site: this.selectedSite,
                        cells: this.selectedCells,
                        pre_check: this.preCheck,
                        full_check: this.fullCheck,
                    }),
                });
                const data = await parseJsonResponse(response);
                if (!response.ok || data.type === "Error") {
                    window.dispatchEvent(
                        new CustomEvent("notify", {
                            detail: {
                                type: "error",
                                title: data.title || "Could not generate scripts",
                                message: data.message || "Could not generate the scripts.",
                            },
                        })
                    );
                    return;
                }
                window.location.href = data.redirect_url;
            } catch (error) {
                window.dispatchEvent(
                    new CustomEvent("notify", {
                        detail: {
                            type: "error",
                            title: "Could not generate scripts",
                            message: String(error),
                        },
                    })
                );
            } finally {
                this.generating = false;
            }
        },

        syncCellCheckboxes() {
            document.querySelectorAll("#cells-panel input[data-cell]").forEach((input) => {
                input.checked = this.selectedCells.includes(input.dataset.cell);
            });
        },

        filterCells(event) {
            const q = (event.target.value || "").toLowerCase();
            document.querySelectorAll("#cells-panel .cell-row").forEach((row) => {
                const name = row.getAttribute("data-name") || "";
                row.style.display = !q || name.includes(q) ? "" : "none";
            });
        },
    }));

    Alpine.data("scriptsPage", () => ({
        csrfToken: "",
        uploadUrl: "",
        uploadFullCheckUrl: "",
        processUrl: "",
        canImport: false,
        requiresPrecheck: false,
        requiresFullCheck: false,
        hasPrecheckFile: false,
        hasFullCheckFile: false,
        precheckFilename: "",
        fullCheckFilename: "",
        uploading: false,
        processing: false,

        init() {
            const el = this.$el;
            this.csrfToken = el.dataset.csrfToken || "";
            this.uploadUrl = el.dataset.uploadUrl || "";
            this.uploadFullCheckUrl = el.dataset.uploadFullCheckUrl || "";
            this.processUrl = el.dataset.processUrl || "";
            this.canImport = el.dataset.canImport === "true";
            this.requiresPrecheck = el.dataset.requiresPrecheck === "true";
            this.requiresFullCheck = el.dataset.requiresFullCheck === "true";
            this.hasPrecheckFile = el.dataset.hasPrecheckReturn === "true";
            this.hasFullCheckFile = el.dataset.hasFullCheckReturn === "true";
            this.precheckFilename = el.dataset.precheckFilename || "";
            this.fullCheckFilename = el.dataset.fullCheckFilename || "";
        },

        get hasRequiredFiles() {
            const preOk = !this.requiresPrecheck || this.hasPrecheckFile;
            const fullOk = !this.requiresFullCheck || this.hasFullCheckFile;
            return preOk && fullOk;
        },

        get cannotProcess() {
            return !this.canImport || !this.hasRequiredFiles || this.uploading || this.processing;
        },

        get showPrecheckDropzone() {
            return this.canImport && this.requiresPrecheck && !this.hasPrecheckFile;
        },

        get showPrecheckFileCard() {
            return this.canImport && this.requiresPrecheck && this.hasPrecheckFile;
        },

        get showFullCheckDropzone() {
            return this.canImport && this.requiresFullCheck && !!this.uploadFullCheckUrl && !this.hasFullCheckFile;
        },

        get showFullCheckFileCard() {
            return this.canImport && this.requiresFullCheck && !!this.uploadFullCheckUrl && this.hasFullCheckFile;
        },

        get processButtonClass() {
            return this.cannotProcess
                ? "bg-disabled text-disabled-text cursor-not-allowed"
                : "bg-primary text-white cursor-pointer";
        },

        get processButtonLabel() {
            return this.processing ? "Processing…" : "Process analysis";
        },

        async copyScript(text) {
            try {
                await navigator.clipboard.writeText(text);
                window.dispatchEvent(
                    new CustomEvent("notify", {
                        detail: {
                            type: "success",
                            title: "Script copied",
                            message: "The content was copied to the clipboard.",
                        },
                    })
                );
            } catch (error) {
                window.dispatchEvent(
                    new CustomEvent("notify", {
                        detail: {
                            type: "error",
                            title: "Could not copy",
                            message: String(error),
                        },
                    })
                );
            }
        },

        copyPreCheck() {
            this.copyScript(this.$refs.preCheckScript?.textContent || "");
        },

        copyFullCheck() {
            this.copyScript(this.$refs.fullCheckScript?.textContent || "");
        },

        pickPrecheckFile() {
            this.$refs.precheckFileInput?.click();
        },

        pickFullCheckFile() {
            this.$refs.fullCheckFileInput?.click();
        },

        onPrecheckDrop(event) {
            const file = event.dataTransfer?.files?.[0];
            if (file) this.uploadFile(file, "precheck");
        },

        onFullCheckDrop(event) {
            const file = event.dataTransfer?.files?.[0];
            if (file) this.uploadFile(file, "fullcheck");
        },

        onPrecheckFileSelected(event) {
            const file = event.target?.files?.[0];
            if (file) this.uploadFile(file, "precheck");
            if (event.target) event.target.value = "";
        },

        onFullCheckFileSelected(event) {
            const file = event.target?.files?.[0];
            if (file) this.uploadFile(file, "fullcheck");
            if (event.target) event.target.value = "";
        },

        async uploadFile(file, kind) {
            if (!this.canImport || this.uploading || this.processing) return;
            const url = kind === "fullcheck" ? this.uploadFullCheckUrl : this.uploadUrl;
            if (!url) return;
            this.uploading = true;
            const body = new FormData();
            body.append("file", file);
            try {
                const response = await fetch(url, {
                    method: "POST",
                    headers: {
                        Accept: "application/json",
                        "X-CSRFToken": this.csrfToken,
                        "X-Requested-With": "XMLHttpRequest",
                    },
                    body,
                });
                const data = await parseJsonResponse(response);
                if (!response.ok || data.type === "Error") {
                    window.dispatchEvent(
                        new CustomEvent("notify", {
                            detail: {
                                type: "error",
                                title: data.title || "Upload error",
                                message: data.message || "Could not upload the return file.",
                            },
                        })
                    );
                    return;
                }
                if (kind === "fullcheck") {
                    this.hasFullCheckFile = true;
                    this.fullCheckFilename = data.filename || file.name;
                } else {
                    this.hasPrecheckFile = true;
                    this.precheckFilename = data.filename || file.name;
                }
                window.dispatchEvent(
                    new CustomEvent("notify", {
                        detail: {
                            type: "success",
                            title: data.title || "Return imported",
                            message: data.message || "File uploaded successfully.",
                        },
                    })
                );
            } catch (error) {
                window.dispatchEvent(
                    new CustomEvent("notify", {
                        detail: {
                            type: "error",
                            title: "Upload error",
                            message: String(error),
                        },
                    })
                );
            } finally {
                this.uploading = false;
            }
        },

        async processAnalysis() {
            if (this.cannotProcess) return;
            this.processing = true;
            try {
                const { data, ok } = await processCheckRequest(this.processUrl, this.csrfToken);
                if (!ok || data.type === "Error") {
                    if (data.redirect_url) {
                        window.location.href = data.redirect_url;
                        return;
                    }
                    window.dispatchEvent(
                        new CustomEvent("notify", {
                            detail: {
                                type: "error",
                                title: data.title || "Could not process",
                                message: data.message || "Processing failed.",
                            },
                        })
                    );
                    return;
                }
                if (data.redirect_url) {
                    window.location.href = data.redirect_url;
                    return;
                }
                window.dispatchEvent(
                    new CustomEvent("notify", {
                        detail: {
                            type: "success",
                            title: data.title || "Analysis ready",
                            message: data.message || "Processing finished.",
                        },
                    })
                );
            } catch (error) {
                window.dispatchEvent(
                    new CustomEvent("notify", {
                        detail: {
                            type: "error",
                            title: "Could not process",
                            message: String(error),
                        },
                    })
                );
            } finally {
                this.processing = false;
            }
        },
    }));

    Alpine.data("returnsPage", () => ({
        csrfToken: "",
        uploadUrl: "",
        uploadFullCheckUrl: "",
        processUrl: "",
        requiresPrecheck: false,
        requiresFullCheck: false,
        hasPrecheckFile: false,
        hasFullCheckFile: false,
        precheckFilename: "",
        fullCheckFilename: "",
        uploading: false,
        processing: false,

        init() {
            const el = this.$el;
            this.csrfToken = el.dataset.csrfToken || "";
            this.uploadUrl = el.dataset.uploadUrl || "";
            this.uploadFullCheckUrl = el.dataset.uploadFullCheckUrl || "";
            this.processUrl = el.dataset.processUrl || "";
            this.requiresPrecheck = el.dataset.requiresPrecheck === "true";
            this.requiresFullCheck = el.dataset.requiresFullCheck === "true";
            this.hasPrecheckFile = el.dataset.hasPrecheckReturn === "true";
            this.hasFullCheckFile = el.dataset.hasFullCheckReturn === "true";
            this.precheckFilename = el.dataset.precheckFilename || "";
            this.fullCheckFilename = el.dataset.fullCheckFilename || "";
        },

        get hasRequiredFiles() {
            const preOk = !this.requiresPrecheck || this.hasPrecheckFile;
            const fullOk = !this.requiresFullCheck || this.hasFullCheckFile;
            return preOk && fullOk;
        },

        get cannotProcess() {
            return !this.hasRequiredFiles || this.uploading || this.processing;
        },

        get showPrecheckDropzone() {
            return this.requiresPrecheck && !this.hasPrecheckFile;
        },

        get showPrecheckFileCard() {
            return this.requiresPrecheck && this.hasPrecheckFile;
        },

        get showFullCheckDropzone() {
            return this.requiresFullCheck && !!this.uploadFullCheckUrl && !this.hasFullCheckFile;
        },

        get showFullCheckFileCard() {
            return this.requiresFullCheck && !!this.uploadFullCheckUrl && this.hasFullCheckFile;
        },

        get processButtonClass() {
            return this.cannotProcess
                ? "bg-disabled text-disabled-text cursor-not-allowed"
                : "bg-primary text-white cursor-pointer";
        },

        get processButtonLabel() {
            return this.processing ? "Processing…" : "Process analysis";
        },

        pickPrecheckFile() {
            this.$refs.precheckFileInput?.click();
        },

        pickFullCheckFile() {
            this.$refs.fullCheckFileInput?.click();
        },

        onPrecheckDrop(event) {
            const file = event.dataTransfer?.files?.[0];
            if (file) this.uploadFile(file, "precheck");
        },

        onFullCheckDrop(event) {
            const file = event.dataTransfer?.files?.[0];
            if (file) this.uploadFile(file, "fullcheck");
        },

        onPrecheckFileSelected(event) {
            const file = event.target?.files?.[0];
            if (file) this.uploadFile(file, "precheck");
            if (event.target) event.target.value = "";
        },

        onFullCheckFileSelected(event) {
            const file = event.target?.files?.[0];
            if (file) this.uploadFile(file, "fullcheck");
            if (event.target) event.target.value = "";
        },

        async uploadFile(file, kind) {
            if (this.uploading || this.processing) return;
            const url = kind === "fullcheck" ? this.uploadFullCheckUrl : this.uploadUrl;
            if (!url) return;
            this.uploading = true;
            const body = new FormData();
            body.append("file", file);
            try {
                const response = await fetch(url, {
                    method: "POST",
                    headers: {
                        Accept: "application/json",
                        "X-CSRFToken": this.csrfToken,
                        "X-Requested-With": "XMLHttpRequest",
                    },
                    body,
                });
                const data = await parseJsonResponse(response);
                if (!response.ok || data.type === "Error") {
                    window.dispatchEvent(
                        new CustomEvent("notify", {
                            detail: {
                                type: "error",
                                title: data.title || "Upload error",
                                message: data.message || "Could not upload the return file.",
                            },
                        })
                    );
                    return;
                }
                if (kind === "fullcheck") {
                    this.hasFullCheckFile = true;
                    this.fullCheckFilename = data.filename || file.name;
                } else {
                    this.hasPrecheckFile = true;
                    this.precheckFilename = data.filename || file.name;
                }
                window.dispatchEvent(
                    new CustomEvent("notify", {
                        detail: {
                            type: "success",
                            title: data.title || "Return imported",
                            message: data.message || "File uploaded successfully.",
                        },
                    })
                );
            } catch (error) {
                window.dispatchEvent(
                    new CustomEvent("notify", {
                        detail: {
                            type: "error",
                            title: "Upload error",
                            message: String(error),
                        },
                    })
                );
            } finally {
                this.uploading = false;
            }
        },

        async processAnalysis() {
            if (this.cannotProcess) return;
            this.processing = true;
            try {
                const { data, ok } = await processCheckRequest(this.processUrl, this.csrfToken);
                if (!ok || data.type === "Error") {
                    window.dispatchEvent(
                        new CustomEvent("notify", {
                            detail: {
                                type: "error",
                                title: data.title || "Could not process",
                                message: data.message || "Could not process the analysis.",
                            },
                        })
                    );
                    return;
                }
                if (data.redirect_url) {
                    window.location.href = data.redirect_url;
                }
            } catch (error) {
                window.dispatchEvent(
                    new CustomEvent("notify", {
                        detail: {
                            type: "error",
                            title: "Could not process",
                            message: String(error),
                        },
                    })
                );
            } finally {
                this.processing = false;
            }
        },
    }));

    Alpine.data("failurePage", () => ({
        csrfToken: "",
        processUrl: "",
        running: false,
        showDetails: false,

        init() {
            const el = this.$el;
            this.csrfToken = el.dataset.csrfToken || "";
            this.processUrl = el.dataset.processUrl || "";
        },

        get buttonLabel() {
            return this.running ? "Processing…" : "Run again";
        },

        get detailsLabel() {
            return this.showDetails ? "Hide technical details" : "View technical details";
        },

        toggleDetails() {
            this.showDetails = !this.showDetails;
        },

        async runAgain() {
            if (this.running) return;
            this.running = true;
            try {
                const { data, ok } = await processCheckRequest(this.processUrl, this.csrfToken);
                if (!ok || data.type === "Error") {
                    window.dispatchEvent(
                        new CustomEvent("notify", {
                            detail: {
                                type: "error",
                                title: data.title || "Could not process",
                                message: data.message || "Could not process the analysis.",
                            },
                        })
                    );
                    return;
                }
                if (data.redirect_url) {
                    window.location.href = data.redirect_url;
                }
            } catch (error) {
                window.dispatchEvent(
                    new CustomEvent("notify", {
                        detail: {
                            type: "error",
                            title: "Could not process",
                            message: String(error),
                        },
                    })
                );
            } finally {
                this.running = false;
            }
        },
    }));

    Alpine.data("resultPage", () => ({
        filter: "all",
        query: "",
        rows: [],
        totalCount: 0,
        consistentCount: 0,
        inconsistentCount: 0,
        failedCount: 0,
        exportUrl: "",
        emailUrl: "",
        downloadBusy: false,

        init() {
            const el = this.$el;
            this.totalCount = Number(el.dataset.total || 0);
            this.consistentCount = Number(el.dataset.consistent || 0);
            this.inconsistentCount = Number(el.dataset.inconsistent || 0);
            this.failedCount = Number(el.dataset.failed || 0);
            this.exportUrl = el.dataset.exportUrl || "";
            this.emailUrl = el.dataset.emailUrl || "";
            if (this.inconsistentCount > 0) {
                this.filter = "nok";
            } else if (this.failedCount > 0) {
                this.filter = "failed";
            } else {
                this.filter = "all";
            }
            const dataEl = document.getElementById("precheck-validations-data");
            const raw = dataEl ? JSON.parse(dataEl.textContent || "[]") : [];
            this.rows = raw.map((item) => ({
                code: item.code || "",
                label: item.label || item.code || "",
                expected: item.expected ?? "",
                found: item.found ?? "",
                note: item.note || "—",
                status: item.status || "",
                isOk: item.status === "consistent",
                isNok: item.status === "inconsistent",
                isFailed: item.status === "failed",
                statusText:
                    item.status === "consistent"
                        ? "OK"
                        : item.status === "inconsistent"
                          ? "NOK"
                          : item.status === "failed"
                            ? "Warning"
                            : item.status || "—",
            }));
        },

        get overallScore() {
            if (!this.totalCount) return null;
            return Math.round((this.consistentCount / this.totalCount) * 100);
        },

        get scoreLabel() {
            return this.overallScore === null ? "—" : `${this.overallScore}%`;
        },

        get scoreClass() {
            if (this.overallScore === null) return "text-secondary";
            if (this.overallScore >= 80) return "text-success-text";
            if (this.overallScore >= 50) return "text-[#92400e]";
            return "text-[#991b1b]";
        },

        get visibleRows() {
            const q = (this.query || "").trim().toLowerCase();
            return this.rows.filter((item) => {
                if (this.filter === "ok" && !item.isOk) return false;
                if (this.filter === "nok" && !item.isNok) return false;
                if (this.filter === "failed" && !item.isFailed) return false;
                if (!q) return true;
                return [item.label, item.expected, item.found, item.note, item.statusText]
                    .join(" ")
                    .toLowerCase()
                    .includes(q);
            });
        },

        get showEmptyFilter() {
            return this.visibleRows.length === 0;
        },

        get filterAllClass() {
            return this.filter === "all"
                ? "bg-dark-blue text-white"
                : "text-secondary hover:bg-background";
        },

        get filterOkClass() {
            return this.filter === "ok"
                ? "bg-dark-blue text-white"
                : "text-secondary hover:bg-background";
        },

        get filterNokClass() {
            return this.filter === "nok"
                ? "bg-dark-blue text-white"
                : "text-secondary hover:bg-background";
        },

        get filterFailedClass() {
            return this.filter === "failed"
                ? "bg-dark-blue text-white"
                : "text-secondary hover:bg-background";
        },

        get filterAllLabel() {
            return `All (${this.totalCount})`;
        },

        get filterOkLabel() {
            return `OK (${this.consistentCount})`;
        },

        get filterNokLabel() {
            return `NOK (${this.inconsistentCount})`;
        },

        get filterFailedLabel() {
            return `Warnings (${this.failedCount})`;
        },

        setFilterAll() {
            this.filter = "all";
        },

        setFilterOk() {
            this.filter = "ok";
        },

        setFilterNok() {
            this.filter = "nok";
        },

        setFilterFailed() {
            this.filter = "failed";
        },

        onSearch(event) {
            this.query = event?.target?.value || "";
        },

        exportReport() {
            this.downloadOutput(this.exportUrl, "Claro_RF_Check_Report.xlsx", "Export failed");
        },

        prepareEmail(format) {
            const kind = format === "msg" ? "msg" : "eml";
            const joiner = this.emailUrl.includes("?") ? "&" : "?";
            this.downloadOutput(
                `${this.emailUrl}${joiner}format=${kind}`,
                `Claro_RF_Check_Report.${kind}`,
                "Share failed"
            );
        },

        filenameFromDisposition(header, fallback) {
            if (!header) return fallback;
            const encoded = /filename\*=UTF-8''([^;]+)/i.exec(header);
            if (encoded) {
                try {
                    return decodeURIComponent(encoded[1]);
                } catch (error) {
                    return fallback;
                }
            }
            const quoted = /filename="([^"]+)"/i.exec(header);
            if (quoted) return quoted[1];
            const plain = /filename=([^;]+)/i.exec(header);
            return plain ? plain[1].trim() : fallback;
        },

        notifyOutputError(title, message) {
            window.dispatchEvent(
                new CustomEvent("notify", {
                    detail: {
                        type: "error",
                        title,
                        message,
                    },
                })
            );
        },

        async downloadOutput(url, fallbackName, errorTitle) {
            if (!url || this.downloadBusy) return;
            this.downloadBusy = true;
            try {
                const response = await fetch(url, {
                    method: "GET",
                    headers: {
                        Accept: "application/json",
                        "X-Requested-With": "XMLHttpRequest",
                    },
                });
                if (!response.ok) {
                    const data = await response.json().catch(() => ({}));
                    this.notifyOutputError(
                        data.title || errorTitle,
                        data.message || "Could not generate the report. Try again."
                    );
                    return;
                }
                const blob = await response.blob();
                const filename = this.filenameFromDisposition(
                    response.headers.get("Content-Disposition"),
                    fallbackName
                );
                const objectUrl = URL.createObjectURL(blob);
                const link = document.createElement("a");
                link.href = objectUrl;
                link.download = filename;
                document.body.appendChild(link);
                link.click();
                link.remove();
                URL.revokeObjectURL(objectUrl);
            } catch (error) {
                this.notifyOutputError(errorTitle, "Could not generate the report. Try again.");
            } finally {
                this.downloadBusy = false;
            }
        },
    }));

    Alpine.data("combinedConfigure", () => ({
        csrfToken: "",
        saveUrl: "",
        selected: [],
        labels: { "2G": "2G", "3G": "3G", "4G": "4G LTE", "5G": "5G NR" },
        saving: false,

        init() {
            const el = this.$el;
            this.csrfToken = el.dataset.csrfToken || "";
            this.saveUrl = el.dataset.saveUrl || "";
            try {
                this.selected = JSON.parse(el.dataset.selected || "[]");
            } catch (error) {
                this.selected = [];
            }
        },

        isSelected(tech) {
            return this.selected.includes(tech);
        },

        toggle(tech) {
            if (this.isSelected(tech)) {
                this.selected = this.selected.filter((item) => item !== tech);
            } else {
                this.selected = [...this.selected, tech];
            }
        },

        labelFor(tech) {
            return this.labels[tech] || tech;
        },

        get selectionLabel() {
            const n = this.selected.length;
            return `${n} technolog${n === 1 ? "y" : "ies"} selected`;
        },

        get canContinue() {
            return this.selected.length >= 2 && !this.saving;
        },

        async continueNext() {
            if (!this.canContinue) return;
            this.saving = true;
            try {
                const response = await fetch(this.saveUrl, {
                    method: "POST",
                    headers: {
                        Accept: "application/json",
                        "Content-Type": "application/json",
                        "X-CSRFToken": this.csrfToken,
                        "X-Requested-With": "XMLHttpRequest",
                    },
                    body: JSON.stringify({ technologies: this.selected }),
                });
                const data = await response.json();
                if (!response.ok || data.type === "Error") {
                    window.dispatchEvent(
                        new CustomEvent("notify", {
                            detail: {
                                type: "error",
                                title: data.title || "Could not save",
                                message: data.message || "Failed to save configuration.",
                            },
                        })
                    );
                    return;
                }
                window.location.href = data.redirect_url;
            } catch (error) {
                window.dispatchEvent(
                    new CustomEvent("notify", {
                        detail: { type: "error", title: "Could not save", message: String(error) },
                    })
                );
            } finally {
                this.saving = false;
            }
        },
    }));

    Alpine.data("combinedSites", () => ({
        csrfToken: "",
        uploadUrl: "",
        generateUrl: "",
        jobStatusUrl: "",
        jobId: "",
        jobStatus: "",
        epFileName: "",
        selected: [],
        sites: [],
        search: "",
        page: 1,
        pageSize: 10,
        uploading: false,
        generating: false,
        polling: false,
        sitesCount: 0,
        processingLabel: "Processing EP file…",

        init() {
            const el = this.$el;
            this.csrfToken = el.dataset.csrfToken || "";
            this.uploadUrl = el.dataset.uploadUrl || "";
            this.generateUrl = el.dataset.generateUrl || "";
            this.jobStatusUrl = el.dataset.jobStatusUrl || "";
            this.jobId = el.dataset.jobId || "";
            this.jobStatus = el.dataset.jobStatus || "";
            this.epFileName = el.dataset.epFileName || "";
            this.polling = el.dataset.polling === "true";
            this.sitesCount = Number(el.dataset.sitesCount || 0);
            try {
                this.selected = JSON.parse(el.dataset.selectedSites || "[]");
            } catch (error) {
                this.selected = [];
            }
            const sitesEl = document.getElementById("combined-sites-data");
            try {
                this.sites = sitesEl ? JSON.parse(sitesEl.textContent || "[]") : [];
            } catch (error) {
                this.sites = [];
            }
            if (!this.sitesCount) this.sitesCount = this.sites.length;
            if (this.polling && this.jobStatusUrl) {
                this.pollJobStatus();
            }
        },

        get isProcessing() {
            return this.polling || this.jobStatus === "pending" || this.jobStatus === "processing";
        },

        get sitesCountLabel() {
            if (!this.sitesCount) return "EP imported";
            return `${this.sitesCount} site${this.sitesCount === 1 ? "" : "s"} available`;
        },

        get selectedSiteKeys() {
            const selected = new Set(this.selected);
            const keys = new Set();
            for (const site of this.sites) {
                if (selected.has(site.site_name)) {
                    keys.add(site.site_key || site.site_name);
                }
            }
            return keys;
        },

        get filteredSites() {
            const q = (this.search || "").toLowerCase().trim();
            const keys = this.selectedSiteKeys;
            return this.sites.filter((site) => {
                const key = site.site_key || site.site_name;
                if (keys.size && !keys.has(key)) return false;
                if (!q) return true;
                return String(site.site_name || "")
                    .toLowerCase()
                    .includes(q);
            });
        },

        get totalPages() {
            return Math.max(1, Math.ceil(this.filteredSites.length / this.pageSize));
        },

        get pagedSites() {
            const start = (this.page - 1) * this.pageSize;
            return this.filteredSites.slice(start, start + this.pageSize);
        },

		get hasPrevPage() {
            return this.page > 1;
        },

        get hasNextPage() {
            return this.page < this.totalPages;
        },

        get prevPageDisabled() {
            return !this.hasPrevPage;
        },

        get nextPageDisabled() {
            return !this.hasNextPage;
        },

        get showNoSitesMatch() {
            return this.filteredSites.length === 0;
        },

        get pageLabel() {
            return `Page ${this.page} of ${this.totalPages}`;
        },

        get sitesPagerLabel() {
            const total = this.filteredSites.length;
            if (!total) return "0 sites";
            const start = (this.page - 1) * this.pageSize + 1;
            const end = Math.min(this.page * this.pageSize, total);
            return `Showing ${start}–${end} of ${total} sites`;
        },

        onSearchSites(event) {
            this.search = event?.target?.value || "";
            this.page = 1;
        },

        prevPage() {
            if (this.hasPrevPage) this.page -= 1;
        },

        nextPage() {
            if (this.hasNextPage) this.page += 1;
        },

        cellCountLabel(site) {
            const count = site?.cell_count ?? 0;
            return `${count} cell${count === 1 ? "" : "s"} found`;
        },

        siteRowClass(site) {
            return this.isSelected(site)
                ? "bg-light-blue border-primary border-l-4"
                : "bg-white border-thin-gray";
        },

        siteCheckboxClass(site) {
            return this.isSelected(site)
                ? "bg-primary text-white"
                : "bg-white border border-[#9ca3af]";
        },

        isSelected(site) {
            return this.selected.includes(site);
        },

        toggle(site) {
            if (this.isSelected(site)) {
                this.selected = this.selected.filter((item) => item !== site);
            } else {
                this.selected = [...this.selected, site];
            }
            this.page = 1;
        },

        selectAllFiltered() {
            const names = this.filteredSites.map((site) => site.site_name).filter(Boolean);
            this.selected = [...new Set([...this.selected, ...names])];
        },

        clearSelection() {
            this.selected = [];
        },

        get selectedCountLabel() {
            return `${this.selected.length} selected`;
        },

        get canContinue() {
            return Boolean(
                this.jobId &&
                    this.selected.length &&
                    !this.generating &&
                    !this.uploading &&
                    !this.isProcessing
            );
        },

        pickFile() {
            this.$refs.epFileInput?.click();
        },

        onDrop(event) {
            const file = event.dataTransfer?.files?.[0];
            if (file) this.uploadFile(file);
        },

        onFileSelected(event) {
            const file = event.target?.files?.[0];
            if (file) this.uploadFile(file);
            if (event.target) event.target.value = "";
        },

        async pollJobStatus() {
            const maxAttempts = 180;
            for (let attempt = 0; attempt < maxAttempts; attempt += 1) {
                await new Promise((resolve) => setTimeout(resolve, 1000));
                try {
                    const response = await fetch(this.jobStatusUrl, {
                        headers: {
                            Accept: "application/json",
                            "X-Requested-With": "XMLHttpRequest",
                            "X-CSRFToken": this.csrfToken,
                        },
                    });
                    const data = await response.json();
                    const status = data.status || data.job?.status || "";
                    this.jobStatus = status;
                    if (data.filename || data.job?.filename) {
                        this.epFileName = data.filename || data.job.filename;
                    }
                    const rowsProcessed = data.rows_processed ?? data.job?.rows_processed;
                    const rowsTotal = data.rows_total ?? data.job?.rows_total;
                    if (rowsTotal) {
                        this.processingLabel = `Processing EP file… ${rowsProcessed || 0} / ${rowsTotal}`;
                    } else if (rowsProcessed) {
                        this.processingLabel = `Processing EP file… ${rowsProcessed} rows`;
                    }
                    if (status === "success" || status === "failed") {
                        window.location.href = `/check/combined/sites/?job=${this.jobId}`;
                        return;
                    }
                } catch (error) {
                    // keep polling
                }
            }
        },

        async uploadFile(file) {
            if (!this.uploadUrl || this.uploading) return;
            this.uploading = true;
            const formData = new FormData();
            formData.append("file", file);
            formData.append("technology", "5G");
            try {
                const response = await fetch(this.uploadUrl, {
                    method: "POST",
                    headers: {
                        Accept: "application/json",
                        "X-Requested-With": "XMLHttpRequest",
                        "X-CSRFToken": this.csrfToken,
                    },
                    body: formData,
                });
                const data = await response.json();
                if (!response.ok || data.type === "Error") {
                    window.dispatchEvent(
                        new CustomEvent("notify", {
                            detail: {
                                type: "error",
                                title: data.title || "Upload error",
                                message: data.message || "Failed to upload the EP file.",
                            },
                        })
                    );
                    return;
                }
                this.jobId = data.job?.id || "";
                this.epFileName = data.job?.filename || file.name;
                this.jobStatus = data.job?.status || "processing";
                if (this.jobId) {
                    window.location.href = `/check/combined/sites/?job=${this.jobId}`;
                }
            } catch (error) {
                window.dispatchEvent(
                    new CustomEvent("notify", {
                        detail: { type: "error", title: "Upload error", message: String(error) },
                    })
                );
            } finally {
                this.uploading = false;
            }
        },

        async continueNext() {
            if (!this.canContinue) return;
            this.generating = true;
            try {
                const response = await fetch(this.generateUrl, {
                    method: "POST",
                    headers: {
                        Accept: "application/json",
                        "Content-Type": "application/json",
                        "X-CSRFToken": this.csrfToken,
                        "X-Requested-With": "XMLHttpRequest",
                    },
                    body: JSON.stringify({ job_id: this.jobId, sites: this.selected }),
                });
                const data = await response.json();
                if (!response.ok || data.type === "Error") {
                    window.dispatchEvent(
                        new CustomEvent("notify", {
                            detail: {
                                type: "error",
                                title: data.title || "Could not generate scripts",
                                message: data.message || "Failed to generate scripts.",
                            },
                        })
                    );
                    return;
                }
                window.location.href = data.redirect_url;
            } catch (error) {
                window.dispatchEvent(
                    new CustomEvent("notify", {
                        detail: {
                            type: "error",
                            title: "Could not generate scripts",
                            message: String(error),
                        },
                    })
                );
            } finally {
                this.generating = false;
            }
        },
    }));

    Alpine.data("combinedScripts", () => ({
        csrfToken: "",
        uploadPrecheckUrl: "",
        uploadFullCheckUrl: "",
        processUrl: "",
        canImport: false,
        canProcess: false,
        board: { technologies: [], precheck_tech: null, full_check_techs: [] },
        openScripts: {},
        scriptTechs: [],
        allScriptsOpen: false,
        uploading: false,
        processing: false,

        init() {
            const el = this.$el;
            this.csrfToken = el.dataset.csrfToken || "";
            this.uploadPrecheckUrl = el.dataset.uploadPrecheckUrl || "";
            this.uploadFullCheckUrl = el.dataset.uploadFullCheckUrl || "";
            this.processUrl = el.dataset.processUrl || "";
            this.canImport = el.dataset.canImport === "true";
            this.canProcess = el.dataset.canProcess === "true";
            this.scriptTechs = (el.dataset.scriptTechs || "")
                .split(",")
                .map((item) => item.trim())
                .filter(Boolean);
            const boardEl = document.getElementById("combined-returns-board");
            try {
                this.board = boardEl ? JSON.parse(boardEl.textContent || "{}") : this.board;
            } catch (error) {
                this.board = { technologies: [], precheck_tech: null, full_check_techs: [] };
            }
            this.syncProcessFlag();
        },

        get precheckTech() {
            return this.board?.precheck_tech || null;
        },

        get fullCheckTechs() {
            return this.board?.full_check_techs || [];
        },

        get cannotProcess() {
            return !this.canImport || !this.canProcess || this.uploading || this.processing;
        },

        isScriptOpen(tech) {
            return Boolean(this.openScripts[tech]);
        },

        toggleScript(tech) {
            this.openScripts = { ...this.openScripts, [tech]: !this.openScripts[tech] };
            const techs = this.scriptTechs.length ? this.scriptTechs : Object.keys(this.openScripts);
            this.allScriptsOpen = techs.length > 0 && techs.every((item) => this.openScripts[item]);
        },

        toggleAllScripts() {
            const techs = this.scriptTechs.length
                ? this.scriptTechs
                : (this.board?.technologies || []).map((item) => item.technology);
            const next = !this.allScriptsOpen;
            const map = {};
            techs.forEach((tech) => {
                map[tech] = next;
            });
            this.openScripts = map;
            this.allScriptsOpen = next;
        },

        syncProcessFlag() {
            if (typeof this.board?.all_ready === "boolean") {
                this.canProcess = this.canImport && this.board.all_ready;
            }
        },

        pickFullCheck(technology) {
            document.getElementById(`full-check-input-${technology}`)?.click();
        },

        pickPrecheck() {
            this.$refs.precheckFileInput?.click();
        },

        onDrop(event, kind, technology) {
            const file = event.dataTransfer?.files?.[0];
            if (file) this.uploadFile(file, kind, technology);
        },

        onFileSelected(event, kind, technology) {
            const file = event.target?.files?.[0];
            if (file) this.uploadFile(file, kind, technology);
            if (event.target) event.target.value = "";
        },

        async copyText(text) {
            try {
                await navigator.clipboard.writeText(text);
                window.dispatchEvent(
                    new CustomEvent("notify", {
                        detail: {
                            type: "success",
                            title: "Script copied",
                            message: "The content was copied to the clipboard.",
                        },
                    })
                );
            } catch (error) {
                window.dispatchEvent(
                    new CustomEvent("notify", {
                        detail: { type: "error", title: "Could not copy", message: String(error) },
                    })
                );
            }
        },

        async uploadFile(file, kind, technology) {
            if (!this.canImport || this.uploading || this.processing) return;
            const url = kind === "fullcheck" ? this.uploadFullCheckUrl : this.uploadPrecheckUrl;
            if (!url) return;
            this.uploading = true;
            const body = new FormData();
            body.append("file", file);
            if (kind === "fullcheck") {
                body.append("technology", technology);
            }
            try {
                const response = await fetch(url, {
                    method: "POST",
                    headers: {
                        Accept: "application/json",
                        "X-CSRFToken": this.csrfToken,
                        "X-Requested-With": "XMLHttpRequest",
                    },
                    body,
                });
                const data = await response.json();
                if (!response.ok || data.type === "Error") {
                    window.dispatchEvent(
                        new CustomEvent("notify", {
                            detail: {
                                type: "error",
                                title: data.title || "Upload error",
                                message: data.message || "Could not upload the return file.",
                            },
                        })
                    );
                    return;
                }
                if (data.returns_board) {
                    this.board = data.returns_board;
                }
                if (typeof data.can_process === "boolean") {
                    this.canProcess = data.can_process;
                } else {
                    this.syncProcessFlag();
                }
                window.dispatchEvent(
                    new CustomEvent("notify", {
                        detail: {
                            type: "success",
                            title: data.title || "Return imported",
                            message: data.message || "File uploaded successfully.",
                        },
                    })
                );
            } catch (error) {
                window.dispatchEvent(
                    new CustomEvent("notify", {
                        detail: { type: "error", title: "Upload error", message: String(error) },
                    })
                );
            } finally {
                this.uploading = false;
            }
        },

        async processAnalysis() {
            if (this.cannotProcess) return;
            this.processing = true;
            try {
                const { data, ok } = await processCheckRequest(this.processUrl, this.csrfToken);
                if (!ok || data.type === "Error") {
                    if (data.redirect_url) {
                        window.location.href = data.redirect_url;
                        return;
                    }
                    window.dispatchEvent(
                        new CustomEvent("notify", {
                            detail: {
                                type: "error",
                                title: data.title || "Could not process",
                                message: data.message || "Processing failed.",
                            },
                        })
                    );
                    return;
                }
                if (data.redirect_url) {
                    window.location.href = data.redirect_url;
                    return;
                }
                window.dispatchEvent(
                    new CustomEvent("notify", {
                        detail: {
                            type: "success",
                            title: data.title || "Analysis ready",
                            message: data.message || "Processing finished.",
                        },
                    })
                );
            } catch (error) {
                window.dispatchEvent(
                    new CustomEvent("notify", {
                        detail: {
                            type: "error",
                            title: "Could not process",
                            message: String(error),
                        },
                    })
                );
            } finally {
                this.processing = false;
            }
        },
    }));

    Alpine.data("combinedResult", () => ({
        tab: "overview",
        techFilter: "all",
        filter: "all",
        search: "",
        exportUrl: "",
        emailUrl: "",
        downloadBusy: false,
        page: 1,
        pageSize: 25,
        technologies: [],
        preRows: [],
        fullRows: [],
        totalCount: 0,
        consistentCount: 0,
        inconsistentCount: 0,
        failedCount: 0,

        init() {
            const el = this.$el;
            this.technologies = (el.dataset.techs || "").split(",").filter(Boolean);
            this.exportUrl = el.dataset.exportUrl || "";
            this.emailUrl = el.dataset.emailUrl || "";
            this.totalCount = Number(el.dataset.total || 0);
            this.consistentCount = Number(el.dataset.consistent || 0);
            this.inconsistentCount = Number(el.dataset.inconsistent || 0);
            this.failedCount = Number(el.dataset.failed || 0);
            const preEl = document.getElementById("combined-pre-validations");
            const fullEl = document.getElementById("combined-full-validations");
            try {
                this.preRows = preEl ? JSON.parse(preEl.textContent || "[]") : [];
            } catch (error) {
                this.preRows = [];
            }
            try {
                this.fullRows = fullEl ? JSON.parse(fullEl.textContent || "[]") : [];
            } catch (error) {
                this.fullRows = [];
            }
            if (!this.preRows.length && this.fullRows.length) this.tab = "full";
            if (this.inconsistentCount > 0) this.filter = "nok";
            else if (this.failedCount > 0) this.filter = "failed";
        },

        resetRowsPage() {
            this.page = 1;
        },

        setTabOverview() {
            this.tab = "overview";
            this.resetRowsPage();
        },
        setTabPre() {
            this.tab = "pre";
            this.resetRowsPage();
        },
        setTabFull() {
            this.tab = "full";
            this.resetRowsPage();
        },
        setTechAll() {
            this.techFilter = "all";
            this.resetRowsPage();
        },
        setTechFilter(tech) {
            this.techFilter = tech;
            this.resetRowsPage();
        },
        setFilterAll() {
            this.filter = "all";
            this.resetRowsPage();
        },
        setFilterOk() {
            this.filter = "ok";
            this.resetRowsPage();
        },
        setFilterFailed() {
            this.filter = "failed";
            this.resetRowsPage();
        },
        setFilterNok() {
            this.filter = "nok";
            this.resetRowsPage();
        },
        onSearch(event) {
            this.search = event?.target?.value || "";
            this.resetRowsPage();
        },

        get tabOverviewClass() {
            return this.tab === "overview"
                ? "border-b-2 border-primary font-medium text-primary"
                : "text-muted";
        },
        get tabPreClass() {
            return this.tab === "pre"
                ? "border-b-2 border-primary font-medium text-primary"
                : "text-muted";
        },
        get tabFullClass() {
            return this.tab === "full"
                ? "border-b-2 border-primary font-medium text-primary"
                : "text-muted";
        },
        get techAllClass() {
            return this.techFilter === "all"
                ? "bg-primary text-white border-primary"
                : "bg-white text-secondary border-thin-gray";
        },
        techButtonClass(tech) {
            return this.techFilter === tech
                ? "bg-primary text-white border-primary"
                : "bg-white text-secondary border-thin-gray";
        },
        get filterAllClass() {
            return this.filter === "all" ? "is-active" : "";
        },
        get filterOkClass() {
            return this.filter === "ok" ? "is-active" : "";
        },
        get filterFailedClass() {
            return this.filter === "failed" ? "is-active" : "";
        },
        get filterNokClass() {
            return this.filter === "nok" ? "is-active" : "";
        },

        get activeRows() {
            if (this.tab === "pre") return this.preRows;
            if (this.tab === "full") return this.fullRows;
            return [...this.preRows, ...this.fullRows];
        },

        rowMatchesTech(row) {
            return this.techFilter === "all" || row.technology === this.techFilter;
        },

        get countedRows() {
            return this.activeRows.filter((row) => this.rowMatchesTech(row));
        },

        get scopedTotal() {
            return this.countedRows.length;
        },

        get scopedConsistent() {
            return this.countedRows.filter((row) => row.status === "consistent").length;
        },

        get scopedFailed() {
            return this.countedRows.filter((row) => row.status === "failed").length;
        },

        get scopedInconsistent() {
            return this.countedRows.filter((row) => row.status === "inconsistent").length;
        },

        get visibleRows() {
            const q = (this.search || "").toLowerCase();
            return this.countedRows.filter((row) => {
                const status = row.status || "";
                if (this.filter === "ok" && status !== "consistent") return false;
                if (this.filter === "nok" && status !== "inconsistent") return false;
                if (this.filter === "failed" && status !== "failed") return false;
                if (!q) return true;
                const hay = [
                    row.label,
                    row.code,
                    row.parameter,
                    row.site_name,
                    row.technology,
                    row.expected,
                    row.found,
                    row.actual,
                ]
                    .filter(Boolean)
                    .join(" ")
                    .toLowerCase();
                return hay.includes(q);
            });
        },

        get totalRowsPages() {
            return Math.max(1, Math.ceil(this.visibleRows.length / this.pageSize));
        },

        get pagedRows() {
            const start = (this.page - 1) * this.pageSize;
            return this.visibleRows.slice(start, start + this.pageSize);
        },

        get hasPrevRowsPage() {
            return this.page > 1;
        },

        get hasNextRowsPage() {
            return this.page < this.totalRowsPages;
        },

        get prevRowsDisabled() {
            return !this.hasPrevRowsPage;
        },

        get nextRowsDisabled() {
            return !this.hasNextRowsPage;
        },

        get showRowsPager() {
            return this.visibleRows.length > 0;
        },

        get rowsPageLabel() {
            return `Page ${this.page} of ${this.totalRowsPages}`;
        },

        get rowsPagerLabel() {
            const total = this.visibleRows.length;
            if (!total) return "0 rows";
            const start = (this.page - 1) * this.pageSize + 1;
            const end = Math.min(this.page * this.pageSize, total);
            return `Showing ${start}–${end} of ${total} rows`;
        },

        prevRowsPage() {
            if (this.hasPrevRowsPage) this.page -= 1;
        },

        nextRowsPage() {
            if (this.hasNextRowsPage) this.page += 1;
        },

        get showEmptyFilter() {
            return this.visibleRows.length === 0;
        },

        get filterAllLabel() {
            return `All (${this.scopedTotal})`;
        },
        get filterOkLabel() {
            return `Ready (${this.scopedConsistent})`;
        },
        get filterFailedLabel() {
            return `Attention (${this.scopedFailed})`;
        },
        get filterNokLabel() {
            return `Issues (${this.scopedInconsistent})`;
        },

        exportReport() {
            this.downloadOutput(this.exportUrl, "Claro_RF_Check_Report.xlsx", "Export failed");
        },

        prepareEmail(format) {
            const kind = format === "msg" ? "msg" : "eml";
            const joiner = this.emailUrl.includes("?") ? "&" : "?";
            this.downloadOutput(
                `${this.emailUrl}${joiner}format=${kind}`,
                `Claro_RF_Check_Report.${kind}`,
                "Share failed"
            );
        },

        filenameFromDisposition(header, fallback) {
            if (!header) return fallback;
            const encoded = /filename\*=UTF-8''([^;]+)/i.exec(header);
            if (encoded) {
                try {
                    return decodeURIComponent(encoded[1]);
                } catch (error) {
                    return fallback;
                }
            }
            const quoted = /filename="([^"]+)"/i.exec(header);
            if (quoted) return quoted[1];
            const plain = /filename=([^;]+)/i.exec(header);
            return plain ? plain[1].trim() : fallback;
        },

        notifyOutputError(title, message) {
            window.dispatchEvent(
                new CustomEvent("notify", {
                    detail: {
                        type: "error",
                        title,
                        message,
                    },
                })
            );
        },

        async downloadOutput(url, fallbackName, errorTitle) {
            if (!url || this.downloadBusy) return;
            this.downloadBusy = true;
            try {
                const response = await fetch(url, {
                    method: "GET",
                    headers: {
                        Accept: "application/json",
                        "X-Requested-With": "XMLHttpRequest",
                    },
                });
                if (!response.ok) {
                    const data = await response.json().catch(() => ({}));
                    this.notifyOutputError(
                        data.title || errorTitle,
                        data.message || "Could not generate the report. Try again."
                    );
                    return;
                }
                const blob = await response.blob();
                const filename = this.filenameFromDisposition(
                    response.headers.get("Content-Disposition"),
                    fallbackName
                );
                const objectUrl = URL.createObjectURL(blob);
                const link = document.createElement("a");
                link.href = objectUrl;
                link.download = filename;
                document.body.appendChild(link);
                link.click();
                link.remove();
                URL.revokeObjectURL(objectUrl);
            } catch (error) {
                this.notifyOutputError(errorTitle, "Could not generate the report. Try again.");
            } finally {
                this.downloadBusy = false;
            }
        },

        statusLabel(status) {
            if (status === "consistent") return "Ready";
            if (status === "inconsistent") return "Issue";
            return "Attention";
        },

        statusClass(status) {
            if (status === "consistent") return "bg-success-bg text-success-text border border-[#bbf7d0]";
            if (status === "inconsistent") return "bg-[#fee2e2] text-[#991b1b] border border-[#fecaca]";
            return "bg-[#fef3c7] text-[#92400e] border border-[#fde68a]";
        },
    }));
});

document.addEventListener("htmx:afterSwap", (event) => {
    if (window.Alpine && event.detail?.target) {
        Alpine.initTree(event.detail.target);
    }
});
