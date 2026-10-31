"""Isolated browser-test server. Never uses the application's database."""
import tempfile
from pathlib import Path
import os
import uvicorn
import main
from manage_user import create_user

if __name__ == '__main__':
    test_root = Path(__file__).resolve().parent.parent / 'test-temp-e2e'
    test_root.mkdir(exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='doga-e2e-', dir=test_root) as directory:
        main.DB_PATH = str(Path(directory) / 'test.db')
        os.environ['COOKIE_SECURE'] = '0'
        for role in ('admin', 'viewer'):
            create_user('e2e-'+role, 'E2E-only-password-42', role)
        uvicorn.run(main.app, host='127.0.0.1', port=8001)
