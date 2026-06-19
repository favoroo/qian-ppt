"""导入数据归一化测试：结构校验、ID 重写防冲突。"""
import pytest
import app


class TestNormalizeImportData:
    def test_valid_data(self):
        data = {"settings": {"title": "T"}, "slides": [{"id": "s1", "canvas_elements": [{"type": "text"}]}]}
        normalized, err = app.normalize_import_data(data)
        assert err is None
        assert normalized['settings']['title'] == "T"
        assert normalized['slides'][0]['id'] == "s1"

    def test_missing_slides(self):
        normalized, err = app.normalize_import_data({"settings": {}})
        assert err is not None
        assert "slides" in err

    def test_non_dict(self):
        normalized, err = app.normalize_import_data([1, 2, 3])
        assert err is not None

    def test_slide_must_be_dict(self):
        data = {"slides": ["not a dict"]}
        normalized, err = app.normalize_import_data(data)
        assert err is not None
        assert "JSON 对象" in err

    def test_element_must_have_type(self):
        data = {"slides": [{"id": "s1", "canvas_elements": [{"x": 1}]}]}
        normalized, err = app.normalize_import_data(data)
        assert err is not None
        assert "type" in err

    def test_defaults_filled(self):
        data = {"slides": [{}]}
        normalized, err = app.normalize_import_data(data)
        assert err is None
        slide = normalized['slides'][0]
        assert 'id' in slide
        assert slide['theme'] == 'light'
        assert slide['canvas_elements'] == []
        assert slide['images'] == []
        assert 'backgroundColor' in slide


class TestRewriteImportIds:
    """append 模式下重写 slide/element ID 防冲突。"""

    def test_rewrite_changes_ids(self):
        imported = {
            "slides": [
                {"id": "slide-1", "canvas_elements": [{"id": "elem-1", "type": "text"}]}
            ]
        }
        existing = {"slides": [{"id": "slide-1", "canvas_elements": []}]}
        result = app.rewrite_import_ids(imported, existing)
        # ID 应被重写，不再是原值
        assert result['slides'][0]['id'] != "slide-1"
        assert result['slides'][0]['canvas_elements'][0]['id'] != "elem-1"

    def test_rewrite_keeps_structure(self):
        imported = {
            "slides": [
                {"id": "s1", "canvas_elements": [{"id": "e1", "type": "text", "text": "hi"}]}
            ]
        }
        existing = {"slides": []}
        result = app.rewrite_import_ids(imported, existing)
        elem = result['slides'][0]['canvas_elements'][0]
        assert elem['type'] == "text"
        assert elem['text'] == "hi"
