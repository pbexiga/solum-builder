# Releasing a version

1. **Clean tree on `main`,** everything merged that is going in.
2. **`make check` and `make accept`** both green. Go through the user's test list for
   anything changed since the last release.
3. **Version.** `__version__` in `solum/__init__.py`, the one place it's set (D-305):
   `pyproject.toml`, `/api/health`, Help → About, the exports and the Mac app's `.dmg` read
   it. `X.Y.Z`: Z for fixes and small additions, Y for something new to install or a
   feature users would look for in the release notes, X for a change that breaks
   people's files or setups (D-328).
4. **Format changes.** If the circuit schema changed, its migration and old-version
   fixture are in; `make schema` regenerates `docs/circuit.schema.json`.
5. **Library.** `python3 scripts/models_index.py` leaves no diff; no model is flagged
   *Decide*; `THIRD-PARTY-NOTICES.md` covers anything new.
6. **Docs.** The guide's pages and screenshots match the app; the README's install and
   update steps still work.
7. **Build the image:** `make image`, then run it against an empty data folder and open a
   starter, run it, render audio. The image is built on x86-64 and ARM64 alike (D-327):
   when anything about ngspice or the Dockerfile changed, run `make check` and `make accept`
   on both (an Apple Silicon Mac with Podman is an ARM64 machine).
8. **Build the Mac app** on an Apple Silicon Mac: `make mac-app` (it runs the tests and a
   smoke test itself; [Building the Mac app](mac-app.md)). Quit any copy of the app first.
   Open `dist/Solum Builder-<version>.dmg`, drag the app to Applications, open it, run a
   starter, export a build package, render a clip, and quit: nothing left in Activity
   Monitor. Once in a while, and when what it bundles changed, on a clean user account.
9. **Fresh-clone check:** clone into a new folder, `make dev-image`, `make check`,
   `docker compose up --build`, open the app.
10. **Tag** `vX.Y.Z` on the commit and push the tag. `make image-tar` writes the image for
   copying to a machine that won't build it (`docs/NAS.md`).
11. **GitHub release** for the tag: the notes, and the `.dmg` attached. The notes say the
   app is signed by us, not by Apple, give the Open Anyway steps (as the README does), and
   that `make mac-app` builds the same app from the source.
