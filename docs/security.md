# Security

## What the proxy is

A local command executor. Anything placed in `~/.mac-proxy/req/` as a valid request is run as your user, with the privacy grants held by `/usr/bin/osascript`.

## What the code does and does not enforce

- No allowlist: `run` accepts any `argv`; `applescript` and `jxa` accept any script; `screenshot` writes to any absolute path.
- No authentication or signing of requests. The only barrier is directory permission: `install.sh` sets `~/.mac-proxy`, `req/`, `res/`, `tmp/` to mode 700.
- Timeouts are enforced (default 60 s, max 600 s).
- Chrome `set_url` / `open_url` accept only `http:`, `https:`, `about:blank` and the new-tab page (`chrome.js`).
- Responses (stdout/stderr of your commands) are written to `res/` and removed by the client after reading, or by the daemon after 300 s.

## Risks

1. Any process running as you that can write to `req/` can use the permissions you granted (Screen Recording, Automation, drive access). Malware running as you could do the same, but it could already run commands as you; the new element is access to the extra TCC grants.
2. Loosening the directory mode (for example to share between users) would let other accounts run commands as you. Do not.
3. Screenshots and command output may contain sensitive data; they pass through files in `res/` briefly.
4. Prompt-injection risk: if an AI agent builds requests from untrusted text, the proxy will execute them faithfully.

## Recommendations

- Keep mode 700 on `~/.mac-proxy`; check after restoring from backup or syncing.
- Do not expose the directory over file sharing or sync services.
- Grant only the permissions you need; revoke in System Settings > Privacy & Security if you stop using the proxy.
- If you build on top, add an allowlist in your own wrapper before calling `call()`, and log requests.
- Uninstall: `launchctl bootout gui/$(id -u)/com.example.mac-proxy`, then delete the plist in `~/Library/LaunchAgents` and `~/.mac-proxy`.

## Reporting

Open an issue on the GitHub repository; for sensitive reports use a private security advisory.
