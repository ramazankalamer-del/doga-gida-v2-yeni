"""A source-only checkout must explain how to prepare the frontend."""
from fastapi.testclient import TestClient
import main
import pytest


def test_missing_frontend_explains_setup(tmp_path, monkeypatch):
    if main.DIST.exists():
        pytest.skip('Derlenmiş arayüz HTTP açılış kontrolünde doğrulanır.')
    monkeypatch.setattr(main, 'DB_PATH', str(tmp_path / 'startup.db'))
    with TestClient(main.app) as client:
        response = client.get('/')
        assert response.status_code == 503
        assert 'BASLAT.bat' in response.text
        assert 'npm run build' in response.text
        assert client.get('/api/health').json() == {'status': 'ok'}
        assert client.get('/docs').status_code == 200
