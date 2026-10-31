"""Local setup and launcher. Run from any directory with Python 3.12+."""
from pathlib import Path
import argparse
import os
import shutil
import socket
import sqlite3
import subprocess
import sys
import threading
import time
import urllib.request
import webbrowser

ROOT = Path(__file__).resolve().parent


def run(args, cwd=ROOT, env=None):
    subprocess.run([str(arg) for arg in args], cwd=cwd, env=env, check=True)


def backup(path):
    if not path.exists():
        return
    folder = ROOT / 'yedekler'
    folder.mkdir(exist_ok=True)
    target = folder / f'doga-{time.time_ns()}.db'
    with sqlite3.connect(path.as_uri() + '?mode=ro', uri=True) as source:
        with sqlite3.connect(target) as dest:
            source.backup(dest)
            if dest.execute('PRAGMA integrity_check').fetchone()[0] != 'ok':
                raise RuntimeError('Veritabanı yedeği doğrulanamadı.')
    print(f'Veritabanı yedeği: {target}', flush=True)


def available_port(preferred):
    for port in (preferred, *range(8010, 8021)):
        with socket.socket() as sock:
            try:
                sock.bind(('127.0.0.1', port))
            except OSError:
                continue
            return port
    raise RuntimeError('Uygun port bulunamadı. --port ile başka port seçin.')


def open_when_ready(process, url):
    for _ in range(60):
        if process.poll() is not None:
            return
        try:
            with urllib.request.urlopen(url + '/api/health', timeout=1) as response:
                if response.status == 200:
                    webbrowser.open(url)
                    return
        except OSError:
            time.sleep(0.5)


def main():
    parser = argparse.ArgumentParser(description='Doğa Gıda yerel başlatıcı')
    parser.add_argument('--port', type=int, default=8000)
    parser.add_argument('--no-browser', action='store_true')
    parser.add_argument('--rebuild', action='store_true', help='Arayüzü yeniden derle')
    args = parser.parse_args()
    if sys.version_info < (3, 12):
        raise RuntimeError('Python 3.12 veya üstü gerekli.')
    if not 1 <= args.port <= 65535:
        parser.error('Port 1–65535 arasında olmalı.')
    needs_build = args.rebuild or not (ROOT / 'frontend/dist/index.html').is_file()
    if needs_build:
        npm = shutil.which('npm.cmd' if os.name == 'nt' else 'npm')
        node = shutil.which('node')
        if not npm or not node:
            raise RuntimeError('Node.js 22.12+ LTS kurun (https://nodejs.org), ardından tekrar açın.')
        version = subprocess.check_output([node, '--version'], text=True).strip().lstrip('v')
        if tuple(map(int, version.split('.')[:2])) < (22, 12):
            raise RuntimeError('Node.js 22.12 veya üstü gerekli.')
    # No activation or PowerShell execution-policy change is needed.
    python = ROOT / '.venv' / ('Scripts/python.exe' if os.name == 'nt' else 'bin/python')
    if not python.exists():
        run([sys.executable, '-m', 'venv', ROOT / '.venv'])
    run([python, '-m', 'pip', 'install', '-r', ROOT / 'backend/requirements.txt'])
    if needs_build:
        print('Arayüz hazırlanıyor...', flush=True)
        run([npm, 'ci'], ROOT / 'frontend')
        run([npm, 'run', 'build'], ROOT / 'frontend')
    env = os.environ.copy()
    env['COOKIE_SECURE'] = '0'  # This launcher binds only to loopback HTTP.
    db = Path(env.get('DATABASE_PATH', ROOT / 'backend/data/doga.db')).resolve()
    env['DATABASE_PATH'] = str(db)
    backup(db)
    run([python, '-c', 'import main; main.initialize()'], ROOT / 'backend', env)
    with sqlite3.connect(db) as connection:
        has_admin = connection.execute("SELECT 1 FROM users WHERE role='admin' AND active=1").fetchone()
    if not has_admin:
        print('İlk yönetici hesabını oluşturun. Parola en az 12 karakter olmalı.', flush=True)
        username = input('Yönetici kullanıcı adı: ').strip()
        run([python, 'manage_user.py', username, '--role', 'admin'], ROOT / 'backend', env)
    port = available_port(args.port)
    url = f'http://127.0.0.1:{port}'
    if port != args.port:
        print(f'{args.port} portu dolu; mevcut program korunarak {port} kullanılacak.', flush=True)
    print(f'Program adresi: {url}\nKapatmak için Ctrl+C.', flush=True)
    process = subprocess.Popen([str(python), '-m', 'uvicorn', 'main:app', '--host', '127.0.0.1', '--port', str(port)], cwd=ROOT / 'backend', env=env)
    if not args.no_browser:
        threading.Thread(target=open_when_ready, args=(process, url), daemon=True).start()
    try:
        code = process.wait()
    except KeyboardInterrupt:
        if process.poll() is None:
            process.terminate()
        process.wait()
        return
    if code:
        raise RuntimeError(f'Sunucu başlatılamadı (kod {code}). Yukarıdaki hata kaydını kontrol edin.')


if __name__ == '__main__':
    try:
        main()
    except (OSError, RuntimeError, subprocess.CalledProcessError) as error:
        print(f'\nBaşlatma tamamlanamadı: {error}', file=sys.stderr)
        sys.exit(1)
