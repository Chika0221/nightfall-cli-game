#!/bin/bash
# Run as root INSIDE a fresh Ubuntu 24.04 WSL build distribution only.
set -euo pipefail
if [[ $(id -u) != 0 ]] || ! grep -qi microsoft /proc/sys/kernel/osrelease; then
  echo 'Run this only as root in a dedicated Ubuntu WSL build distribution.' >&2
  exit 1
fi
source /etc/os-release
[[ "$ID" == ubuntu && "$VERSION_ID" == 24.04 ]] || { echo 'Ubuntu 24.04 LTS is required.' >&2; exit 1; }
source_dir=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd -P)
# Some rootfs images omit installed manual pages; restore them before reinstalling tools.
for config in /etc/dpkg/dpkg.cfg.d/*; do
  [[ -f "$config" ]] || continue
  sed -i '\|^path-exclude[ =]*/usr/share/man/|d' "$config"
done
export DEBIAN_FRONTEND=noninteractive
apt-get update
apt-get install -y --reinstall bash coreutils findutils grep diffutils tar gzip less nano man-db manpages util-linux
apt-get install -y python3 python3-venv locales systemd systemd-sysv
locale-gen en_US.UTF-8 ja_JP.UTF-8
if ! id contractor >/dev/null 2>&1; then
  useradd --create-home --shell /bin/bash contractor
fi
passwd -l contractor
install -d -m 0700 /opt/nightfall /opt/nightfall/manager /var/lib/nightfall
install -d -m 0755 /srv/nightfall /etc/nightfall /usr/local/lib/nightfall-client
python3 -m venv --without-pip /opt/nightfall/venv
site=$(/opt/nightfall/venv/bin/python -c 'import sysconfig; print(sysconfig.get_path("purelib"))')
cp -R "$source_dir/nightfall" "$site/"
find "$site/nightfall" -type d -name __pycache__ -exec rm -rf {} +
install -m 0644 "$source_dir/nightfall/client.py" /usr/local/lib/nightfall-client/client.py
for name in mission vault; do
  printf '#!/bin/sh\nexec /usr/bin/python3 -I /usr/local/lib/nightfall-client/client.py %s "$@"\n' "$name" > "/usr/local/bin/$name"
  chmod 0755 "/usr/local/bin/$name"
done
printf '#!/bin/sh\nexec /usr/bin/python3 -I /usr/local/lib/nightfall-client/client.py recover "$@"\n' > /usr/local/bin/nightfall-recover
chmod 0755 /usr/local/bin/nightfall-recover
install -m 0755 "$source_dir/scripts/player-shell.sh" /usr/local/bin/nightfall-shell
install -m 0644 "$source_dir/scripts/bashrc" /etc/nightfall/bashrc
install -m 0644 "$source_dir/scripts/wsl.conf" /etc/wsl.conf
install -m 0644 "$source_dir/scripts/nightfall.service" /etc/systemd/system/nightfall.service
systemctl enable nightfall.service
/opt/nightfall/venv/bin/python -I -m nightfall.admin init
mandb -q
for tool in bash pwd ls cat find less grep head tail sort uniq wc diff nano chmod tar mkdir cp mv touch rm rmdir du man; do
  command -v "$tool" >/dev/null
  man -w "$tool" >/dev/null
done
dpkg-query -W > /opt/nightfall/packages.txt
apt-get clean
printf 'NIGHTFALL-WSL-1\n' > /etc/nightfall/identity
printf 'Provisioning complete. Stop this build distro and export its rootfs.\n'
