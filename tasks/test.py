from invoke import task


@task(default=True)
def pytest(c, file_path=None, keyword=None, marker=None, debug=False, serial=False):
    """Execute pytest"""
    cmd = ["pytest"]
    if file_path:
        cmd.append(file_path.replace("./code/", ""))
    if keyword:
        cmd.extend(["-k", keyword])
    if marker:
        cmd.extend(["-m", marker])
    if debug:
        cmd.extend(["-n 0", "--pudb"])
    if serial:
        cmd.append("-n 0")
    c.run(" ".join(cmd))
