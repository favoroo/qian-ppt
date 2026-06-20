import sys
import os
from pathlib import Path

# Add the slide-editor path to sys.path
editor_path = str(Path(__file__).resolve().parent.parent / '.agents' / 'skills' / 'slide-editor')
if editor_path not in sys.path:
    sys.path.insert(0, editor_path)

from three_templates import build_3d_element, get_preset_list

def test_build_3d_element_presets():
    # Test that new presets exist in the list
    presets = get_preset_list()
    preset_names = [p["name"] for p in presets]
    assert "torusKnot" in preset_names
    assert "dna" in preset_names
    assert "globe" in preset_names

def test_build_3d_element_generation():
    # Test generating standard shapes with floating and neonLight
    elem = build_3d_element(geometry="cube", floating=True, neon_light=True)
    assert "BoxGeometry" in elem["html"]
    assert "floating=true" in elem["html"]
    assert "PointLight" in elem["html"]
    assert "MeshStandardMaterial" in elem["html"]

def test_build_3d_element_dna():
    # Test generating DNA helix
    elem = build_3d_element(geometry="dna", floating=True, neon_light=True)
    assert "CylinderGeometry" in elem["html"]
    assert "SphereGeometry" in elem["html"]
    assert "group.rotation.y" in elem["html"]

def test_build_3d_element_globe():
    # Test generating Globe
    elem = build_3d_element(geometry="globe", floating=True, neon_light=True)
    assert "TorusGeometry" in elem["html"]
    assert "SphereGeometry" in elem["html"]
    assert "satAngle" in elem["html"]
