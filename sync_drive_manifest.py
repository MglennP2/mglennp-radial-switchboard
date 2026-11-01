import os, re, urllib.request
from homestead_crew_and_gitops_agent import github_autocommit_file, load_local_env

DOC_ID = '1Mikoqt-76Oxh4nrcz88KM-rC0OjrObxou1qf--SfO74'
GATE = 'MGLENNP-GREENLIGHT-V2'
LOCKED = {'switchboard_api.py', 'radial_synapse_phonebook.py'}

def main():
    load_local_env()
    req = urllib.request.Request(
        f'https://docs.google.com/document/d/{DOC_ID}/export?format=txt',
        headers={'User-Agent': 'MglennP-Bridge/2.0'}
    )
    txt = urllib.request.urlopen(req, timeout=15).read().decode('utf-8-sig', errors='replace')
    st = re.search(r'^STATUS:\s*(.+)$', txt, re.M)
    gc = re.search(r'^GATE_CODE:\s*(.+)$', txt, re.M)
    rid = re.search(r'^RELEASE_ID:\s*(.+)$', txt, re.M)
    msg = re.search(r'^COMMIT_MESSAGE:\s*(.+)$', txt, re.M)
    if not st or st.group(1).strip() != 'RELEASE_APPROVED' or not gc or gc.group(1).strip() != GATE:
        print('STANDBY: No approved release.')
        return
    for m in re.finditer(r'===BEGIN_FILE:\s*([^\r\n=]+)===\r?\n(.*?)\r?\n===END_FILE===', txt, re.S):
        p, body = m.group(1).strip().lstrip('/'), m.group(2) + '\n'
        if os.path.basename(p) in LOCKED:
            continue
        open('.tmp_stage', 'w', encoding='utf-8').write(body)
        commit_title = (msg.group(1).strip() if msg else 'Cloud Bridge Release') + ' [' + (rid.group(1).strip() if rid else 'v2') + ']'
        r = github_autocommit_file('.tmp_stage', p, commit_title)
        print(p, '->', r.get('status'), r.get('html_url') or r.get('error'))

if __name__ == '__main__':
    main()
