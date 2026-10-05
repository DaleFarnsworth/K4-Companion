# PyInstaller spec for k4companion.exe and k4companion-debug.exe, the
# same program with a console for -d and --da output. Both come from one
# analysis of k4companion.py, which the build makes from k4companion with
# the configuration copied in (see .github/workflows/build-windows.yml):
#
#   pyinstaller --noconfirm tools/k4companion.spec
#
# Left out are the parts of Qt that PyQt6 brings along but the program
# never uses, about 16 MB of each .exe: software OpenGL (it draws none;
# Qt's OpenGL modules themselves stay, since pyqtgraph imports them),
# PDF and the image format plugins (the only image it writes is PNG,
# which Qt handles itself), Qt's TLS and the OpenSSL it would use (the
# K4's encrypted connection is Python's own ssl, with its own OpenSSL),
# and Qt's translations.

import os

root = os.path.abspath(os.path.join(SPECPATH, '..'))

unused_files = {
    'opengl32sw.dll',
    'Qt6Pdf.dll',
    'libcrypto-3-x64.dll',
    'libssl-3-x64.dll',
}
unused_folders = (
    'PyQt6/Qt6/plugins/imageformats/',
    'PyQt6/Qt6/plugins/tls/',
    'PyQt6/Qt6/translations/',
)

def used(entry):
    dest = entry[0].replace('\\', '/')
    return (os.path.basename(dest) not in unused_files
            and not dest.startswith(unused_folders))

a = Analysis(
    [os.path.join(root, 'k4companion.py')],
    binaries=[(os.path.join(root, 'Contributions', 'opus.dll'), '.')],
    # The other Qt bindings, so that pyqtgraph's hook picks PyQt6 even
    # where they are installed too.
    excludes=['tkinter', 'PyQt5', 'PySide2', 'PySide6'],
)
a.binaries = [entry for entry in a.binaries if used(entry)]
a.datas = [entry for entry in a.datas if used(entry)]

pyz = PYZ(a.pure)

for name, console in (('k4companion', False), ('k4companion-debug', True)):
    EXE(
        pyz,
        a.scripts,
        a.binaries,
        a.datas,
        [],
        name=name,
        console=console,
        icon=os.path.join(root, 'Windows', 'k4companion.ico'),
        upx=False,
    )
