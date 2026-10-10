import importlib.util
import plistlib
import sys
from pathlib import Path

ROOT=Path(__file__).resolve().parents[2]
spec=importlib.util.spec_from_file_location('macos_service',ROOT/'scripts/macos-service.py')
service=importlib.util.module_from_spec(spec);spec.loader.exec_module(service)


def test_launch_agent_handles_spaces_and_uses_native_brew_paths(tmp_path):
    root=tmp_path/'My Media Server';home=tmp_path/'Example User'
    config=service.launch_agent(root,home)
    assert plistlib.loads(plistlib.dumps(config))==config
    assert config['ProgramArguments']==[str(root.resolve()/'.venv/bin/python'),'-m','app']
    assert config['WorkingDirectory']==str(root.resolve())
    assert '/opt/homebrew/bin' in config['EnvironmentVariables']['PATH'].split(':')
    assert config['RunAtLoad'] is True
    assert config['KeepAlive']=={'SuccessfulExit':False}
    assert str(home/'Library/Logs/Gravyflix') in config['StandardOutPath']
    assert set(config['EnvironmentVariables'])=={'PYTHONPATH','PATH','PYTHONUNBUFFERED'}


def test_macos_helper_rejects_other_hosts(monkeypatch):
    import pytest
    monkeypatch.setattr(service.sys,'platform','linux')
    with pytest.raises(SystemExit,match='Apple Silicon'):service.check_host()


def test_macos_helper_rejects_rosetta(monkeypatch):
    import pytest
    monkeypatch.setattr(service.sys,'platform','darwin')
    monkeypatch.setattr(service.platform,'machine',lambda:'x86_64')
    with pytest.raises(SystemExit,match='Apple Silicon'):service.check_host()


def test_macos_helper_rejects_old_macos(monkeypatch):
    import pytest
    monkeypatch.setattr(service.sys,'platform','darwin')
    monkeypatch.setattr(service.platform,'machine',lambda:'arm64')
    monkeypatch.setattr(service.platform,'mac_ver',lambda:('13.6',(),''))
    with pytest.raises(SystemExit,match='14 or newer'):service.check_host()


def test_launch_agent_round_trip_does_not_include_process_secrets(tmp_path,monkeypatch):
    monkeypatch.setenv('OPENSUBTITLES_API_KEY','test-secret')
    data=plistlib.dumps(service.launch_agent(tmp_path,tmp_path))
    assert b'test-secret' not in data and b'OPENSUBTITLES_API_KEY' not in data
