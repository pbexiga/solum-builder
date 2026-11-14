# Building the Mac app

`Solum Builder.app` is the same server and page as the Docker image, behind a native window, with everything it needs inside it (D-321). It is built on an Apple Silicon Mac, never in the dev image.

## Build it

```
make mac-app
```

The only thing the Mac must have is Xcode's command-line tools (`xcode-select --install`). The build brings the rest into `build/mac/` (git-ignored): `uv`, `micromamba`, Python 3.12, the Python packages, ngspice 44.2 built from source (library and program), and the PDF libraries from conda-forge. Nothing is installed on the Mac or put on its PATH.

It then runs the unit, simulation, rules and acceptance tests against that ngspice, builds the app, smoke-tests the app itself (starts it with an empty home folder, runs starters, exports the PDFs, renders a clip, quits it), and writes `dist/Solum-Builder-<version>.dmg`. The version is `solum/__init__.py`'s (D-305).

- First build: about 10 minutes (ngspice is compiled twice) and 1.5 GB in `build/mac/`. Later builds reuse it: 2 to 3 minutes.
- `SKIP_TESTS=1 make mac-app` leaves the test suites out; the smoke test still runs.
- Remove everything it brought: `rm -rf build/mac dist`.
- The app is **signed by us, not by Apple** (D-326): an ad-hoc signature, which Apple Silicon requires, and no Developer ID or notarisation (the project has no Apple Developer account). Built on your own Mac it opens with a double-click; downloaded, macOS asks for System Settings → Privacy & Security → Open Anyway the first time. Anyone who'd rather not trust the download builds the same `.dmg` with `make mac-app`; the README says so.

## Signing and notarising (optional)

With an Apple Developer account, the same build signs with a Developer ID and notarises (D-330). Set these before `make mac-app` (the release workflow sets them from its secrets):

| Variable | What |
|---|---|
| `MAC_SIGN_IDENTITY` | The certificate's name in a keychain, `Developer ID Application: <name> (<team>)` |
| `NOTARY_KEY_FILE`, `NOTARY_KEY_ID`, `NOTARY_ISSUER_ID` | An App Store Connect API key (the `.p8` file, its key id, the issuer id); leave them out to sign without notarising |

`scripts/mac_sign.sh` signs every binary in the app inside out with the hardened runtime, then the app with `packaging/mac/entitlements.plist` (empty: the app needs no entitlement), before the smoke test, so what's tested is what ships. With the key it sends the app to Apple and staples the ticket, then signs, notarises and staples the `.dmg`.

`MAC_SIGN_IDENTITY=- SKIP_TESTS=1 make mac-app` checks the hardened runtime on a Mac with no certificate: an ad-hoc signature with it, and library validation turned off, which a Developer ID build doesn't need (ad hoc has no Team ID, and the hardened runtime loads only its own team's libraries). Run it after changing what the app bundles: a new library that needs an entitlement fails the smoke test there.

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
| The build, the icon, the smoke test, signing | `scripts/mac_app.sh`, `scripts/mac_icon.py`, `scripts/mac_smoke.py`, `scripts/mac_sign.sh` |
| The release build on GitHub, the release notes' template, the entitlements | `.github/workflows/release.yml`, `packaging/mac/release-notes.md`, `packaging/mac/entitlements.plist` |

On the person's Mac the app keeps: circuits, blocks, models and audio in `~/Library/Application Support/Solum Builder/` (or the folder chosen in Settings), the cache in `~/Library/Caches/Solum Builder/`, its log in `~/Library/Logs/Solum Builder/solum.log`.

## Updating what the build pins

Everything downloaded is pinned with its SHA-256, at the top of `scripts/mac_app.sh` (ngspice's in `scripts/ngspice_build.sh`, shared with the Docker image); a file that doesn't match stops the build.

- **uv, micromamba**: set the new version and the checksum their release pages publish.
- **ngspice**: built by `scripts/ngspice_build.sh`, the same script the Docker image runs (D-327), so the app and the image always have the same one. A new version may move the acceptance values: set `NGSPICE_VERSION` and the tarball's checksum there, then run `make dev-image`, `make check` and `make accept` (the image) and the full `make mac-app`. Keep `-ffp-contract=off` (D-322).
- **The PDF libraries**: make a fresh environment and export it over the lock, keeping the comment lines at its top:
  ```
  export MAMBA_ROOT_PREFIX=$PWD/build/mac/mamba-root
  build/mac/tools/micromamba create -y -p /tmp/pdflibs -c conda-forge --override-channels pango harfbuzz fontconfig
  build/mac/tools/micromamba env export -p /tmp/pdflibs --explicit --md5
  ```
  Then build, and open a build package's PDFs.
- **Python packages**: `pyproject.toml`, as for the image.

After any of these, do the hand checks in [release.md](release.md).
