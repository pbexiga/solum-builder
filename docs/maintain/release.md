# Releasing a version

The same steps every time, whoever does them. An agent asked to release follows this page
in order, does the steps marked *(agent)*, and stops for the maintainer at the ones that
are theirs: merging, tagging, approving and publishing (D-331).

1. **Clean tree on `main`,** everything merged that is going in.
2. **`make check` and `make accept`** both green. Go through the user's test list for
   anything changed since the last release.
3. **Version.** `__version__` in `solum/__init__.py`, the one place it's set (D-305):
   `pyproject.toml`, `/api/health`, Help → About, the exports and the Mac app's `.dmg` read
   it. `X.Y.Z`: Z for fixes and small additions, Y for something new to install or a
   feature users would look for in the release notes, X for a change that breaks
   people's files or setups (D-328). *(agent)* Propose the number from what changed since
   the last tag (`git log <last tag>..main`, the D-entries added since), with a line on
   why, and let the maintainer agree it; then the bump goes in its own release pull
   request, with nothing else in it but the notes it needs.
4. **Format changes.** If the circuit schema changed, its migration and old-version
   fixture are in; `make schema` regenerates `docs/circuit.schema.json`.
5. **Library.** `python3 scripts/models_index.py` leaves no diff; no model is flagged
   *Decide*; `THIRD-PARTY-NOTICES.md` covers anything new.
6. **Docs.** The guide's pages and screenshots match the app; the README's install and
   update steps still work.
7. **Build the image:** `make image`, then run it against an empty data folder and open a
   starter, run it, render audio. The image is built on x86-64 and ARM64 alike (D-327);
   the release run tests both on GitHub's Linux runners ([The Linux checks](#the-linux-checks)),
   so a local run on one is enough (an Apple Silicon Mac with Podman is an ARM64 machine).
8. **Build the Mac app** on an Apple Silicon Mac: `make mac-app` (it runs the tests and a
   smoke test itself; [Building the Mac app](mac-app.md)). Quit any copy of the app first.
   Open `dist/Solum-Builder-<version>.dmg`, drag the app to Applications, open it, run a
   starter, export a build package, render a clip, and quit: nothing left in Activity
   Monitor. Once in a while, and when what it bundles changed, on a clean user account.
   To check the runners before tagging: Actions → **Release** → Run workflow on `main`,
   Approve; the Linux rows run too, and the `.dmg` comes back as the run's artifact.
9. **Fresh-clone check** *(optional)*: clone into a new folder, `make dev-image`, `make check`,
   `docker compose up --build`, open the app. The release run's Linux rows do this on clean
   machines (D-346); do it by hand when the Linux checks are off, or after a change to
   `compose.yaml` or `.env.example`, which the rows don't use.
10. **Tag** `vX.Y.Z` on `main`'s merged commit and push the tag (`git tag vX.Y.Z`,
   `git push origin vX.Y.Z`). `make image-tar` writes the image for copying to a machine
   that won't build it (`docs/NAS.md`).
11. **Approve the release build.** The tag starts the **Release** workflow
   (`.github/workflows/release.yml`, D-330, D-346). The two Linux rows start at once
   ([The Linux checks](#the-linux-checks)); the Mac build waits in the `release` environment
   until you click **Review deployments → Approve** on the run. Then GitHub's macOS runner
   checks the tag is `v` + `__version__`, runs the same `make mac-app` (tests, app, smoke
   test, `.dmg`) and attests where the `.dmg` came from (about 20 minutes). When the Mac build
   and both Linux rows are green, the `draft` job makes a **draft release** with the `.dmg`
   and its `.sha256`. Any of them red: no draft.
12. **Finish the draft.** Download its `.dmg` and open it on your Mac: it must ask for Open
   Anyway (it's the downloaded one now), then run a starter. Paste *What's new* into the
   notes (drafted in step 13; the template, `packaging/mac/release-notes.md`, has the rest: the Open Anyway steps, that
   it's signed by us and not by Apple, `make mac-app`, how to check the download, Docker's
   update). Once the app is signed by a Developer ID, replace the template's "Why macOS asks"
   paragraph. Then **Publish release**.
13. **What's new** *(agent, while the build runs)*: drafted for the maintainer to edit and
   paste, never published by the agent. From `git log <last tag>..v<new>`, the pull
   requests merged since and the D-entries added since: what a user would look for, in
   the guide's plain words (DESIGN.md), not how it was built. Grouped as **New**,
   **Better**, **Fixed**, a line each, the biggest first; anything that changes what
   people must do (a moved folder, a migration, a new requirement) at the top, said
   plainly. No D-numbers, branch names or test counts. Given to the maintainer as
   Markdown in the conversation, ready to paste under the draft's *What's new* heading.

## The Linux checks

What a local run on the Mac misses is x86-64 Linux (Podman on an Apple Silicon Mac is ARM64)
and a clean machine. So the release run tests Linux on GitHub's runners, on the tag, beside
the Mac build (D-346); pull requests aren't checked, since the maintainer and the agent run
`make check` and `make accept` before every one.

- **What runs.** The `linux` job, one row per machine on the run's page:
  **Linux (ubuntu-24.04)** (x86-64) and **Linux (ubuntu-24.04-arm)** (ARM64), at the same
  time. Each builds the dev image (its layers kept between releases in GitHub's cache, so
  the ngspice build runs only when the Dockerfile or its recipe changes), runs `make check`,
  then `make accept` (the 25 known gaps stay strict xfails: one that starts passing turns
  the row red, as locally), builds the runtime image, starts it on empty data and cache
  folders as compose does, checks `/api/health` and runs the TS808 through `/api/run`.
  About 15 minutes each, no secrets, read-only.
- **A red row** means no draft release: the Mac build may finish, but `draft` doesn't run.
  GitHub emails whoever started the run (pushed the tag). Open the row, read the failed
  step. A real failure: fix it on a branch, merge, and release a new patch version (`vX.Y.Z+1`).
  A flaky one (a runner's hiccup): **Re-run failed jobs** on the run; when they pass, `draft`
  runs. Don't move a published tag; an unpublished one may be deleted and pushed again
  (`git push origin :vX.Y.Z`, then tag the fixed commit).
- **The switch: repository variable `LINUX_CHECKS`** (Settings → Secrets and variables →
  Actions → Variables), no code change: unset or `both` runs both rows; `x64` only x86-64;
  `arm` only ARM64; `off` none (the draft then waits only for the Mac build). If one row is
  to go, drop ARM64 (`x64`): the Mac tests ARM64 locally, x86-64 is the gap. Any other value
  runs both.
- **Dropping `make accept` alone:** delete the *make accept* step from the `linux` job.
- **Removing the Linux checks:** delete the `linux` job, and `linux` from the `draft` job's
  `needs` and its `if` (`needs.linux.result …`).

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
