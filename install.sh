#!/bin/zsh
# Install / update mac-proxy: copy to the internal disk and (re)start the launchd agent.
# The privacy grants belong to /usr/bin/osascript run by launchd, so re-running this never re-prompts.
set -e
SRC=${0:A:h}
DST=$HOME/.mac-proxy
LABEL=com.example.mac-proxy
PLIST=$HOME/Library/LaunchAgents/$LABEL.plist

mkdir -p $DST/req $DST/res $DST/tmp
chmod 700 $DST $DST/req $DST/res $DST/tmp
cp $SRC/daemon.js $SRC/chrome.js $SRC/mac_proxy.py $SRC/vol_io.py $DST/
chmod 755 $DST/mac_proxy.py

cat > $PLIST <<EOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>Label</key>
  <string>$LABEL</string>
  <key>ProgramArguments</key>
  <array>
    <string>/usr/bin/osascript</string>
    <string>-l</string>
    <string>JavaScript</string>
    <string>$DST/daemon.js</string>
  </array>
  <key>RunAtLoad</key>
  <true/>
  <key>KeepAlive</key>
  <true/>
  <key>ThrottleInterval</key>
  <integer>2</integer>
  <key>ProcessType</key>
  <string>Background</string>
  <key>StandardOutPath</key>
  <string>$HOME/Library/Logs/mac-proxy.log</string>
  <key>StandardErrorPath</key>
  <string>$HOME/Library/Logs/mac-proxy.log</string>
</dict>
</plist>
EOF

uid=$(id -u)
if launchctl print gui/$uid/$LABEL >/dev/null 2>&1; then
  launchctl kickstart -k gui/$uid/$LABEL
else
  launchctl bootstrap gui/$uid $PLIST
fi
echo "mac-proxy installed: $DST"
