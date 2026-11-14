# PyInstaller spec for the Mac app (D-321). Run by scripts/mac_app.sh, which sets
# SOLUM_MAC_BUILD to the build folder (ngspice, the icon) and puts the PDF libraries on
# DYLD_FALLBACK_LIBRARY_PATH for PyInstaller's WeasyPrint hook to find.
import os
from pathlib import Path

REPO = Path(SPECPATH).resolve().parents[1]
BUILD = Path(os.environ["SOLUM_MAC_BUILD"])
NG = BUILD / "ngspice"
BUNDLE_ID = "io.github.solum-builder"  # the same as solum/desktop/window.py's
MIN_MACOS = "14.0"  # what ngspice is built for; every other library allows less (D-322)

scope: dict = {}
exec((REPO / "solum" / "__init__.py").read_text(), scope)
VERSION = scope["__version__"]

a = Analysis(
    [str(REPO / "packaging" / "mac" / "launch.py")],
    pathex=[str(REPO)],
    binaries=[(str(NG / "lib" / "libngspice.0.dylib"), "ngspice/lib")]
    + [(str(p), "ngspice/lib/ngspice") for p in sorted((NG / "lib" / "ngspice").glob("*.cm"))],
    datas=[
        (str(REPO / "library"), "library"),
        (str(REPO / "web"), "web"),
        (str(REPO / "docs" / "guide"), "docs/guide"),
        (str(REPO / "packaging" / "mac" / "fonts.conf"), "fonts"),
    ],
    hiddenimports=["solum.api.app"],
    excludes=["pytest", "hypothesis", "mypy", "ruff", "playwright", "tkinter", "cairosvg"],
    noarchive=False,
)
pyz = PYZ(a.pure)
exe = EXE(
    pyz, a.scripts, [], exclude_binaries=True, name="Solum Builder",
    console=False, target_arch="arm64", codesign_identity=None, entitlements_file=None,
)
coll = COLLECT(exe, a.binaries, a.datas, name="Solum Builder")
app = BUNDLE(
    coll,
    name="Solum Builder.app",
    icon=str(BUILD / "SolumBuilder.icns"),
    bundle_identifier=BUNDLE_ID,
    version=VERSION,
    info_plist={
        "CFBundleShortVersionString": VERSION,
        "LSMinimumSystemVersion": MIN_MACOS,
        "NSHighResolutionCapable": True,
        "NSHumanReadableCopyright": "See THIRD-PARTY-NOTICES.md for what the app carries.",
    },
)
