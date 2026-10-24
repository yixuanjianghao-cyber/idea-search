"""Create a source-only ZIP from an explicit allowlist; never include local config."""
import hashlib
import json
from pathlib import Path
import re
from datetime import datetime
from zipfile import ZipFile, ZIP_DEFLATED

ROOT = Path(__file__).resolve().parent.parent
FILES = ('README.md', 'AGENTS.md', 'CHANGELOG.md', 'CONTRIBUTING.md', 'SECURITY.md', 'LICENSE',
         'THIRD_PARTY_NOTICES.md', '开始使用.txt', '.gitignore', 'package.json',
         'requirements.txt', 'requirements-build.txt', 'build.ps1', 'server.mjs',
         'config.mjs', 'cli.mjs')
SUFFIXES = {'.py', '.mjs', '.js', '.html', '.css', '.cmd', '.txt', '.md', '.yml', '.yaml', '.png', '.ico'}
SECRET = re.compile(rb'ghp_[A-Za-z0-9]{30,}|github_pat_[A-Za-z0-9_]{40,}|sk-[A-Za-z0-9]{32,}|-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----')


def main():
    paths = [ROOT / name for name in FILES]
    for folder in ('desktop', 'lib', 'public', 'scripts', 'assets', 'test', '.github'):
        paths += [p for p in (ROOT / folder).rglob('*') if p.is_file()
                  and '__pycache__' not in p.parts and p.suffix in SUFFIXES]
    paths = sorted(set(paths))
    for path in paths:
        if SECRET.search(path.read_bytes()):
            raise RuntimeError(f'Possible secret; inspect before packaging: {path.relative_to(ROOT)}')
    version = json.loads((ROOT / 'package.json').read_text(encoding='utf-8-sig'))['version']
    output = ROOT / 'dist' / ('opensource-' + datetime.now().strftime('%Y%m%d-%H%M%S-%f'))
    output.mkdir(parents=True)
    archive = output / f'IdeaSearch-{version}-source-MIT.zip'
    with ZipFile(archive, 'x', ZIP_DEFLATED) as bundle:
        for path in paths:
            bundle.write(path, 'IdeaSearch/' + path.relative_to(ROOT).as_posix())
    digest = hashlib.sha256(archive.read_bytes()).hexdigest()
    archive.with_suffix('.zip.sha256').write_text(digest + '\n', encoding='ascii')
    # ASCII JSON also works when Windows' console code page differs from UTF-8.
    print(json.dumps({'archive': str(archive), 'files': len(paths), 'sha256': digest}, ensure_ascii=True))


if __name__ == '__main__':
    main()
