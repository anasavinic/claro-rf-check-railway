from invoke import Context, task


@task
def check(c):
    """Run Ruff in check-only mode (no writes)."""
    c.run("ruff check .")
    c.run("ruff format --check .")


@task
def format(c):
    """Apply Ruff auto-fixes and format the tree."""
    c.run("ruff check --fix .")
    c.run("ruff format .")


@task
def pip_audit(c):
    """Audit the runtime lockfile for known vulnerabilities."""
    c.run("pip-audit -r requirements.txt --no-deps --disable-pip --progress-spinner off --cache-dir .pip-audit-cache")


@task(default=True)
def lint(c: Context):
    """Check Ruff compliance without modifying the working tree."""
    check(c)
    print("Lint completed.")
