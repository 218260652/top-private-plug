#!/usr/bin/env bash
# Run explicitly on YOUR dedicated Linux gateway; changes forwarding and firewall.
set -euo pipefail
if [ "$(id -u)" != 0 ]; then echo 'Run as root on the VPN server.' >&2; exit 1; fi
command -v iptables >/dev/null
command -v ip >/dev/null
uplink="${TPP_UPLINK:-$(ip -4 route show default | awk 'NR==1 {print $5}')}"
if [[ ! "$uplink" =~ ^[a-zA-Z0-9_.:-]+$ ]]; then echo 'Set TPP_UPLINK to your public interface.' >&2; exit 1; fi
if [ ! -c /dev/net/tun ]; then echo '/dev/net/tun is unavailable. Use a TUN-capable VPS.' >&2; exit 1; fi
sysctl -w net.ipv4.ip_forward=1
printf 'net.ipv4.ip_forward=1\n' > /etc/sysctl.d/80-top-private-plug.conf
iptables -N TPP_FWD 2>/dev/null || true
iptables -F TPP_FWD
for network in 0.0.0.0/8 10.0.0.0/8 100.64.0.0/10 127.0.0.0/8 169.254.0.0/16 172.16.0.0/12 192.0.0.0/24 192.0.2.0/24 192.168.0.0/16 198.18.0.0/15 198.51.100.0/24 203.0.113.0/24 224.0.0.0/4 240.0.0.0/4; do
  iptables -A TPP_FWD -d "$network" -j REJECT
done
iptables -A TPP_FWD -o "$uplink" -j ACCEPT
iptables -A TPP_FWD -j DROP
rule() { local table="$1"; shift; iptables -t "$table" -C "$@" 2>/dev/null || iptables -t "$table" -I "$@"; }
rule filter INPUT -i tpp+ -j DROP
rule filter FORWARD -o tpp+ -j DROP
rule filter FORWARD -o tpp+ -d 10.77.0.0/16 -m conntrack --ctstate ESTABLISHED,RELATED -j ACCEPT
rule filter FORWARD -i tpp+ -s 10.77.0.0/16 -j TPP_FWD
rule nat POSTROUTING -s 10.77.0.0/16 -o "$uplink" -j MASQUERADE
printf 'Top private Plug forwarding configured through %s. Persist added rules using your firewall service, or rerun after reboot.\n' "$uplink"
