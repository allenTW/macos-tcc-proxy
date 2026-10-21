#!/bin/sh
# CLI examples. Assumes ./install.sh has been run (client lives in ~/.mac-proxy).
P="$HOME/.mac-proxy/mac_proxy.py"

python3 "$P" ping                                   # pong
python3 "$P" run /bin/ls -la "$HOME/Downloads"      # runs under the daemon's privacy grants
python3 "$P" applescript 'tell application "Finder" to get name of startup disk'
python3 "$P" jxa 'Application("Finder").name()'
python3 "$P" screenshot /tmp/screen.png             # needs Screen Recording approved once
python3 "$P" --timeout 120 run /usr/bin/sqlite3 /path/to/data.db .tables
echo 'tell application "Finder" to get name of startup disk' | python3 "$P" applescript -
python3 "$P" list_tabs                              # Chrome tabs; null if Chrome is not running
