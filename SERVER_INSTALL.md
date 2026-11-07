# Server install (Debian/Ubuntu)

The deployment bundle intentionally has no Telegram token. Rotate the token previously pasted in chat, then add the new token on the server in `/opt/task-reminder-bot/config.py`.

Upload the contents of this folder to a private directory on the server, preserving `tasks.json`, then run as root:

```sh
bash install_server.sh
nano /opt/task-reminder-bot/config.py
systemctl enable --now task-reminder-bot
systemctl status task-reminder-bot --no-pager
```

Logs: `journalctl -u task-reminder-bot -f`

The installer supports Debian/Ubuntu with apt, creates a restricted `taskbot` service user, a Python virtual environment, and a systemd service. It copies the provided `tasks.json` if the server does not already have one.
