#!/bin/bash
# Signing and notarising the Mac app (D-330): run by scripts/mac_app.sh only when
# MAC_SIGN_IDENTITY is set; without it the app stays ad-hoc signed (D-326).
#   mac_sign.sh app APP          sign every binary inside out, then the app, with the
#                                hardened runtime and packaging/mac/entitlements.plist
#   mac_sign.sh dmg DMG          sign the disk image
#   mac_sign.sh notarise FILE    send an app or a disk image to Apple and staple the ticket
# MAC_SIGN_IDENTITY  a "Developer ID Application: …" certificate in a keychain, or "-"
#                    (ad hoc, with the hardened runtime: a check of the entitlements on a
#                    Mac with no certificate; it can't be notarised)
# NOTARY_KEY_FILE, NOTARY_KEY_ID, NOTARY_ISSUER_ID   an App Store Connect API key (notarise)
set -euo pipefail

REPO="$(cd "$(dirname "$0")/.." && pwd)"
ENTITLEMENTS="$REPO/packaging/mac/entitlements.plist"
ID="${MAC_SIGN_IDENTITY:?MAC_SIGN_IDENTITY names the certificate to sign with}"
fail() { printf '\nmac_sign.sh: %s\n' "$*" >&2; exit 1; }

# Ad hoc has no timestamp server; a real identity must have a secure timestamp to notarise.
# Nor has it a Team ID, and the hardened runtime loads only libraries of the program's own
# team: the ad-hoc check turns library validation off, which a Developer ID build doesn't need.
if [ "$ID" = - ]; then
  STAMP=--timestamp=none
  cp "$ENTITLEMENTS" "${TMPDIR:-/tmp}/solum-adhoc.plist"
  ENTITLEMENTS="${TMPDIR:-/tmp}/solum-adhoc.plist"
  /usr/libexec/PlistBuddy -c "Add :com.apple.security.cs.disable-library-validation bool true" "$ENTITLEMENTS"
else
  STAMP=--timestamp
fi
sign() {  # codesign, without its line for each signature it replaces (ad hoc, PyInstaller's)
  codesign --force --sign "$ID" "$STAMP" "$@" 2>&1 | { grep -v ': replacing existing signature$' || true; }
}

sign_app() {
  local app="$1" file
  [ -d "$app/Contents/MacOS" ] || fail "$app isn't an app bundle."
  # Every Mach-O file but the app's own program (libraries, Python's extension modules,
  # ngspice's code models), deepest first, so each is signed before what holds it.
  # Symbolic links are left alone: what they point at is signed.
  while IFS= read -r file; do
    sign --options runtime "$file"
  done < <(find "$app/Contents" -type f ! -path "$app/Contents/MacOS/*" -print0 \
    | xargs -0 file -N -F '|' | grep '| *Mach-O' | cut -d'|' -f1 \
    | awk -F/ '{ print NF "\t" $0 }' | sort -rn | cut -f2-)
  for file in "$app/Contents/MacOS/"*; do
    [ -L "$file" ] || sign --options runtime --entitlements "$ENTITLEMENTS" "$file"
  done
  sign --options runtime --entitlements "$ENTITLEMENTS" "$app"
  codesign --verify --strict --deep "$app" || fail "the signature of $app doesn't verify."
}

notarise() {
  local file="$1" zip=""
  [ "$ID" != - ] || fail "an ad-hoc signed build can't be notarised."
  : "${NOTARY_KEY_FILE:?}" "${NOTARY_KEY_ID:?}" "${NOTARY_ISSUER_ID:?}"
  if [ -d "$file" ]; then  # an app goes to Apple as a zip; the ticket is stapled to the app
    zip="$(mktemp -d)/$(basename "$file").zip"
    ditto -c -k --keepParent "$file" "$zip"
  fi
  xcrun notarytool submit "${zip:-$file}" --wait --timeout 1h \
    --key "$NOTARY_KEY_FILE" --key-id "$NOTARY_KEY_ID" --issuer "$NOTARY_ISSUER_ID" \
    --output-format json | tee "${TMPDIR:-/tmp}/notarytool.json"
  [ -z "$zip" ] || rm -rf "$(dirname "$zip")"
  grep -q '"status" *: *"Accepted"' "${TMPDIR:-/tmp}/notarytool.json" \
    || fail "Apple didn't accept $(basename "$file") (above; 'xcrun notarytool log <id>' says why)."
  xcrun stapler staple "$file"
  xcrun stapler validate "$file"
}

case "${1:-} ${2:+x}" in
  "app x") sign_app "$2" ;;
  "dmg x") sign "$2" && codesign --verify --strict "$2" ;;
  "notarise x") notarise "$2" ;;
  *) echo "usage: $0 app APP | dmg DMG | notarise FILE" >&2; exit 2 ;;
esac
