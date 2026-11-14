## What's new

<!-- Write this by hand before publishing: what a user would look for, in plain words. -->

## The Mac app (Apple Silicon, macOS 14 or later)

1. Download **Solum-Builder-@VERSION@.dmg** below.
2. Open it and drag **Solum Builder** to **Applications**.
3. Open it from Applications. The first time, macOS says it can't check the app for malicious software. Open **System Settings → Privacy & Security**, scroll down to **Security**, and click **Open Anyway** next to *Solum Builder*; confirm. After that it opens with a double-click. (Again once for each new version.)

**Why macOS asks.** The app is signed by us, not by Apple: the project has no Apple Developer account, so the app isn't notarised and macOS doesn't know who made it. If you'd rather not trust a download, build the same app yourself from this tag: on an Apple Silicon Mac with Xcode's command-line tools, `make mac-app` ([Building the Mac app](https://github.com/@REPO@/blob/@TAG@/docs/maintain/mac-app.md)).

**Checking the download.** This `.dmg` was built by GitHub from the tagged commit, not on anyone's computer. Its SHA-256 is in `Solum-Builder-@VERSION@.dmg.sha256`, and with GitHub's command-line tool you can check where it came from:

    gh attestation verify Solum-Builder-@VERSION@.dmg --repo @REPO@

To update, drag the new app to Applications, replacing the old one: your circuits are kept.

## Docker (any computer)

    git pull
    docker compose up --build

Then open http://localhost:8000. Intel Macs use Docker.
