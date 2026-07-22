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
    'https://api.uouin.com/cloudflare.html': 'Uouin',
    'https://ip.164746.xyz': 'ZXW',
    'https://ipdb.api.030101.xyz/?type=bestcf': 'IPDB',
    'https://ipdb.api.030101.xyz/?type=bestcfv6': 'IPDBv6',
    'https://cf.090227.xyz/CloudFlareYes': 'CFYes',
    'https://ip.haogege.xyz': 'HaoGG',
    'https://vps789.com/openApi/cfIpApi': 'VPS',
    'https://www.wetest.vip/page/cloudflare/address_v4.html': 'WeTest',
    'https://www.wetest.vip/page/cloudflare/address_v6.html': 'WeTestV6',
    'https://addressesapi.090227.xyz/ct': 'CMLiuss',
    'https://addressesapi.090227.xyz/cmcc-ipv6': 'CMLiussv6',
    'https://raw.githubusercontent.com/xingpingcn/enhanced-FaaS-in-China/refs/heads/main/Cf.json': 'FaaS',
}

PORT: str = '443'
HEADERS: dict[str, str] = {'User-Agent': 'Mozilla/5.0'}
IPV4_PATTERN: str = r'\b(?:[0-9]{1,3}\.){3}[0-9]{1,3}\b'
LOCATION_URL: str = 'https://ipinfo.io/{ip}/country'
OUTPUT_FILE: Path = Path('ipv4.txt')
MAX_RETRIES: int = 3
RETRY_DELAY: float = 2.0


def _session() -> requests.Session:
    """Create a session with connection reuse and retry strategy."""
    session = requests.Session()
    session.headers.update(HEADERS)
    adapter = HTTPAdapter(
        max_retries=Retry(
            total=MAX_RETRIES,
            backoff_factor=RETRY_DELAY,
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
            if ip.version == 4:
                ips.add(str(ip))
        except ValueError:
            continue
    return ips


def query_location(session: requests.Session, ip: str) -> str:
    """Query country code for an IP via ipinfo.io, return 'XX' on failure."""
    try:
        resp = session.get(LOCATION_URL.format(ip=ip), timeout=10)
        return resp.text.strip()
    except requests.RequestException:
        return 'XX'


def beijing_timestamp() -> str:
    """Return current Beijing time as YYYYMMDD_HH:MM string."""
    return (datetime.now(timezone.utc) + timedelta(hours=8)).strftime('%Y%m%d_%H:%M')


def collect_ips(session: requests.Session) -> set[str]:
    """Collect IPv4 addresses from all sources."""
    all_ips: set[str] = set()
    for url, name in SOURCES.items():
        try:
            text = fetch(session, url)
            ips = extract_ipv4(text)
            all_ips.update(ips)
            print(f'  [{name}] {len(ips)} 个IPv4')
        except requests.RequestException as e:
            print(f'  [{name}] 请求失败: {e}')
    return all_ips


def enrich_locations(session: requests.Session, ips: set[str]) -> dict[str, str]:
    """Query geographic locations for all IPs concurrently."""
    entries: dict[str, str] = {}
    with ThreadPoolExecutor(max_workers=15) as pool:
        fut_map = {pool.submit(query_location, session, ip): ip for ip in ips}
        for future in as_completed(fut_map):
            ip = fut_map[future]
            entries[f'{ip}:{PORT}'] = future.result()
    return entries


def main() -> int:
    """Collect CF优选IPv4, query locations, and write result file."""
    print('采集 CF 优选 IPv4...\n')

    session = _session()

    all_ips = collect_ips(session)
    if not all_ips:
        print('未采集到任何IP，跳过')
        return 1
    print(f'\n去重后共 {len(all_ips)} 个IPv4')

    print('查询地理位置...')
    entries = enrich_locations(session, all_ips)

    tmp = OUTPUT_FILE.with_suffix('.tmp')
    timestamp = beijing_timestamp()
    with tmp.open('w') as f:
        f.write(f'ipv4.list.updated.at#Upd{timestamp}\n')
        for ip_port, location in entries.items():
            f.write(f'{ip_port}#{location}\n')
    tmp.replace(OUTPUT_FILE)
    print(f'\n共 {len(entries)} 个IP写入 {OUTPUT_FILE}')
    return 0


if __name__ == '__main__':
    sys.exit(main())
