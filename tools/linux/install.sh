#!/bin/sh

# Installs K4 Companion on Linux, from the folder the installer has just
# unpacked itself into (see .github/workflows/build-linux.yml), which
# holds this script, the k4companion folder PyInstaller builds (see
# tools/k4companion.spec) and the icon.
#
# Run as yourself, it installs for you alone, needing no root:
#   ~/.local/share/k4companion        the program
#   ~/.local/bin/k4companion          a link to it, to run from a terminal
#   ~/.local/share/applications       its entry in the desktop's menu
# Run with sudo, it installs for everyone, in /opt/k4companion,
# /usr/local/bin and /usr/share, and adds the udev rule that lets the
# K-Pod be opened without root. Either way, installing again replaces
# what is there, and an uninstall script is left with the program.
# Settings are in ~/.config/k4companion, which neither touches.

set -e

here=$(cd "$(dirname "$0")" && pwd)

if [ "$(id -u)" = 0 ]; then
	prefix=/opt/k4companion
	bin=/usr/local/bin
	share=/usr/share
	udev_rule=/etc/udev/rules.d/70-kpod.rules
else
	share=${XDG_DATA_HOME:-$HOME/.local/share}
	prefix=$share/k4companion
	bin=$HOME/.local/bin
	udev_rule=
fi
apps=$share/applications
icons=$share/icons/hicolor/96x96/apps

# A previous installation is replaced, but nothing else is: a folder of
# the same name that isn't one is left for its owner to deal with.
if [ -e "$prefix" ]; then
	if [ ! -x "$prefix/k4companion" ] || [ ! -f "$prefix/uninstall" ]; then
		echo "$prefix exists, but is not a K4 Companion installation. Not installing." >&2
		exit 1
	fi
	rm -rf "$prefix"
fi

echo "Installing K4 Companion in $prefix"
mkdir -p "$prefix" "$bin" "$apps" "$icons"
cp -R "$here/k4companion/." "$prefix/"
cp "$here/k4companion.png" "$icons/k4companion.png"
ln -sf "$prefix/k4companion" "$bin/k4companion"

cat > "$apps/k4companion.desktop" <<EOF
[Desktop Entry]
Type=Application
Name=K4 Companion
Comment=Remote operation of the Elecraft K4
Exec="$prefix/k4companion"
Icon=k4companion
Terminal=false
Categories=Network;HamRadio;
EOF

if [ -n "$udev_rule" ]; then
	echo 'SUBSYSTEM=="hidraw", ATTRS{idVendor}=="04d8", ATTRS{idProduct}=="f12d", TAG+="uaccess"' > "$udev_rule"
	udevadm control --reload-rules 2>/dev/null || true
fi

cat > "$prefix/uninstall" <<EOF
#!/bin/sh
# Removes K4 Companion as its installer installed it, leaving its
# settings in ~/.config/k4companion.
rm -f "$bin/k4companion" "$apps/k4companion.desktop" "$icons/k4companion.png"${udev_rule:+ "$udev_rule"}
rm -rf "$prefix"
echo "K4 Companion removed"
EOF
chmod +x "$prefix/uninstall"

# The menus see a new entry sooner with these, where they are.
update-desktop-database "$apps" 2>/dev/null || true
gtk-update-icon-cache -q "$share/icons/hicolor" 2>/dev/null || true

# PortAudio and Opus, which the program uses the system's copies of.
have_library() {
	if { ldconfig -p 2>/dev/null || /sbin/ldconfig -p 2>/dev/null; } | grep -q "$1"; then
		return 0
	fi
	for folder in /usr/lib /usr/lib64 /usr/lib/*-linux-gnu /lib /lib64 /lib/*-linux-gnu /usr/local/lib; do
		if [ -e "$folder/$1" ]; then
			return 0
		fi
	done
	return 1
}
missing=
have_library libportaudio.so.2 || missing="$missing PortAudio"
have_library libopus.so.0 || missing="$missing Opus"
if [ -n "$missing" ]; then
	echo
	echo "K4 Companion's audio needs the$missing library, which isn't installed. Install it with:"
	if command -v apt-get >/dev/null; then
		echo "  sudo apt install libportaudio2 libopus0"
	elif command -v dnf >/dev/null; then
		echo "  sudo dnf install portaudio opus"
	elif command -v pacman >/dev/null; then
		echo "  sudo pacman -S portaudio opus"
	elif command -v zypper >/dev/null; then
		echo "  sudo zypper install libportaudio2 libopus0"
	else
		echo "  your distribution's PortAudio and Opus packages"
	fi
fi

echo
echo "Installed. Start K4 Companion from the desktop's menu, or with k4companion in a terminal."
case ":$PATH:" in
*":$bin:"*) ;;
*) echo "($bin is not on your PATH, so from a terminal run $bin/k4companion.)" ;;
esac
if [ -z "$udev_rule" ]; then
	echo "To uninstall, run $prefix/uninstall"
	echo "For a K-Pod, see the K-Pod Tab section of the User Manual, or install with sudo."
else
	echo "To uninstall, run sudo $prefix/uninstall"
fi
