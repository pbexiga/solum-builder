#!/bin/bash
# `make mac-app` (D-326): build the Mac app from this checkout, bringing everything it and
# its tests need into build/mac/ (git-ignored). Needs only an Apple Silicon Mac with
# Xcode's command-line tools. Writes dist/Solum Builder-<version>.dmg.
#   SKIP_TESTS=1   leave the test suites out (the app's own smoke test still runs)
# How it works and how to update what it pins: docs/maintain/mac-app.md
set -euo pipefail

REPO="$(cd "$(dirname "$0")/.." && pwd)"
BUILD="$REPO/build/mac"
DIST="$REPO/dist"
TOOLS="$BUILD/tools"
cd "$REPO"

# What the build pins. A changed download fails its checksum and stops the build.
PYTHON_VERSION=3.12
UV_VERSION=0.11.8
UV_SHA256=c729adb365114e844dd7f9316313a7ed6443b89bb5681d409eebac78b0bd06c8
MAMBA_VERSION=2.10.0-0
MAMBA_SHA256=c547639f5caf742236641c362746abb4a3505774753ecd08fe341643670c4c01
NGSPICE_VERSION=44.2  # the Docker image's (Debian trixie): the acceptance values hold
NGSPICE_SHA256=e7dadfb7bd5474fd22409c1e5a67acdec19f77e597df68e17c5549bc1390d7fd
NGSPICE_URL="https://sourceforge.net/projects/ngspice/files/ng-spice-rework/old-releases/$NGSPICE_VERSION/ngspice-$NGSPICE_VERSION.tar.gz/download"
export MACOSX_DEPLOYMENT_TARGET=14.0
# No fused multiply-add: with it, transients through op-amp macro-models stop with
# "Timestep too small" on arm64 (D-322). The second C++ flag is for Apple clang 21.
NG_CFLAGS="-O2 -ffp-contract=off"
NG_CXXFLAGS="-O2 -ffp-contract=off -Wno-invalid-specialization"
NG_OPTIONS="--enable-xspice --enable-cider --enable-osdi --enable-klu --disable-debug --disable-openmp"

say() { printf '\n== %s\n' "$*"; }
fail() { printf '\nmake mac-app: %s\n' "$*" >&2; exit 1; }

fetch() {  # fetch URL FILE SHA256
  [ -f "$2" ] || curl --fail --silent --show-error --location --output "$2" "$1"
  echo "$3  $2" | shasum -a 256 --check --status || {
    rm -f "$2"
    fail "$(basename "$2") isn't the file expected (checksum). Nothing was used; run it again, and if it repeats, see docs/maintain/mac-app.md."
  }
}

[ "$(uname -s)" = Darwin ] && [ "$(uname -m)" = arm64 ] || fail "the Mac app is built on an Apple Silicon Mac."
xcode-select -p >/dev/null 2>&1 || fail "Xcode's command-line tools are missing. Install them with: xcode-select --install"
mkdir -p "$TOOLS" "$DIST"

say "Tools (uv $UV_VERSION, micromamba $MAMBA_VERSION)"
if [ ! -x "$TOOLS/uv" ]; then
  fetch "https://github.com/astral-sh/uv/releases/download/$UV_VERSION/uv-aarch64-apple-darwin.tar.gz" "$TOOLS/uv.tar.gz" "$UV_SHA256"
  tar -xzf "$TOOLS/uv.tar.gz" -C "$TOOLS" --strip-components 1 uv-aarch64-apple-darwin/uv
fi
if [ ! -x "$TOOLS/micromamba" ]; then
  fetch "https://github.com/mamba-org/micromamba-releases/releases/download/$MAMBA_VERSION/micromamba-osx-arm64" "$TOOLS/micromamba.download" "$MAMBA_SHA256"
  cp "$TOOLS/micromamba.download" "$TOOLS/micromamba" && chmod +x "$TOOLS/micromamba"
fi
# everything uv and micromamba keep stays in the build folder
export UV_PYTHON_INSTALL_DIR="$BUILD/uv-python" UV_CACHE_DIR="$BUILD/uv-cache" UV_PYTHON_PREFERENCE=only-managed
export MAMBA_ROOT_PREFIX="$BUILD/mamba-root"

say "Python $PYTHON_VERSION and the packages"
[ -x "$BUILD/venv/bin/python" ] || "$TOOLS/uv" venv --quiet --python "$PYTHON_VERSION" "$BUILD/venv"
"$TOOLS/uv" pip install --quiet --python "$BUILD/venv/bin/python" -e '.[dev,mac]' cairosvg
PY="$BUILD/venv/bin/python"

NG="$BUILD/ngspice"
NG_STAMP="$NGSPICE_VERSION|$MACOSX_DEPLOYMENT_TARGET|$NG_CFLAGS|$NG_CXXFLAGS|$NG_OPTIONS"
if [ "$(cat "$NG/.built" 2>/dev/null)" != "$NG_STAMP" ]; then
  say "ngspice $NGSPICE_VERSION: the library and the program (about 6 minutes, once)"
  SRC="$BUILD/ngspice-src"
  rm -rf "$NG" "$SRC" && mkdir -p "$SRC"
  fetch "$NGSPICE_URL" "$BUILD/ngspice-$NGSPICE_VERSION.tar.gz" "$NGSPICE_SHA256"
  tar -xzf "$BUILD/ngspice-$NGSPICE_VERSION.tar.gz" -C "$SRC" --strip-components 1
  for kind in library program; do  # the program: for the tests of exported netlists (D-206)
    mkdir -p "$SRC/build-$kind"
    ( cd "$SRC/build-$kind"
      shared=$([ $kind = library ] && echo --with-ngshared || echo "--without-x --with-readline=no")
      # shellcheck disable=SC2086
      ../configure $shared $NG_OPTIONS --prefix="$NG" CFLAGS="$NG_CFLAGS" CXXFLAGS="$NG_CXXFLAGS" >configure.log 2>&1 \
        && make -j"$(sysctl -n hw.ncpu)" >make.log 2>&1 && make install >install.log 2>&1 ) \
      || fail "ngspice ($kind) didn't build; see $SRC/build-$kind/*.log"
  done
  echo "$NG_STAMP" >"$NG/.built"
fi

LIBS="$BUILD/pdflibs"
LOCK="$REPO/packaging/mac/pdflibs.lock"
if ! cmp -s "$LOCK" "$LIBS/.lock" 2>/dev/null; then
  say "The PDF libraries (Pango, HarfBuzz, fontconfig) from conda-forge"
  rm -rf "$LIBS"
  "$TOOLS/micromamba" create --yes --quiet --prefix "$LIBS" --file "$LOCK" >/dev/null
  cp "$LOCK" "$LIBS/.lock"
fi

# The libraries are found by this variable (ctypes.util.find_library reads it). macOS
# strips DYLD_* from the environment of its own programs (make, sh, env), so it is set
# here, on the lines that start our Python, and nowhere earlier.
FOUND="$NG/lib:$LIBS/lib"

if [ -z "${SKIP_TESTS:-}" ]; then
  say "Tests against this ngspice: unit, simulation, rules, acceptance"
  PATH="$BUILD/venv/bin:$NG/bin:$PATH" DYLD_FALLBACK_LIBRARY_PATH="$FOUND" \
    "$PY" -m pytest -q -n auto -m "not timing" tests/unit tests/sim tests/rules
  PATH="$BUILD/venv/bin:$NG/bin:$PATH" DYLD_FALLBACK_LIBRARY_PATH="$FOUND" \
    "$PY" -m pytest -q -n 4 --dist loadfile -m "not timing" tests/acceptance
fi

say "The app"
rm -rf "$BUILD/SolumBuilder.iconset"
DYLD_FALLBACK_LIBRARY_PATH="$FOUND" "$PY" scripts/mac_icon.py "$BUILD/SolumBuilder.iconset"
iconutil --convert icns --output "$BUILD/SolumBuilder.icns" "$BUILD/SolumBuilder.iconset"
rm -rf "$DIST/Solum Builder.app" "$DIST/Solum Builder"
SOLUM_MAC_BUILD="$BUILD" DYLD_FALLBACK_LIBRARY_PATH="$FOUND" "$PY" -m PyInstaller --noconfirm \
  --distpath "$DIST" --workpath "$BUILD/pyinstaller" packaging/mac/solum.spec >"$BUILD/pyinstaller.log" 2>&1 \
  || fail "PyInstaller failed; see $BUILD/pyinstaller.log"
rm -rf "$DIST/Solum Builder"  # PyInstaller's folder form; the .app is what ships
APP="$DIST/Solum Builder.app"
codesign --verify --deep "$APP" || fail "the app's (ad-hoc) signature doesn't verify."

say "Smoke test of the built app"
"$PY" scripts/mac_smoke.py "$APP" "$BUILD"

VERSION="$("$PY" -c 'import solum; print(solum.__version__)')"
DMG="$DIST/Solum Builder-$VERSION.dmg"
say "The disk image"
STAGE="$BUILD/dmg"
rm -rf "$STAGE" "$DMG" && mkdir -p "$STAGE"
cp -R "$APP" "$STAGE/" && ln -s /Applications "$STAGE/Applications"
hdiutil create -quiet -volname "Solum Builder" -srcfolder "$STAGE" -format UDZO "$DMG"
rm -rf "$STAGE"
printf '\nBuilt %s (%s), unsigned.\n' "$DMG" "$(du -h "$DMG" | cut -f1)"
