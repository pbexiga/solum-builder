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
   Open `dist/Solum-Builder-<version>.dmg`, drag the app to Applications, open it, run a
   starter, export a build package, render a clip, and quit: nothing left in Activity
   Monitor. Once in a while, and when what it bundles changed, on a clean user account.
   To check the runner builds it too before tagging: Actions → **Release** → Run workflow
   on `main`, Approve; the `.dmg` comes back as the run's artifact.
9. **Fresh-clone check:** clone into a new folder, `make dev-image`, `make check`,
   `docker compose up --build`, open the app.
10. **Tag** `vX.Y.Z` on `main`'s merged commit and push the tag (`git tag vX.Y.Z`,
   `git push origin vX.Y.Z`). `make image-tar` writes the image for copying to a machine
   that won't build it (`docs/NAS.md`).
11. **Approve the release build.** The tag starts the **Release** workflow
   (`.github/workflows/release.yml`, D-330); it waits in the `release` environment until you
   click **Review deployments → Approve** on the run. Then GitHub's macOS runner checks the
   tag is `v` + `__version__`, runs the same `make mac-app` (tests, app, smoke test, `.dmg`),
   attests where the `.dmg` came from and makes a **draft release** with the `.dmg` and its
   `.sha256` (about 20 minutes).
12. **Finish the draft.** Download its `.dmg` and open it on your Mac: it must ask for Open
   Anyway (it's the downloaded one now), then run a starter. Write *What's new* in the notes
   (the template, `packaging/mac/release-notes.md`, has the rest: the Open Anyway steps, that
   it's signed by us and not by Apple, `make mac-app`, how to check the download, Docker's
   update). Once the app is signed by a Developer ID, replace the template's "Why macOS asks"
   paragraph. Then **Publish release**.

## Once, in the repository's settings

- **Environments → New environment `release`**: Required reviewers, yourself; *Prevent
  self-review* off (you are the one who tags). Deployment branches and tags: *Selected*,
  the tag rule `v*` and the branch `main`.
- **Rules → New tag ruleset** for `v*`: restrict creations, updates and deletions, with
  yourself (repository admin) in the bypass list, so only you can push a release tag.
- **Signing, when there's an Apple Developer account** (the workflow signs only when they
  exist): in the `release` environment's secrets, `MACOS_CERT_P12` (the Developer ID
  Application certificate and its key exported as `.p12`, base64: `base64 -i cert.p12 | pbcopy`),
  `MACOS_CERT_PASSWORD`, and for notarising `NOTARY_KEY` (the App Store Connect API key's
  `.p8` text), `NOTARY_KEY_ID`, `NOTARY_ISSUER_ID`. Environment secrets reach only jobs you
  approved; pull requests never run this workflow. A leaked certificate: revoke it in the
  Apple account and make a new one.
