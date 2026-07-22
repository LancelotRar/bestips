import os, re, ipaddress
from datetime import datetime, timedelta, timezone
from concurrent.futures import ThreadPoolExecutor, as_completed
import requests


SOURCES = {
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

PORT = '443'
HEADERS = {'User-Agent': 'Mozilla/5.0'}
IPV4_PATTERN = r'\b(?:[0-9]{1,3}\.){3}[0-9]{1,3}\b'
LOCATION_URL = 'https://ipinfo.io/{ip}/country'
OUTPUT_FILE = 'ipv4.txt'


def fetch(url):
    resp = requests.get(url, headers=HEADERS, timeout=15)
    resp.raise_for_status()
    return resp.text


def extract_ipv4(text):
    ips = set()
    for match in re.findall(IPV4_PATTERN, text):
        try:
            ip = ipaddress.ip_address(match)
            if ip.version == 4:
                ips.add(str(ip))
        except ValueError:
            continue
    return ips


def query_location(ip):
    try:
        resp = requests.get(LOCATION_URL.format(ip=ip), headers=HEADERS, timeout=10)
        return resp.text.strip()
    except requests.RequestException:
        return 'XX'


def beijing_timestamp():
    return (datetime.now(timezone.utc) + timedelta(hours=8)).strftime('%Y%m%d_%H:%M')


def collect_ips():
    all_ips = set()
    for url, name in SOURCES.items():
        try:
            text = fetch(url)
            ips = extract_ipv4(text)
            all_ips.update(ips)
            print(f'  [{name}] {len(ips)} 个IPv4')
        except Exception as e:
            print(f'  [{name}] 失败: {e}')
    return all_ips


def enrich_locations(ips):
    entries = {}
    with ThreadPoolExecutor(max_workers=15) as pool:
        fut_map = {pool.submit(query_location, ip): ip for ip in sorted(ips)}
        for future in as_completed(fut_map):
            ip = fut_map[future]
            entries[f'{ip}:{PORT}'] = future.result()
    return entries


def write_output(entries):
    timestamp = beijing_timestamp()
    with open(OUTPUT_FILE, 'w') as f:
        f.write(f'ipv4.list.updated.at#Upd{timestamp}\n')
        for ip_port, location in entries.items():
            f.write(f'{ip_port}#{location}\n')
    print(f'\n共 {len(entries)} 个IP写入 {OUTPUT_FILE}')


def main():
    print('采集 CF 优选 IPv4...\n')

    if os.path.exists(OUTPUT_FILE):
        os.remove(OUTPUT_FILE)

    all_ips = collect_ips()
    print(f'\n去重后共 {len(all_ips)} 个IPv4')

    print('查询地理位置...')
    entries = enrich_locations(all_ips)

    write_output(entries)


if __name__ == '__main__':
    main()
