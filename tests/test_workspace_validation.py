"""工作区 ID 校验与路径穿越防护测试。"""
import pytest
import app


class TestWorkspaceIdValidation:
    def test_valid_ids(self):
        assert app.validate_workspace_id("default") is True
        assert app.validate_workspace_id("my-workspace") is True
        assert app.validate_workspace_id("ws_123") is True
        assert app.validate_workspace_id("ABC") is True

    def test_invalid_ids(self):
        assert app.validate_workspace_id("") is False
        assert app.validate_workspace_id(None) is False
        assert app.validate_workspace_id(123) is False
        assert app.validate_workspace_id("../etc") is False
        assert app.validate_workspace_id("a/b") is False
        assert app.validate_workspace_id("a\\b") is False
        assert app.validate_workspace_id("a b") is False
        assert app.validate_workspace_id("a.b") is False
        assert app.validate_workspace_id("a:b") is False

    def test_normalize_raises_on_invalid(self):
        with pytest.raises(app.WorkspaceValidationError):
            app.normalize_workspace_id("../etc/passwd")

    def test_normalize_returns_default_when_none(self):
        # 无请求上下文时返回 default
        assert app.normalize_workspace_id(None) == "default"


class TestImageInfoPathTraversal:
    """A2: /api/image-info 路径穿越防护。"""

    def test_dotdot_traversal_blocked(self, client):
        # url=.. 时 filename='..'，os.path.join 会跳出上传目录
        resp = client.get('/api/image-info?url=..')
        assert resp.status_code == 403

    def test_normal_missing_file_returns_404(self, client):
        # 正常文件名但不存在，应返回 404 而非 403
        resp = client.get('/api/image-info?url=nonexistent.png')
        assert resp.status_code == 404


class TestUploadPathTraversal:
    """D9: 上传路径穿越防护。"""

    def test_upload_chinese_filename(self, client):
        """中文文件名应被保留（D9）。"""
        from io import BytesIO
        data = {
            'file': (BytesIO(b'\x89PNG\r\n\x1a\n'), '中文文件名.png')
        }
        resp = client.post('/api/upload', data=data, content_type='multipart/form-data')
        assert resp.status_code == 200
        body = resp.get_json()
        assert '中文文件名' in body['filename']
