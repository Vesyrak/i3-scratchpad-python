# i3 Scratchpad
## Introduction

This script allows you to hide application windows on the i3-scratchpad, showing them with the simple press of a keystroke!
This work is heavily based on the work provided by https://gitlab.com/aquator/i3-scratchpad, and uses almost the same API.

Key changes:
* A rewrite in Python was warranted to increase readability and reduce complexity, which in turn increases maintainability.
* Supports multiple monitors
* does not support short codes for positions yet (e.g. top instead of t)

Do note that this script launches the program on first keystroke, so you don't manually bind programs to a keybind at runtime.
Subsequent keystrokes show/hide the application from the scratchpad. This also means that these applications are always running.

## Building & Installing yourself
Pipenv was used for env management, and will thus be utilised in the following example.
A requirements.txt can be generated for those interested, by using the following command:
`pipenv lock  --requirements --clear > requirements.txt`

Following commands are used for actual building:
```
pipenv install
pyinstaller --paths <path-to-venv>/lib/python<python_version>/site-packages --onefile scratchpad.py
cp dist/scratchpad /usr/local/bin/i3-scratchpad-python
```

## Usage
API is basically the same as https://gitlab.com/aquator/i3-scratchpad.
Below some examples, just add these lines to the bottom of your i3 config:
```
bindsym Mod4+shift+o exec i3-scratchpad-python -a center-right -d 40%x80% -m right -t spotify
bindsym Mod4+shift+u exec i3-scratchpad-python -a center-left -d 40%x80% -m left -t telegram-desktop
bindsym Mod4+shift+m exec i3-scratchpad-python -a top-center -d 90%x50% -m top -t konsole
bindsym Mod4+shift+f exec i3-scratchpad-python -a bottom-center -d 90%x50% -m bottom -t dolphin
```
b