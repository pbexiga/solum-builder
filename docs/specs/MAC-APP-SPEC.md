# Spec: Solum Builder as a macOS app

Status: built, released in 1.1.0 (D-328). Specified 2026-11-12, built 2026-11-13 to 2026-11-14. This is what was built; where it and DECISIONS.md differ, DECISIONS.md wins (D-309). Users' side: the guide's [The Mac app](../guide/mac-app.md) and [Settings](../guide/settings.md); maintainers': [Building the Mac app](../maintain/mac-app.md) and [Releasing](../maintain/release.md).

## 1. Goal

A Mac user downloads `Solum-Builder-<version>.dmg` from the GitHub Releases page, drags the app into Applications and opens it. Solum Builder opens in its own window: no Docker, no Python, no Homebrew, no terminal, no admin password.

The Docker image stays the way to run on Linux, Windows, an Intel Mac, a NAS or a home server. Both are built from the same `solum/` and `web/`: the Mac app is a second packaging, not a second code base (D-321).

### Not in scope

- A native rewrite (Swift/SwiftUI), Electron or Tauri: the web UI is the UI (D-321).
- Windows or Linux desktop apps.
- The Mac App Store (sandboxing; Developer ID distribution is enough).
- Automatic updates (Sparkle or similar).
- An Intel build: every native library twice, a second runner, and macOS 26 is the last macOS for Intel. Intel Macs use Docker (D-321).

## 2. What the user gets

- **Install:** open the `.dmg`, drag the app to Applications. Everything it needs is inside the `.app`; the only system part it uses is macOS's WebKit. Apple Silicon, macOS 14 or later (D-321).
- **First open:** the app isn't notarised (§7), so macOS asks: System Settings → Privacy & Security → **Open Anyway**, once per version. The release notes, the README and the guide give the steps.
- **Run:** one window with the app. The Mac menu bar has the app menu (About, **Settings…** with Cmd-,, Hide, Quit) and Edit; the page's own menus (File, Edit, View, …) stay in the page (D-321).
- **Quit:** closing the window or Cmd-Q stops everything, the server and its render workers too. With unsaved changes it asks first (**Cancel**, **Quit Anyway**) (D-321).
- **Second launch while open:** brings the open window forward; no second copy (D-321).
- **Update:** drag the new app over the old one; files are kept.
- **Uninstall:** delete the app; to remove everything, also delete the folders in §5.

## 3. How it works

```
Solum Builder.app
  launcher (solum/desktop/, frozen by packaging/mac/launch.py)
    1. reads its settings.json (§5); sets DATA_DIR, CACHE_DIR, LIBRARY_DIR, WEB_DIR, GUIDE_DIR,
       NGSPICE_LIBRARY, SPICE_SCRIPTS and CAN_MOVE_FOLDERS=1 for the bundled paths (server_environment)
    2. writes ngspice's spinit for this bundle's path (write_spinit, D-322)
    3. starts the FastAPI app with uvicorn on 127.0.0.1, any free port, in a thread
       (solum/api/serving.py's LocalServer, the same one the UI tests use)
    4. waits for /api/health, then opens a pywebview window on http://127.0.0.1:<port>/
    5. on window close or Quit: stops the server and its render workers, exits
```

- **Window:** pywebview, on the system's WKWebView (D-321). New dependencies, for the Mac app only (`pip install '.[mac]'`): pywebview and PyInstaller.
- **Server address:** `127.0.0.1` only: nothing on the network can reach it, and macOS doesn't ask to allow incoming connections.
- **Nothing in the server differs**: settings were already environment-driven (`load_settings`); the launcher sets the environment before the app is created (D-321).
- **One copy at a time:** a lock file in the caches folder.
- **Log:** `~/Library/Logs/Solum Builder/solum.log` (3 × 1 MB), the launcher's and the server's. If the server doesn't start, the window says *Solum Builder couldn't start* in plain English and names the log.
- **Render workers** (D-083) are the app's program started again (`multiprocessing.freeze_support()` first), with no window and no Dock icon. After a force quit or a crash each one ends itself within a second, when the app that started it is gone.

### What the native window needed

| Behaviour | How it's handled |
|---|---|
| Downloads (WAV, the build package, PDFs) | macOS's save panel (pywebview's `ALLOW_DOWNLOADS`), for links with `download` and attachment responses (D-325, D-312) |
| Links with `target="_blank"` (About, the guide's sources) | Open in the default browser (`OPEN_EXTERNAL_LINKS_IN_BROWSER`) (D-325) |
| The guide's pop-out | A link whose `href` is set as it's pressed, not `window.open` (D-325) |
| File uploads (clips, captures, IRs, Add a model, Import) | The macOS file picker, with no code of ours |
| What the page remembers | Preferences are the server's, in `DATA_DIR` (D-311): theme, Auto-run, pane order, open panes, large views. The page's own storage is private and forgotten on quit: with a new port each launch it would only pile up (D-321) |
| Unsaved work on close | The page tells the launcher (`desktopUnsaved`, `web/desktop.js`); the launcher asks (D-321) |
| Settings… in the menu bar | A `solum-desktop` event the page listens for (`desktopMenus`) |

## 4. Bundling

- **PyInstaller**, a one-folder `.app` (`packaging/mac/solum.spec`) with Python 3.12 and the packages, `library/`, `web/`, `docs/guide/`, libngspice with its code models, and the PDF libraries. Briefcase wasn't needed: PyInstaller's hooks cover every dependency (D-321).
- **libngspice 44.2, built from the release tarball** with `-ffp-contract=off` (fused multiply-add breaks transients through op-amp macro-models on arm64). The same recipe, `scripts/ngspice_build.sh`, builds the Docker image's on x86-64 and arm64, so every platform runs the same ngspice and the acceptance values hold everywhere (D-322, D-327).
- **`spinit`** is written at each start with the code models' paths in single quotes, the only form ngspice takes a path with a space in (D-322).
- **PDFs:** WeasyPrint as in the image (D-205), with Pango, HarfBuzz, fontconfig and glib from conda-forge (pinned lock, macOS 11 and later), found through `DYLD_FALLBACK_LIBRARY_PATH` set inside the process; the app has its own `fonts.conf` (D-324).
- **Data files** are read-only inside the bundle; nothing is written there.
- **Size:** the `.dmg` is about 48 MB.

## 5. Where it keeps things, and Settings

### The Mac app's folders (D-323)

| What | Default |
|---|---|
| Circuits, blocks, models, audio, the server's preferences and settings (`DATA_DIR`) | `~/Library/Application Support/Solum Builder/` |
| Cache: index and results (`CACHE_DIR`) | `~/Library/Caches/Solum Builder/` (Time Machine skips it) |
| The launcher's `settings.json` (the two folders) | `~/Library/Application Support/Solum Builder/`, always, so moving `DATA_DIR` doesn't move it |
| Log | `~/Library/Logs/Solum Builder/solum.log` |

Application Support, not Documents: no permission prompt on first launch, and iCloud doesn't sync it. Documents is a **Change…** away. Folders inside the home folder are kept as `~/…`, so copying Application Support to a new Mac (or Migration Assistant) brings everything; the cache is rebuilt. A damaged `settings.json` gives the defaults.

### One Settings dialog for every version (D-310, D-313)

**File → Settings…** in the page (and **Solum Builder → Settings…**, Cmd-, in the Mac app), built once in `web/settings.js`, for Docker, running from source and the Mac app alike:

| Setting | Mac app | Docker, from source |
|---|---|---|
| Circuits folder | shown, **Change…**, **Show in Finder** | shown read-only, with "set `DATA_DIR` (in `.env` or the environment), then restart"; in a container also the host path (D-313) |
| Cache folder | shown, **Change…** (local, unsynced disks only), **Show in Finder** | the same, `CACHE_DIR` |
| Largest cache size | holds at once, survives a restart | the same |
| Theme | moved here from View → Theme… | the same |

- `GET /api/settings` → `{data_dir, cache_dir, host_data_dir, host_cache_dir, cache_max_gb, cache_used_bytes, can_move_folders, preferences}`; `PUT` for the cache size and the preferences (D-311). `can_move_folders` comes from `CAN_MOVE_FOLDERS`, which only the launcher sets; Change… shows only when the launcher's functions are also on the page (`window.pywebview.api`).
- **The cache size** set in Settings is kept in the server's settings file in `DATA_DIR` and wins over `.env`'s `CACHE_MAX_GB` from then on (D-310). `.env` keeps working as before.
- **Changing the circuits folder:** the launcher checks the folder (`folder_problem`); if the old one holds files the page asks: move them, or leave them and use the new folder as it is. Moving refuses if a name clashes. Then the server is stopped and started again on the new folder in the same process, and the page reloads; unsaved work is asked about first (D-323).
- **Changing the cache folder:** refused in a folder iCloud Drive, Dropbox, OneDrive, Google Drive or Box keeps in sync, and on a network volume (SQLite's locks don't hold there), saying why. Neither folder may be inside the other. The old cache is left where it was (D-323).

## 6. Building it

- **`make mac-app`** on an Apple Silicon Mac, outside the dev image (`scripts/mac_app.sh`). It assumes only Xcode's command-line tools and brings the rest into `build/mac/` (git-ignored): pinned `uv` and `micromamba`, Python 3.12, a venv, ngspice (library and program), the PDF libraries. Nothing is installed on the Mac; `rm -rf build/mac dist` removes it all (D-326).
- **It tests what it ships:** the unit, simulation, rules and acceptance suites against the ngspice it built, then a smoke test of the built app (`scripts/mac_smoke.py`: an empty home folder, starters run, the four PDFs export, a clip renders in a worker, no library loaded from outside the app, nothing left after Quit, a clean log). Then `dist/Solum-Builder-<version>.dmg`, version from `solum/__init__.py` (D-305).
- The UI and parity tests stay the dev image's: the page is the same one.
- First build about 10 minutes and 1.5 GB; later ones 2 to 3 minutes.

## 7. Signing and notarisation

- **Released unsigned, on purpose** (ad-hoc signed, which Apple Silicon requires): the project has no Apple Developer account. The release notes, the README and the guide say so, give the Open Anyway steps, and say that anyone who'd rather not trust the download can build it with `make mac-app` or check it (§8) (D-326).
- **Signing and notarising are ready for when there is a certificate** (D-330): `scripts/mac_sign.sh` signs every Mach-O file inside out with the hardened runtime and a timestamp, then the app, **before the smoke test**; with an App Store Connect key it notarises and staples the app, then the `.dmg`. `make mac-app` runs it when `MAC_SIGN_IDENTITY` is set; the release workflow sets it from its secrets (`MACOS_CERT_P12`, `MACOS_CERT_PASSWORD`, `NOTARY_KEY`, `NOTARY_KEY_ID`, `NOTARY_ISSUER_ID`).
- **Entitlements: none.** Checked with an ad-hoc hardened-runtime build: the smoke test passes with no JIT or unsigned-memory exception. Not yet proved with a real Developer ID: the first signed release is that check (D-330).
- **Bundle id** `com.solumfx.solum-builder`, never to change once released (D-329).

## 8. Releases

- **`.github/workflows/release.yml`** (D-330): on a `v*` tag, on `macos-latest`, in the `release` environment, so it waits for the maintainer's **Approve**. It refuses a tag that isn't `v` + `__version__`, runs the same `make mac-app` from nothing (no caches), writes the `.dmg`'s `.sha256`, attests its provenance (`gh attestation verify`), and makes a **draft release** from `packaging/mac/release-notes.md`. Run by hand (`workflow_dispatch`, from `main`) it builds the `.dmg` as an artifact only, a check before tagging. Pull requests never run it.
- The `.dmg` is named without a space: GitHub renames release files with spaces.
- Only the maintainer pushes `v*` tags (a tag ruleset). The steps, for people and agents, are `docs/maintain/release.md`; the agent drafts *What's new*, the maintainer edits and publishes (D-331).
- Versions: D-328. 1.1.0 is the release with the Mac app and ARM64 Linux.
- The Docker side is unchanged: `git pull`, `docker compose up --build`. Published images are a later version's.

## 9. Process around it (GitHub)

- `main` takes changes by pull request only; the maintainer reviews DECISIONS entries, what can be seen or heard, and scope.
- **Not built yet:** a CI workflow running `make check` on every pull request and on `main` (on x86-64 and on an arm64 runner, so ARM doesn't break unseen, D-327), required by the `main` ruleset, and a "How changes get in" section in `docs/maintain/README.md`. Planned separately.

## 10. Questions settled

- Sign from the first release? No: unsigned, with the Open Anyway steps and `make mac-app` offered (D-326); signing is ready for later (D-330).
- Default circuits folder? Application Support, with Show in Finder and Change… (D-323).
- Where Settings… sits for Docker users? File → Settings…; the theme moved into it (D-310).
- Release notes? Drafted by the agent from what changed since the last tag, edited by the maintainer (D-331).
- An Intel build? No (D-321).
- Minimum macOS? 14 (D-321).
