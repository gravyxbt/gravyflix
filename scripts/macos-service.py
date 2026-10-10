#!/usr/bin/env python3
"""Manage Gravyflix's optional per-user macOS login service; no sudo needed."""
import argparse
import os
import platform
import plistlib
import shutil
import subprocess
import sys
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
LABEL='org.gravyflix.server'


def launch_agent(root,home):
    root=Path(root).resolve();home=Path(home)
    logs=home/'Library/Logs/Gravyflix'
    return {
        'Label':LABEL,
        'ProgramArguments':[str(root/'.venv/bin/python'),'-m','app'],
        'WorkingDirectory':str(root),
        'EnvironmentVariables':{
            'PYTHONPATH':str(root/'backend'),
            'PATH':':'.join([str(root/'.venv/bin'),'/opt/homebrew/bin','/usr/local/bin','/usr/bin','/bin','/usr/sbin','/sbin']),
            'PYTHONUNBUFFERED':'1',
        },
        'RunAtLoad':True,'KeepAlive':{'SuccessfulExit':False},'ThrottleInterval':10,
        'StandardOutPath':str(logs/'server.log'),'StandardErrorPath':str(logs/'server-error.log'),
    }


def check_host():
    if sys.platform!='darwin' or platform.machine()!='arm64':
        raise SystemExit('This helper supports native Apple Silicon macOS only.')
    if int(platform.mac_ver()[0].split('.')[0])<14:
        raise SystemExit('macOS 14 or newer is required.')


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action',choices=['install','start','stop','restart','status','uninstall','print'])
    args=parser.parse_args()
    check_host()
    config=launch_agent(ROOT,Path.home())
    if args.action=='print':
        sys.stdout.buffer.write(plistlib.dumps(config));return
    launchctl=shutil.which('launchctl')
    if not launchctl:raise SystemExit('launchctl was not found.')
    target=f'gui/{os.getuid()}/{LABEL}';domain=f'gui/{os.getuid()}'
    path=Path.home()/'Library/LaunchAgents'/f'{LABEL}.plist'
    def loaded():
        return subprocess.run([launchctl,'print',target],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL).returncode==0
    def invoke(*arguments):subprocess.run([launchctl,*arguments],check=True)
    if args.action=='status':
        if loaded():invoke('print',target)
        else:print('Gravyflix login service is not running.')
        return
    if path.exists():
        existing=plistlib.loads(path.read_bytes())
        if existing.get('Label')!=LABEL or existing.get('WorkingDirectory')!=str(ROOT):
            raise SystemExit('This service file belongs to another installation; it was not changed.')
    if args.action=='install':
        python=ROOT/'.venv/bin/python'
        if not python.is_file() or not (ROOT/'.env').is_file():
            raise SystemExit('Run ./scripts/setup-macos.sh and configure .env first.')
        # A Rosetta virtual environment could otherwise fail much later in OCR startup.
        result=subprocess.run([str(python),'-c','import platform; print(platform.machine())'],capture_output=True,text=True,check=True)
        if result.stdout.strip()!='arm64':raise SystemExit('The project virtual environment must use native ARM Python.')
        path.parent.mkdir(parents=True,exist_ok=True)
        (Path.home()/'Library/Logs/Gravyflix').mkdir(parents=True,exist_ok=True)
        if loaded():invoke('bootout',target)
        temporary=path.with_suffix('.tmp')
        temporary.write_bytes(plistlib.dumps(config));temporary.chmod(0o600);temporary.replace(path)
        invoke('enable',target);invoke('bootstrap',domain,str(path))
        print('Installed login service. Logs: ~/Library/Logs/Gravyflix/')
    elif args.action=='uninstall':
        if loaded():invoke('bootout',target)
        if path.exists():path.unlink()
        print('Removed only the Gravyflix login service. Media and configuration retained.')
    elif args.action=='stop':
        if loaded():invoke('bootout',target)
        print('Stopped Gravyflix for this login session. Use start to resume; uninstall to remove login startup.')
    elif args.action in {'start','restart'}:
        if not path.exists():raise SystemExit('Install the login service first, or use ./scripts/start.sh for foreground mode.')
        invoke('enable',target)
        if loaded():
            if args.action=='restart':invoke('kickstart','-k',target)
        else:invoke('bootstrap',domain,str(path))
        print('Gravyflix login service started.')

if __name__=='__main__':
    try:main()
    except subprocess.CalledProcessError as error:
        raise SystemExit(f'launchctl failed ({error.returncode}). Run from your logged-in Mac Terminal; check ~/Library/Logs/Gravyflix/.') from None
