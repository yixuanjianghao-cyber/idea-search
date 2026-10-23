"""Verify the actual ZIP outside the build tree with no developer runtimes on PATH."""
import json
import os
from pathlib import Path
import socket
import subprocess
import sys
import tempfile
import zipfile

archive = Path(sys.argv[1]).resolve()
with tempfile.TemporaryDirectory(prefix='发布验证 with spaces ') as temporary:
    root = Path(temporary)
    with zipfile.ZipFile(archive) as bundle:
        for name in bundle.namelist():
            if not (root / name).resolve().is_relative_to(root): raise RuntimeError('Unsafe archive entry')
            if any(part in ('.env', '.github-finder.json', '.github-finder-ai-key.json', '.github-finder-desktop.json') for part in Path(name).parts): raise RuntimeError('User configuration in release')
        bundle.extractall(root)
    exe = root / 'IdeaSearch' / 'IdeaSearch.exe'
    assert (exe.parent / '_internal' / 'node.exe').is_file()
    assert (exe.parent / 'LICENSE').is_file()
    env = dict(os.environ)
    for key in ('GHF_PORT','GHF_NODE','NODE_OPTIONS','NODE_PATH','GITHUB_TOKEN','GH_TOKEN','DEEPSEEK_API_KEY'):
        env.pop(key, None)
    env.update(PATH=str(Path(os.environ['WINDIR'])/'System32'), QT_QPA_PLATFORM='offscreen', GHF_DATA_DIR=str(root/'fresh-user'))
    # Reproduce a port conflict without touching another application's process.
    occupied = socket.socket()
    try:
        try: occupied.bind(('127.0.0.1',17890)); occupied.listen()
        except OSError: pass
        result = subprocess.run([str(exe),'--smoke-test'],cwd=root,env=env,timeout=35,creationflags=subprocess.CREATE_NO_WINDOW)
        assert result.returncode == 0, f'Packaged smoke exit {result.returncode}'
    finally: occupied.close()
    print(json.dumps({'zip':archive.name,'clean_path':True,'relocated':True,'port_conflict':True,'exit':result.returncode}))
