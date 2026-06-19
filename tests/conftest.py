"""pytest 配置：确保测试可导入 app 模块，并提供 Flask 测试客户端。"""
import os
import sys
import tempfile
import shutil

import pytest

# 将项目根目录加入 sys.path，使 import app 可用
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import app as app_module


@pytest.fixture
def client():
    """Flask 测试客户端，使用真实 app 但隔离工作区数据。"""
    app_module.app.config['TESTING'] = True
    with app_module.app.test_client() as c:
        yield c
