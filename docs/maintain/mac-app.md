# Building the Mac app

`Solum Builder.app` is the same server and page as the Docker image, behind a native window, with everything it needs inside it (D-321). It is built on an Apple Silicon Mac, never in the dev image.

## Build it

```
make mac-app
```

The only thing the Mac must have is Xcode's command-line tools (`xcode-select --install`). The build brings the rest into `build/mac/` (git-ignored): `uv`, `micromamba`, Python 3.12, the Python packages, ngspice 44.2 built from source (library and program), and the PDF libraries from conda-forge. Nothing is installed on the Mac or put on its PATH.

It then runs the unit, simulation, rules and acceptance tests against that ngspice, builds the app, smoke-tests the app itself (starts it with an empty home folder, runs starters, exports the PDFs, renders a clip, quits it), and writes `dist/Solum Builder-<version>.dmg`. The version is `solum/__init__.py`'s (D-305).

- First build: about 10 minutes (ngspice is compiled twice) and 1.5 GB in `build/mac/`. Later builds reuse it: 2 to 3 minutes.
- `SKIP_TESTS=1 make mac-app` leaves the test suites out; the smoke test still runs.
- Remove everything it brought: `rm -rf build/mac dist`.
- The app is **unsigned on purpose** (D-326). Built on your own Mac it opens with a double-click; downloaded, macOS asks for System Settings → Privacy & Security → Open Anyway the first time.

## Run the tests on a Mac without building the app

`make LOCAL=1 check` can't find ngspice on a Mac: the libraries are found through `DYLD_FALLBACK_LIBRARY_PATH`, and macOS removes that variable from the environment of `make` and `sh`. After one `make mac-app`, start pytest directly:

```
DYLD_FALLBACK_LIBRARY_PATH=$PWD/build/mac/ngspice/lib:$PWD/build/mac/pdflibs/lib \
PATH=$PWD/build/mac/venv/bin:$PWD/build/mac/ngspice/bin:$PATH \
python -m pytest -q -n auto -m "not timing" tests/unit tests/sim tests/rules
```

The UI and parity tests need Playwright's browser and stay the dev image's (`make accept` with Podman or Docker).

## Where the pieces are

| What | Where |
|---|---|
| The launcher: folders, the server in a thread, the window, what Settings asks of macOS | `solum/desktop/` |
| The page's side: Change… and Show in Finder in Settings, the Settings… menu item | `web/desktop.js`, `web/settings.js` |
| The program PyInstaller freezes, its spec, the app's `fonts.conf`, the PDF libraries' lock | `packaging/mac/` |
| The build, the icon, the smoke test | `scripts/mac_app.sh`, `scripts/mac_icon.py`, `scripts/mac_smoke.py` |

On the person's Mac the app keeps: circuits, blocks, models and audio in `~/Library/Application Support/Solum Builder/` (or the folder chosen in Settings), the cache in `~/Library/Caches/Solum Builder/`, its log in `~/Library/Logs/Solum Builder/solum.log`.

## Updating what the build pins

Everything downloaded is pinned at the top of `scripts/mac_app.sh` with its SHA-256; a file that doesn't match stops the build.

- **uv, micromamba**: set the new version and the checksum their release pages publish.
- **ngspice**: must stay the image's version (Debian's `libngspice0`), or the acceptance values may move. When the image's changes, set `NGSPICE_VERSION`, `NGSPICE_URL` and the tarball's checksum, and run the full build: the tests say whether the values hold. Keep `-ffp-contract=off` (D-322).
- **The PDF libraries**: make a fresh environment and export it over the lock, keeping the comment lines at its top:
  ```
  export MAMBA_ROOT_PREFIX=$PWD/build/mac/mamba-root
  build/mac/tools/micromamba create -y -p /tmp/pdflibs -c conda-forge --override-channels pango harfbuzz fontconfig
  build/mac/tools/micromamba env export -p /tmp/pdflibs --explicit --md5
  ```
  Then build, and open a build package's PDFs.
- **Python packages**: `pyproject.toml`, as for the image.

After any of these, do the hand checks in [release.md](release.md).
