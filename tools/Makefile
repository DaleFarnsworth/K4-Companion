SHELL = /bin/sh

.PHONY: default linux windows darwin clean clobber install

VERSION = $(shell sed -n '/version =/{s/^[^"]*"//;s/".*//p;q}' <example_config_files/k4companion.yaml)

default: linux

linux: clean

windows: clean k4companion-$(VERSION)-installer.exe

k4companion-$(VERSION)-installer.exe: Windows/k4companion.exe tools/k4companion.nsi Contributions/opus.dll
	makensis -DVERSION=$(VERSION) tools/k4companion.nsi

macOS: clean darwin

darwin: FORCE

FORCE:

update_version: FORCE
	tools/update_version

clean:

clobber: clean
	rm -rf k4companion-*
