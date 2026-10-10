#!/usr/bin/env python3
"""Audit publishable files without logging secret values; optionally compare a private .env."""
import argparse
import fnmatch
import json
import re
import shutil
import struct
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SOURCE_DIRS = {'backend','roku','scripts','services','tests','docs','config','.github','media','data'}
ROOT_FILES = {'README.md','LICENSE','LICENSE-STATUS.md','THIRD_PARTY_NOTICES.md','SECURITY.md',
              'CONTRIBUTING.md','Makefile','package.json','package-lock.json','bsconfig.json','.gitignore','.env.example'}
IGNORED_PARTS = {'.git','.venv','venv','node_modules','__pycache__','.pytest_cache','.github-cache'}
PATTERNS = {
    'personal home path': re.compile(r'/home/(?!example(?:/|\b)|user(?:/|\b))[A-Za-z0-9_.-]+/'),
    'personal Mac home path': re.compile(r'/Users/(?!example(?:/|\b)|user(?:/|\b))[A-Za-z0-9_.-]+/'),
    'private LAN address': re.compile(r'\b(?:192\.168\.\d{1,3}\.\d{1,3}|10\.(?:\d{1,3}\.){2}\d{1,3}|172\.(?:1[6-9]|2\d|3[01])\.\d{1,3}\.\d{1,3})\b'),
    'network adapter identifier': re.compile(r'\bwlx[0-9a-f]{12}\b',re.I),
    'private key material': re.compile(r'-----BEGIN (?:RSA |EC |OPENSSH |DSA )?PRIVATE KEY-----'),
    'provider credential': re.compile(r'\b(?:AKIA[0-9A-Z]{16}|gh[pousr]_[a-zA-Z0-9]{30,}|github_pat_[a-zA-Z0-9_]{40,}|sk-[a-zA-Z0-9_-]{32,})\b'),
    'credential in URL': re.compile(r'https?://[^\s/"\']+:[^\s/@"\']+@'),
    'possible signed token': re.compile(r'\beyJ[A-Za-z0-9_-]{16,}\.[A-Za-z0-9_-]{16,}\.[A-Za-z0-9_-]{16,}\b'),
}
ASSIGNMENT=re.compile(r'''(?ix)\b(?:api[_-]?key|devpassword|password|access[_-]?token|client[_-]?secret)\b\s*[=:]\s*["']([^"'\r\n]+)["']''')
TEST_DUMMIES={'fake','test','key','api-key','test-key','hidden-secret','a-secret-key','secret','password','dummy','test-password'}

def source_paths(root=ROOT):
    # Deliberate allowlist: installed dependencies, runtime data and archives never enter a release.
    for top in sorted(ROOT_FILES):
        path=root/top
        if path.is_file():yield Path(top)
    for directory in sorted(SOURCE_DIRS):
        if not (root/directory).exists():continue
        for path in sorted((root/directory).rglob('*')):
            rel=path.relative_to(root)
            if not path.is_file() or any(part in IGNORED_PARTS for part in rel.parts):continue
            if directory in {'data','media'} and path.name!='.gitkeep':continue
            if directory=='config' and not path.name.endswith('.example.json'):continue
            yield rel

def forbidden(relative):
    parts=relative.parts;name=relative.name
    if name.startswith('.env') and name!='.env.example':return True
    if any(part in IGNORED_PARTS- {'.git'} for part in parts):return True
    if parts[0] in {'data','media'} and name!='.gitkeep':return True
    if parts[0]=='dist':return True
    if parts[0]=='config' and not name.endswith('.example.json'):return True
    return any(fnmatch.fnmatch(name,p) for p in ['*.sqlite*','*.db','*.db-*','*.log','*.zip','*.tar*','*.pem','*.key','*.p12','*.pfx','.netrc','.npmrc','*.pyc'])

def audit(root,paths,known=()):
    problems=[]
    for relative in paths:
        path=root/relative
        if path.is_symlink():problems.append((str(relative),0,'symlink is not publishable'));continue
        if forbidden(relative):problems.append((str(relative),0,'private/runtime file is selected for publication'));continue
        if not path.is_file():problems.append((str(relative),0,'selected file missing'));continue
        data=path.read_bytes()
        if any(secret and secret in data for secret in known):problems.append((str(relative),0,'matches a private credential value'))
        if path.suffix=='.png':
            offset=8
            while offset+12<=len(data):
                size=struct.unpack('>I',data[offset:offset+4])[0];kind=data[offset+4:offset+8]
                if kind in {b'tEXt',b'zTXt',b'iTXt',b'eXIf',b'tIME'}:problems.append((str(relative),0,'PNG metadata needs review'))
                offset+=size+12
            continue
        if path.suffix=='.ttf':continue # Original third-party font/license, not personal artwork.
        try:text=data.decode('utf-8')
        except UnicodeDecodeError:problems.append((str(relative),0,'unexpected binary file'));continue
        for number,line in enumerate(text.splitlines(),1):
            for label,pattern in PATTERNS.items():
                if pattern.search(line):
                    expected_negative=(label=='credential in URL' and str(relative)=='backend/tests/test_management.py' and ('http://' + 'user:secret' + '@host/') in line)
                    if not expected_negative:problems.append((str(relative),number,label))
            for match in ASSIGNMENT.finditer(line):
                value=match.group(1)
                placeholder=any(marker in value for marker in ['YOUR_','example','getenv','os.environ','request.','body.','values[','{','m.top','config.'])
                dummy=(relative.parts[0] in {'tests'} or 'tests' in relative.parts) and value in TEST_DUMMIES
                if len(value)>=8 and not placeholder and not dummy:problems.append((str(relative),number,'literal credential assignment needs review'))
            if relative.name=='.env.example' and re.match(r'\s*(?:\w*(?:KEY|PASSWORD|SECRET|TOKEN)\w*)\s*=\s*[^\s#]',line):
                problems.append((str(relative),number,'credential example must be blank'))
    return sorted(set(problems))

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--tracked',action='store_true',help='Audit every tracked path, including accidentally tracked ignored files; requires Git.')
    parser.add_argument('--private-env',type=Path,help='Compare exact sensitive values from an uncommitted private .env. Values are never printed.')
    parser.add_argument('--json-report',type=Path,help='Write a redacted report outside the source tree.')
    args=parser.parse_args()
    if args.tracked:
        if not shutil.which('git'):parser.error('--tracked requires Git')
        result=subprocess.run(['git','ls-files','-z'],cwd=ROOT,check=True,capture_output=True)
        paths=[Path(p) for p in result.stdout.decode().split('\0') if p]
    else:paths=list(source_paths())
    known=[]
    if args.private_env:
        from dotenv import dotenv_values
        values=dotenv_values(args.private_env,interpolate=False)
        known=[v.encode() for k,v in values.items() if v and len(v)>=4 and re.search(r'KEY|PASSWORD|SECRET|TOKEN',k,re.I)]
    problems=audit(ROOT,paths,known)
    report={'result':'fail' if problems else 'pass','files_checked':len(paths),'exact_private_values_checked':len(known),
            'findings':[{'file':p,'line':n,'reason':label} for p,n,label in problems],
            'limits':'Checks selected current source files and known private values; not a guarantee against unknown secrets, historical Git blobs, or later edits.'}
    if args.json_report:args.json_report.write_text(json.dumps(report,indent=2)+'\n')
    for path,number,label in problems:print(f'{path}:{number}: {label}')
    print(f"Publication audit: {report['result'].upper()} ({len(paths)} files; {len(problems)} findings). Secret values are never printed.")
    raise SystemExit(bool(problems))

if __name__=='__main__':main()
