"""Explicit user-triggered installation of missing runtimes using Windows winget."""
import os
import shutil

RUNTIMES = {
    'git': ('Git', 'Git.Git', 'https://git-scm.com/download/win'),
    'python': ('Python', 'Python.Python.3.13', 'https://www.python.org/downloads/windows/'),
    'node': ('Node.js', 'OpenJS.NodeJS.LTS', 'https://nodejs.org/en/download'),
    'docker': ('Docker Desktop', 'Docker.DockerDesktop', 'https://www.docker.com/products/docker-desktop/'),
}


def required_runtimes(how):
    return ['git', 'docker'] if how in ('compose','docker') else ['git','python'] if how == 'python' else ['git','node'] if how.startswith('node') else []


def installer_command(runtime):
    executable = shutil.which('winget')
    if not executable: return None
    return executable, ['install','--id',RUNTIMES[runtime][1],'--exact','--source','winget','--accept-package-agreements','--accept-source-agreements']


def refresh_process_path():
    if os.name != 'nt': return
    import winreg
    paths = [os.environ.get('PATH','')]
    for hive, path in [(winreg.HKEY_LOCAL_MACHINE,r'SYSTEM\CurrentControlSet\Control\Session Manager\Environment'), (winreg.HKEY_CURRENT_USER,r'Environment')]:
        try:
            with winreg.OpenKey(hive,path) as key: paths.append(os.path.expandvars(winreg.QueryValueEx(key,'Path')[0]))
        except OSError: pass
    os.environ['PATH'] = ';'.join(dict.fromkeys(part for path in paths for part in path.split(';') if part))
