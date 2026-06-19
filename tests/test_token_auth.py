"""Token 认证测试：QIAN_PPT_TOKEN 设置后写操作需带 X-Auth-Token。"""
import uuid
import pytest
import app as app_module


@pytest.fixture
def token_enabled():
    """临时启用 Token 认证，测试后恢复。"""
    original = app_module.AUTH_TOKEN
    app_module.AUTH_TOKEN = 'test-secret-token'
    yield
    app_module.AUTH_TOKEN = original


def test_write_blocked_without_token(client, token_enabled):
    """无 Token 时写操作返回 401。"""
    resp = client.post('/api/workspaces', json={'id': 'ws-no-token', 'name': 'ws-no-token'})
    assert resp.status_code == 401
    data = resp.get_json()
    assert data['error'] == 'unauthorized'


def test_write_allowed_with_correct_token(client, token_enabled):
    """带正确 Token 时写操作通过认证。"""
    ws_id = f'ws-token-{uuid.uuid4().hex[:8]}'
    resp = client.post(
        '/api/workspaces',
        json={'id': ws_id, 'name': ws_id},
        headers={'X-Auth-Token': 'test-secret-token'}
    )
    assert resp.status_code in (200, 201)


def test_write_blocked_with_wrong_token(client, token_enabled):
    """错误 Token 时写操作返回 401。"""
    resp = client.post(
        '/api/workspaces',
        json={'name': 'ws-wrong-token'},
        headers={'X-Auth-Token': 'wrong-token'}
    )
    assert resp.status_code == 401


def test_read_allowed_without_token(client, token_enabled):
    """读操作无需 Token。"""
    resp = client.get('/api/workspaces')
    assert resp.status_code == 200


def test_no_auth_when_token_unset(client):
    """未设置 Token 时所有操作免认证（本地零配置）。"""
    # 确保默认无 Token
    assert app_module.AUTH_TOKEN == ''
    resp = client.get('/api/workspaces')
    assert resp.status_code == 200
