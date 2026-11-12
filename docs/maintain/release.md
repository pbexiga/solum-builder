# Releasing a version

1. **Clean tree on `main`,** everything merged that is going in.
2. **`make check` and `make accept`** both green. Go through the user's test list for
   anything changed since the last release.
3. **Version.** `__version__` in `solum/__init__.py`, the one place it's set (D-305):
   `pyproject.toml`, `/api/health`, Help → About and the exports read it.
4. **Format changes.** If the circuit schema changed, its migration and old-version
   fixture are in; `make schema` regenerates `docs/circuit.schema.json`.
5. **Library.** `python3 scripts/models_index.py` leaves no diff; no model is flagged
   *Decide*; `THIRD-PARTY-NOTICES.md` covers anything new.
6. **Docs.** The guide's pages and screenshots match the app; the README's install and
   update steps still work.
7. **Build the image:** `make image`, then run it against an empty data folder and open a
   starter, run it, render audio.
8. **Fresh-clone check:** clone into a new folder, `make dev-image`, `make check`,
   `docker compose up --build`, open the app.
9. **Tag** `vX.Y.Z` on the commit and push the tag. `make image-tar` writes the image for
   copying to a machine that won't build it (`docs/NAS.md`).
