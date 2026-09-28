## Program to remotely control an Elecraft K4 transceiver

K4 Companion is an application written in python3 that remotely
controls one or more Elecraft K4 transceivers via TCP/IP.  It controls
the main K4 features, including remote audio, and shows a panadapter
and waterfall for each receiver. It also has a few enhancements, like
per-mode equalizer settings and configurable CW and general macros.

K4 Companion can also key the K4 from paddles or a straight key
connected to the computer, through a MoMIDI interface, a serial port,
or a Vail adapter. Its built-in keyer offers plain Iambic, Iambic A,
Iambic B and Ultimatic modes, and it plays its own sidetone, so you hear your
sending without waiting for the audio to come back from the K4.

Connections to the K4 are encrypted (TLS on port 9204) by default.

K4 Companion began life as a simple macro-sending program called
K4Macro-Python, created by Charles Powell, NK8O. It has now grown
into a full-fledged remote control program for the K4.

K4 Companion is a standalone python3 program downloadable
[here](https://github.com/DaleFarnsworth/K4-Companion/blob/main/k4companion).
Information on installing dependencies is found in the
[User Manual](https://github.com/DaleFarnsworth/K4-Companion/blob/main/Documentation/K4%20Companion%20User%20Manual.pdf).
An optional k4companion.yaml configuration file may be passed to
K4 Companion to customize much of its behavior, but the
configuration language is somewhat daunting.

To simplify installation on Windows and to avoid managing dependencies, a
[full Windows install](https://github.com/DaleFarnsworth/K4-Companion/blob/main/Windows/k4companion-installer.exe) is recommended.
Alongside k4companion.exe it installs k4companion-debug.exe, the same
program with a console, for debugging.

The
[Windows Quick Start Guide](https://github.com/DaleFarnsworth/K4-Companion/blob/main/Documentation/K4%20Companion%20Windows%20Quick%20Start.pdf)
should ease the initial installation on Windows.

Some work has been done on porting K4-Companion to MacOS, but its installation
is not yet sufficiently straight-forward enough to recommend.

Code found in the _main_ branch is considered ready for wide use.
Code in any other branches, including _dev_ is pre-release. These
branches will be rebased at inconvenient times. You have been warned!

Please send problem reports either: by sending an email, by entering
an issue on github, or by making a pull request. Problem reports and
suggestions are greatly appreciated.

Dale Farnsworth, W7DA
dale@farnsworth.org

![Screenshot](images/screenshot.png)
