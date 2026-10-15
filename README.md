# File-open time benchmark

This project measures how long an editor takes to open a file after a click on
that file in its Explorer. The required comparison currently covers LVCE Editor
and Visual Studio Code. Each result includes the individual trials, editor
versions, host details, the protocol and downloadable raw JSON. The latest
complete charts and evidence are published on
[GitHub Pages](https://levivilet.github.io/file-open-time-benchmark/).

## Measurement protocol

Each trial creates a workspace with `hello.txt` containing exactly `hello
world`, launches the pinned editor with a fresh HOME, XDG profile and Chromium
user-data directory, and waits ten seconds after the editor page becomes
available. The benchmark locates the unique accessible Explorer tree item
named `hello.txt` and sends a CDP mouse click at its on-screen bounds.

The monotonic measurement starts immediately before the mouse press is
dispatched and ends when the selected document identifies `hello.txt` and its
visible editor text equals the expected contents. Click dispatch and the CDP
observation overhead are included. Workspace preparation, editor launch,
readiness, settling and cleanup are excluded. Each editor runs three fresh
profile trials. The page compares medians and lists every duration; it does not
claim that the results represent cold-start time or that small differences are
statistically significant.

The workflow pins exact editor artifacts in
[`config/editors.lock.json`](config/editors.lock.json), verifies downloaded
SHA-256 checksums and runs on Linux ARM64 for both editors. Report generation
rejects missing or duplicate editors, incompatible protocols, invalid opens,
incorrect content, invalid durations and version mismatches. GitHub Actions
validates the complete comparison on pull requests and publishes the report to
Pages after a successful run on `main`.

## Run locally

On Linux ARM64 with Xvfb and the editor runtime dependencies installed:

```sh
python3 scripts/install.py --editors lvce,vscode
xvfb-run -a python3 scripts/benchmark.py --editor lvce
xvfb-run -a python3 scripts/benchmark.py --editor vscode
python3 -m unittest discover -s tests
```

To build the static report from complete artifacts:

```sh
python3 scripts/report.py --input results/editors --output .tmp/pages
```

Other IDEs can be added when they expose a comparable accessible Explorer item
and a verifiable visible-document completion signal. The current report only
includes the two required editors.
