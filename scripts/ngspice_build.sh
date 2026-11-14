#!/bin/sh
# ngspice for Solum Builder, built the same way everywhere (D-327): the Docker image (both
# architectures) and `make mac-app` run this, so the version, checksum, flags and options
# live here only. Builds the shared library (the app's) and the program (the tests of
# exported netlists, D-206) into PREFIX, from the release tarball kept in WORKDIR.
#   ngspice_build.sh PREFIX WORKDIR
#   NG_EXTRA_CXXFLAGS  added to the C++ flags (the Mac's Apple clang needs one)
# Needs a C and C++ compiler and make; nothing else (no X, no readline, no FFTW).
set -eu

NGSPICE_VERSION=44.2  # the acceptance values were measured with 44.2: change it only with them
NGSPICE_SHA256=e7dadfb7bd5474fd22409c1e5a67acdec19f77e597df68e17c5549bc1390d7fd
NGSPICE_URL="https://sourceforge.net/projects/ngspice/files/ng-spice-rework/old-releases/$NGSPICE_VERSION/ngspice-$NGSPICE_VERSION.tar.gz/download"
# No fused multiply-add: with it (clang and gcc on arm64 fuse a*b+c by default), transients
# through op-amp macro-models stop with "Timestep too small" (D-322, D-327).
NG_CFLAGS="-O2 -ffp-contract=off"
NG_CXXFLAGS="-O2 -ffp-contract=off ${NG_EXTRA_CXXFLAGS:-}"
NG_OPTIONS="--enable-xspice --enable-cider --enable-osdi --enable-klu --disable-debug --disable-openmp"

[ $# -eq 2 ] || { echo "usage: $0 PREFIX WORKDIR" >&2; exit 2; }
PREFIX="$1"
WORK="$2"
mkdir -p "$WORK"
TARBALL="$WORK/ngspice-$NGSPICE_VERSION.tar.gz"
SRC="$WORK/ngspice-src"

# Linux has GNU's sha256sum, macOS shasum (and, since 27, a BSD sha256sum without
# GNU's options): only the printed digest is the same, so that is what's compared.
if command -v shasum >/dev/null; then sha() { shasum -a 256 "$1"; }; else sha() { sha256sum "$1"; }; fi
[ -f "$TARBALL" ] || curl --fail --silent --show-error --location --output "$TARBALL" "$NGSPICE_URL"
[ "$(sha "$TARBALL" | cut -d' ' -f1)" = "$NGSPICE_SHA256" ] || {
  rm -f "$TARBALL"
  echo "ngspice-$NGSPICE_VERSION.tar.gz isn't the file expected (checksum); nothing was built. Run it again; if it repeats, see docs/maintain/mac-app.md." >&2
  exit 1
}
JOBS="$(nproc 2>/dev/null || sysctl -n hw.ncpu)"

rm -rf "$SRC" && mkdir -p "$SRC"
tar -xzf "$TARBALL" -C "$SRC" --strip-components 1
for kind in library program; do
  mkdir -p "$SRC/build-$kind"
  if [ $kind = library ]; then shared=--with-ngshared; else shared="--without-x --with-readline=no"; fi
  # shellcheck disable=SC2086
  ( cd "$SRC/build-$kind" \
    && ../configure $shared $NG_OPTIONS --prefix="$PREFIX" CFLAGS="$NG_CFLAGS" CXXFLAGS="$NG_CXXFLAGS" >configure.log 2>&1 \
    && make -j"$JOBS" >make.log 2>&1 && make install >install.log 2>&1 ) || {
    echo "ngspice ($kind) didn't build; see $SRC/build-$kind/*.log" >&2
    tail -n 30 "$SRC/build-$kind/"*.log >&2
    exit 1
  }
done
rm -rf "$SRC"
echo "ngspice $NGSPICE_VERSION built into $PREFIX"
