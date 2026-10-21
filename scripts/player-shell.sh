#!/bin/bash
set -u
export LC_ALL=C.UTF-8 LANG=C.UTF-8
client=/usr/local/lib/nightfall-client/client.py
for attempt in {1..20}; do
  [[ -S /run/nightfall/control.sock ]] && break
  sleep 0.25
done
/usr/bin/python3 -I "$client" session-start || exit 1
finish() { /usr/bin/python3 -I "$client" session-stop >/dev/null 2>&1 || true; }
trap finish EXIT
trap 'exit 130' INT
trap 'exit 129' HUP TERM
printf '\nNIGHTFALL MAINTENANCE TERMINAL\nHost: maintenance-03\nUser: contractor\n\n'
printf 'less/man は q、nano は Ctrl+O → Enterで保存、Ctrl+Xで終了。\n困ったら mission help。終了は exit。進捗は保存されます。\n\n'
mission
cd /home/contractor || exit 1
/bin/bash --noprofile --rcfile /etc/nightfall/bashrc -i
