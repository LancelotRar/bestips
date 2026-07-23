import ipaddress
import re
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timedelta, timezone
from pathlib import Path

import requests
from requests.adapters import HTTPAdapter
from urllib3.util import Retry


SOURCES: dict[str, str] = {
    'https://www.wetest.vip/page/cloudfront/address_v4.html': 'WeTest',
    'https://api.uouin.com/cloudflare.html': 'UOUIN',
    'https://bestcf.pages.dev/xinyitang3/ipv4.txt': 'Mia',
    'https://stock.hostmonit.com/CloudFlareYes': 'CFYES',
    'https://bestcf.pages.dev/tiancheng/all.txt': 'Tiancheng',
    'https://raw.githubusercontent.com/gslege/CloudflareIP/refs/heads/main/SG.txt': 'Gslege-SG', 
    'https://raw.githubusercontent.com/gslege/CloudflareIP/refs/heads/main/DE.txt': 'Gslege-DE',
    'https://raw.githubusercontent.com/gslege/CloudflareIP/refs/heads/main/US.txt': 'Gslege-US',                 
    'https://raw.githubusercontent.com/ymyuuu/IPDB/refs/heads/main/BestCF/bestcfv4.txt': 'IPDB',
    'https://vps789.com/openApi/cfIpApi': 'VPS789',
    'https://api.4ce.cn/api/bestCFIP': 'vvhan',
}

PORT: str = '443'
HEADERS: dict[str, str] = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/143.0.0.0 Safari/537.36 Edg/143.0.0.0'}
IPV4_PATTERN: str = r'\b(?:[0-9]{1,3}\.){3}[0-9]{1,3}\b'
LOCATION_URL: str = 'https://ipinfo.io/{ip}/country'
OUTPUT_FILE: Path = Path('best-cf-ipv4.txt')
MAX_RETRIES: int = 3
RETRY_BACKOFF_FACTOR: float = 2.0


def _session() -> requests.Session:
    """Create a session with connection reuse and retry strategy."""
    session = requests.Session()
    session.headers.update(HEADERS)
    adapter = HTTPAdapter(
        max_retries=Retry(
            total=MAX_RETRIES,
            backoff_factor=RETRY_BACKOFF_FACTOR,
            allowed_methods={'GET'},
            status_forcelist={429, 500, 502, 503, 504},
        )
    )
    session.mount('http://', adapter)
    session.mount('https://', adapter)
    return session


def fetch(session: requests.Session, url: str, timeout: int = 15) -> str:
    """Fetch a URL with retry support and return response text."""
    resp = session.get(url, timeout=timeout)
    resp.raise_for_status()
    return resp.text


def extract_ipv4(text: str) -> set[str]:
    """Extract valid IPv4 addresses from raw text."""
    ips: set[str] = set()
    for match in re.finditer(IPV4_PATTERN, text):
        try:
            ip = ipaddress.ip_address(match.group())
            ips.add(str(ip))
        except ValueError:
            continue
    return ips


def query_location(session: requests.Session, ip: str) -> str:
    """Query country code for an IP via ipinfo.io, return 'XX' on failure."""
    try:
        resp = session.get(LOCATION_URL.format(ip=ip), timeout=10)
        resp.raise_for_status()
        return resp.text.strip()
    except requests.RequestException:
        return 'XX'


def beijing_timestamp() -> str:
    """Return current Beijing time as YYYY-MM-DD HH:MM string."""
    return (datetime.now(timezone.utc) + timedelta(hours=8)).strftime('%Y-%m-%d %H:%M')


def collect_ips(session: requests.Session) -> set[str]:
    """Collect IPv4 addresses from all sources."""
    all_ips: set[str] = set()
    for url, name in SOURCES.items():
        try:
            text = fetch(session, url)
            ips = extract_ipv4(text)
            all_ips.update(ips)
            print(f'  [{name}] {len(ips)} IPv4')
        except requests.RequestException as e:
            print(f'  [{name}] failed: {e}')
    return all_ips


def _fetch_location(ip: str) -> tuple[str, str]:
    """Query location for a single IP with its own session."""
    sess = _session()
    try:
        return ip, query_location(sess, ip)
    finally:
        sess.close()


def enrich_locations(ips: set[str]) -> dict[str, str]:
    """Query geographic locations for all IPs concurrently."""
    entries: dict[str, str] = {}
    with ThreadPoolExecutor(max_workers=15) as pool:
        fut_map = {pool.submit(_fetch_location, ip): ip for ip in ips}
        for future in as_completed(fut_map):
            ip, location = future.result()
            entries[f'{ip}:{PORT}'] = location
    return entries


def main() -> int:
    """Collect Cloudflare IPs, query locations, and write result file."""
    print('Collecting Cloudflare IPs...\n')

    session = _session()

    all_ips = collect_ips(session)
    if not all_ips:
        print('No IPs collected, skip')
        return 1
    print(f'\n{len(all_ips)} unique IPv4')

    print('Querying locations...')
    entries = enrich_locations(all_ips)

    tmp = OUTPUT_FILE.with_suffix('.tmp')
    timestamp = beijing_timestamp()
    with tmp.open('w') as f:
        f.write(f'bestips updated at#{timestamp}\n')
        for ip_port, location in entries.items():
            f.write(f'{ip_port}#{location}\n')
    tmp.replace(OUTPUT_FILE)
    print(f'\n{len(entries)} IPs written to {OUTPUT_FILE}')
    return 0


if __name__ == '__main__':
    sys.exit(main())
