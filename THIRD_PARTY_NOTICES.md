# Third-party components

IdeaSearch's own code is MIT licensed. Bundled dependencies retain their own terms.

- Python 3.14: Python Software Foundation License; https://www.python.org/downloads/source/
- Node.js 24: MIT and bundled third-party notices; see assets/licenses/Node-LICENSE.txt and https://github.com/nodejs/node
- PySide6 / Shiboken6 / Qt 6.12: LGPLv3/GPLv3 or commercial licensing. This application uses Qt Core, Gui, Widgets, Network and SVG through replaceable DLLs. Library modification and reverse engineering for debugging such modifications are not prohibited by this application's MIT license. Corresponding upstream source: https://download.qt.io/official_releases/QtForPython/ and https://download.qt.io/official_releases/qt/6.12/ . See https://doc.qt.io/qtforpython-6/licenses.html and the license texts under assets/licenses.
- PyInstaller: GPL with bootloader exception; https://pyinstaller.org/en/stable/license.html . Packaging does not change the application's MIT license.

Binary redistributors must preserve dependency notices and applicable source availability obligations. This file is not a relicense of third-party software. Users may rebuild the application against their modified compatible libraries using build.ps1 and requirements-build.txt.
