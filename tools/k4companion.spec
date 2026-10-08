# PyInstaller spec for K4 Companion, from k4companion.py, which the build
# makes from k4companion with the configuration copied in (see
# .github/workflows/build-windows.yml, build-macos.yml and
# build-linux.yml):
#
#   pyinstaller --noconfirm tools/k4companion.spec
#
# On Windows, k4companion.exe and k4companion-debug.exe, the same program
# with a console for -d and --da output, both from one analysis. On
# macOS, K4 Companion.app; run from Terminal as
# "K4 Companion.app/Contents/MacOS/k4companion", it shows that output
# itself, so there is no second build. On Linux, a k4companion folder
# holding the program, which tools/linux/install.sh installs; it shows
# that output when run from a terminal, as on macOS.
#
# Left out are the parts of Qt that PyQt6 brings along but the program
# never uses, about 16 MB of each .exe: software OpenGL (it draws none;
# Qt's OpenGL modules themselves stay, since pyqtgraph imports them),
# PDF and the image format plugins (the only image it writes is PNG,
# which Qt handles itself), Qt's TLS and the OpenSSL it would use (the
# K4's encrypted connection is Python's own ssl, with its own OpenSSL),
# and Qt's translations. On Linux, likewise Qt's GTK theme, which brings
# GTK itself along (Qt draws the windows the same without it), and its
# network information plugins.

import os
import sys

root = os.path.abspath(os.path.join(SPECPATH, '..'))
macos = sys.platform == 'darwin'
linux = sys.platform.startswith('linux')

unused_files = {
    'opengl32sw.dll',
    'Qt6Pdf.dll',
    'libQt6Pdf.so.6',
    'libcrypto-3-x64.dll',
    'libssl-3-x64.dll',
}
unused_folders = (
    'PyQt6/Qt6/plugins/imageformats/',
    'PyQt6/Qt6/plugins/tls/',
    'PyQt6/Qt6/translations/',
    'PyQt6/Qt6/lib/QtPdf.framework/',
    'PyQt6/Qt6/plugins/platformthemes/libqgtk3.so',
    'PyQt6/Qt6/plugins/networkinformation/',
)

# On Linux, the libraries that are the system's own business, left for
# the system's copies to be used: the audio ones (ALSA, JACK, PortAudio
# and Opus, which K4 Companion's audio and MIDI use, PortAudio's and
# Opus's found by name rather than linked, so a bundled copy would never
# be looked for), which have to agree with the system's sound setup;
# udev, which has to agree with the system's udev; and the C++ runtime,
# which the system's graphics drivers load a newer one of than the
# build machine's. tools/linux/install.sh says what to install where
# PortAudio or Opus is missing.
system_libraries = {
    'libasound.so.2',
    'libjack.so.0',
    'libportaudio.so.2',
    'libopus.so.0',
    'libudev.so.1',
    'libstdc++.so.6',
    'libgcc_s.so.1',
}

def used(entry):
    dest = entry[0].replace('\\', '/')
    name = os.path.basename(dest)
    return (name not in unused_files
            and not (linux and name in system_libraries)
            and not dest.startswith(unused_folders))

if macos:
    # The Opus library, which macOS doesn't have: Homebrew's, named
    # libopus.dylib as opuslib looks for it. OPUS_DYLIB says where it is.
    binaries = [(os.environ['OPUS_DYLIB'], '.')]
elif linux:
    # The system's: see system_libraries.
    binaries = []
else:
    binaries = [(os.path.join(root, 'Contributions', 'opus.dll'), '.')]

a = Analysis(
    [os.path.join(root, 'k4companion.py')],
    binaries=binaries,
    # The K-Pod's module, which the program imports by a name in a
    # variable, so that PyInstaller can't see it: hidraw on Linux, hid
    # elsewhere (see where the program imports it).
    hiddenimports=['hidraw', 'hid'] if linux else ['hid'],
    # The other Qt bindings, so that pyqtgraph's hook picks PyQt6 even
    # where they are installed too. Where there's no splash screen (see
    # below), its module too: it is there to be imported all the same,
    # and says at length that it has no splash screen to close, where
    # without it close_splash_screen() quietly finds nothing to do.
    excludes=['tkinter', 'PyQt5', 'PySide2', 'PySide6'] + (['pyi_splash'] if macos or linux else []),
)
a.binaries = [entry for entry in a.binaries if used(entry)]

def linked_only(binaries):
    # The libraries left in the bundle's top folder that nothing in it
    # links to any longer, taken out until none are: there only for
    # what was left out above. Python's own library stays, which the
    # program loads rather than links to, as do Python's extension
    # modules, which Python loads. Linux only, where a library's links
    # are read with ldd.
    from PyInstaller.depend.bindepend import get_imports
    while True:
        needed = set()
        for dest, source, kind in binaries:
            if kind == 'SYMLINK':
                needed.add(os.path.basename(source))
            else:
                needed.update(os.path.basename(name) for name, path in get_imports(source))
        kept = [(dest, source, kind) for dest, source, kind in binaries
                if kind == 'EXTENSION'
                or '/' in dest.replace('\\', '/')
                or os.path.basename(dest) in needed
                or os.path.basename(dest).startswith('libpython')]
        if len(kept) == len(binaries):
            return kept
        binaries = kept

if linux:
    a.binaries = linked_only(a.binaries)
a.datas = [entry for entry in a.datas if used(entry)]

pyz = PYZ(a.pure)

icon = os.path.join(root, 'Windows', 'k4companion.ico')

if macos:
    # A folder bundle, not one file: PyInstaller no longer builds an app
    # bundle around a one-file program, and one that unpacks itself at
    # every start is slower to and harder for Gatekeeper besides.
    exe = EXE(
        pyz,
        a.scripts,
        [],
        exclude_binaries=True,
        name='k4companion',
        console=False,
        upx=False,
    )
    collected = COLLECT(exe, a.binaries, a.datas, name='k4companion', upx=False)
    version = os.environ.get('K4COMPANION_VERSION', '0')
    BUNDLE(
        collected,
        name='K4 Companion.app',
        # Converted to the .icns macOS wants, which takes Pillow.
        icon=icon,
        bundle_identifier='org.farnsworth.k4companion',
        version=version,
        info_plist={
            'CFBundleDisplayName': 'K4 Companion',
            'CFBundleShortVersionString': version,
            'NSHighResolutionCapable': True,
            # Asked of the user the first time transmit audio opens the
            # microphone; without it macOS refuses the microphone.
            'NSMicrophoneUsageDescription':
                'K4 Companion sends your microphone to the K4 as its transmit audio.',
            # No App Nap: it coalesces timers, and the keyer's waking late
            # for them is what the sidetone delay was found growing from.
            'NSAppSleepDisabled': True,
        },
    )
elif linux:
    # A folder, as on macOS, and for the same reason of starting faster:
    # each panadapter window is the program started again, which a
    # single file would unpack anew every time.
    exe = EXE(
        pyz,
        a.scripts,
        [],
        exclude_binaries=True,
        name='k4companion',
        console=True,
        upx=False,
    )
    COLLECT(exe, a.binaries, a.datas, name='k4companion', upx=False)
else:
    # Shown by the .exe while it unpacks itself and Python imports Qt
    # and the rest, until close_splash_screen() takes it down. Scaled to
    # fit 760x480, which takes Pillow at build time. Windows only:
    # PyInstaller has no splash screen on macOS.
    splash = Splash(
        os.path.join(root, 'tools', 'k4_splash.png'),
        binaries=a.binaries,
        datas=a.datas,
    )

    for name, console in (('k4companion', False), ('k4companion-debug', True)):
        EXE(
            pyz,
            a.scripts,
            splash,
            splash.binaries,
            a.binaries,
            a.datas,
            [],
            name=name,
            console=console,
            icon=icon,
            upx=False,
        )
