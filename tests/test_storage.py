"""存储层测试：原子写、备份保留、版本单调递增、乐观锁冲突。

使用临时工作区隔离，测试后清理。
"""
import os
import json
import shutil
import pytest
import app


TEST_WORKSPACE = "test_storage_ws"


@pytest.fixture
def clean_workspace():
    """提供干净的测试工作区，测试后删除。"""
    wid = app.ensure_workspace(TEST_WORKSPACE, "测试工作区")
    data_file = app.workspace_data_file(wid)
    backup_folder = app.workspace_backup_folder(wid)
    # 清空备份数据
    if os.path.exists(data_file):
        os.remove(data_file)
    if os.path.exists(backup_folder):
        shutil.rmtree(backup_folder)
    os.makedirs(backup_folder, exist_ok=True)
    yield wid
    # 清理
    ws_dir = app.workspace_dir(wid)
    if os.path.exists(ws_dir):
        shutil.rmtree(ws_dir, ignore_errors=True)
    meta = app.read_workspaces_meta()
    meta.get('workspaces', {}).pop(TEST_WORKSPACE, None)
    app.write_workspaces_meta(meta)


class TestAtomicWrite:
    def test_atomic_write_creates_valid_json(self, clean_workspace):
        data = {"_version": 0, "settings": {}, "slides": [{"id": "s1"}]}
        app.save_slides(data, clean_workspace)
        data_file = app.workspace_data_file(clean_workspace)
        # 文件应是合法 JSON
        with open(data_file, 'r', encoding='utf-8') as f:
            loaded = json.load(f)
        assert loaded['slides'][0]['id'] == "s1"

    def test_atomic_write_no_tmp_left(self, clean_workspace):
        data = {"_version": 0, "settings": {}, "slides": []}
        app.save_slides(data, clean_workspace)
        ws_dir = app.workspace_dir(clean_workspace)
        # 不应残留临时文件
        files = os.listdir(ws_dir)
        tmps = [f for f in files if f.endswith('.tmp') or f.startswith('.save_')]
        assert tmps == []


class TestBackupPruning:
    def test_backup_keeps_only_10(self, clean_workspace):
        for i in range(12):
            app.save_slides({"_version": 0, "settings": {"i": i}, "slides": []}, clean_workspace)
        backup_folder = app.workspace_backup_folder(clean_workspace)
        backups = [f for f in os.listdir(backup_folder) if f.startswith('slides_')]
        assert len(backups) == 10

    def test_backup_created_before_overwrite(self, clean_workspace):
        # 第一次保存（ensure_workspace 可能已创建默认文件，此处备份的是默认数据）
        app.save_slides({"_version": 0, "settings": {"v": 1}, "slides": []}, clean_workspace)
        # 第二次保存：备份的是第一次的数据 {v:1}
        app.save_slides({"_version": 0, "settings": {"v": 2}, "slides": []}, clean_workspace)
        backup_folder = app.workspace_backup_folder(clean_workspace)
        backups = sorted([f for f in os.listdir(backup_folder) if f.startswith('slides_')])
        assert len(backups) >= 1
        # 最新的备份应包含第一次保存的数据
        with open(os.path.join(backup_folder, backups[-1]), 'r', encoding='utf-8') as f:
            backup_data = json.load(f)
        assert backup_data['settings']['v'] == 1


class TestVersionMonotonic:
    def test_version_increases(self, clean_workspace):
        v1 = app.save_slides({"_version": 0, "settings": {}, "slides": []}, clean_workspace)
        v2 = app.save_slides({"_version": 0, "settings": {}, "slides": []}, clean_workspace)
        assert v2 > v1

    def test_next_version_no_collision(self, clean_workspace):
        """同毫秒内两次保存版本号不碰撞。"""
        import time
        v1 = app.save_slides({"_version": 0, "settings": {}, "slides": []}, clean_workspace)
        v2 = app.save_slides({"_version": 0, "settings": {}, "slides": []}, clean_workspace)
        assert v1 != v2


class TestOptimisticLock:
    def test_correct_version_succeeds(self, clean_workspace):
        v1 = app.save_slides({"_version": 0, "settings": {}, "slides": []}, clean_workspace)
        # 用正确版本再次保存
        v2 = app.save_slides({"_version": 0, "settings": {"v": 2}, "slides": []}, clean_workspace, expected_version=v1)
        assert v2 > v1

    def test_stale_version_raises_conflict(self, clean_workspace):
        v1 = app.save_slides({"_version": 0, "settings": {}, "slides": []}, clean_workspace)
        # 先保存一次推进版本
        app.save_slides({"_version": 0, "settings": {"v": 2}, "slides": []}, clean_workspace)
        # 用旧版本 v1 保存应冲突
        with pytest.raises(app.VersionConflictError) as exc_info:
            app.save_slides({"_version": 0, "settings": {"v": 3}, "slides": []}, clean_workspace, expected_version=v1)
        assert exc_info.value.current_version != v1

    def test_no_expected_version_skips_check(self, clean_workspace):
        """expected_version=None 时不校验（兼容老前端）。"""
        v1 = app.save_slides({"_version": 0, "settings": {}, "slides": []}, clean_workspace)
        # 不传 expected_version，即使版本不匹配也能保存
        v2 = app.save_slides({"_version": 0, "settings": {"v": 2}, "slides": []}, clean_workspace)
        assert v2 > v1


class TestLoadRecovery:
    def test_load_recovers_from_backup(self, clean_workspace):
        # 保存两次：第二次保存会备份第一次的真实数据
        app.save_slides({"_version": 0, "settings": {"name": "real"}, "slides": []}, clean_workspace)
        app.save_slides({"_version": 0, "settings": {"name": "real2"}, "slides": []}, clean_workspace)
        # 损坏 slides.json
        data_file = app.workspace_data_file(clean_workspace)
        with open(data_file, 'w', encoding='utf-8') as f:
            f.write("{ corrupted json !!!")
        # load_slides 应从备份恢复（备份含第一次的真实数据）
        recovered = app.load_slides(clean_workspace)
        assert recovered['settings']['name'] == "real"
