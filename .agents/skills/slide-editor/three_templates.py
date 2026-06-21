"""Three.js 3D 元素代码模板。

为幻灯片编辑器和 Agent CLI 生成一致的 Three.js 场景代码。
生成的代码内嵌在 HTML 元素的 html 字段中，通过 <script> 标签执行。
"""

from __future__ import annotations

import json
import time
import random
from typing import Any

# 3D 预设列表
PRESETS = {
    "cube": {
        "label": "立方体",
        "icon": "cube",
        "geometry": "cube",
    },
    "sphere": {
        "label": "球体",
        "icon": "circle",
        "geometry": "sphere",
    },
    "torus": {
        "label": "圆环",
        "icon": "donut_large",
        "geometry": "torus",
    },
    "cylinder": {
        "label": "圆柱",
        "icon": "cylinder",
        "geometry": "cylinder",
    },
    "cone": {
        "label": "圆锥",
        "icon": "change_history",
        "geometry": "cone",
    },
    "icosahedron": {
        "label": "二十面体",
        "icon": "pentagon",
        "geometry": "icosahedron",
    },
    "particles": {
        "label": "粒子系统",
        "icon": "grain",
        "geometry": "particles",
    },
    "galaxy": {
        "label": "星系粒子",
        "icon": "cyclone",
        "geometry": "galaxy",
    },
    "waves": {
        "label": "动态波浪",
        "icon": "waves",
        "geometry": "waves",
    },
    "network": {
        "label": "科技网络",
        "icon": "hub",
        "geometry": "network",
    },
    "torusKnot": {
        "label": "圆环结",
        "icon": "all_inclusive",
        "geometry": "torusKnot",
    },
    "dna": {
        "label": "双螺旋",
        "icon": "dna",
        "geometry": "dna",
    },
    "globe": {
        "label": "科技地球",
        "icon": "language",
        "geometry": "globe",
    },

    "custom": {
        "label": "自定义代码",
        "icon": "code",
        "geometry": "custom",
    },
}

# 默认 3D 参数
DEFAULT_DATA = {
    "geometry": "cube",
    "color": "#C5E803",
    "autoRotate": True,
    "rotateSpeed": 0.01,
    "metalness": 0.1,
    "roughness": 0.85,
    "wireframe": False,
    "background": "transparent",
    "floating": True,
    "neonLight": False,
}

# 默认尺寸
DEFAULT_SIZE = {"width": 240, "height": 240}

# CSS 样式（所有 3D 元素共用）
THREE_CSS = ".three-canvas{width:100%;height:100%;display:block}"


def _gen_uid() -> str:
    """生成唯一实例 id。"""
    return f"three-{int(time.time()*1000)}-{random.randint(1000, 9999)}"


def _geometry_code(geometry: str) -> str:
    """返回创建几何体的 JS 代码片段。"""
    if geometry == "cube":
        return "var geometry = new THREE.BoxGeometry(1.5, 1.5, 1.5);"
    if geometry == "sphere":
        return "var geometry = new THREE.SphereGeometry(1, 48, 32);"
    if geometry == "torus":
        return "var geometry = new THREE.TorusGeometry(1, 0.35, 24, 80);"
    if geometry == "cylinder":
        return "var geometry = new THREE.CylinderGeometry(0.8, 0.8, 1.8, 48);"
    if geometry == "cone":
        return "var geometry = new THREE.ConeGeometry(1, 1.8, 48);"
    if geometry == "icosahedron":
        return "var geometry = new THREE.IcosahedronGeometry(1.2, 0);"
    if geometry == "torusKnot":
        return "var geometry = new THREE.TorusKnotGeometry(0.7, 0.22, 120, 16);"
    return "var geometry = new THREE.BoxGeometry(1.5, 1.5, 1.5);"


def generate_three_js_code(data: dict[str, Any], uid: str | None = None) -> str:
    """根据参数生成完整的 Three.js 场景代码（含 canvas 和 script 标签）。

    Args:
        data: 3D 参数字典（geometry/color/autoRotate/rotateSpeed/metalness/roughness/wireframe/background）
        uid: 唯一实例 id，若为 None 则自动生成

    Returns:
        完整的 HTML 字符串，包含 <canvas> 和 <script>
    """
    if uid is None:
        uid = _gen_uid()

    geometry = data.get("geometry", "cube")
    color = data.get("color", "#C5E803")
    auto_rotate = "true" if data.get("autoRotate", True) else "false"
    rotate_speed = float(data.get("rotateSpeed", 0.01))
    metalness = float(data.get("metalness", 0.1))
    roughness = float(data.get("roughness", 0.85))
    wireframe = "true" if data.get("wireframe", False) else "false"
    background = data.get("background", "transparent")
    floating = "true" if data.get("floating", True) else "false"
    neon_light = "true" if data.get("neonLight", False) else "false"

    # 粒子系统/特殊几何体使用特殊渲染
    if geometry == "particles":
        return _generate_particles_code(uid, color, auto_rotate, rotate_speed, background, floating)
    if geometry == "galaxy":
        return _generate_galaxy_code(uid, color, auto_rotate, rotate_speed, background, floating)
    if geometry == "waves":
        return _generate_waves_code(uid, color, auto_rotate, rotate_speed, background, floating)
    if geometry == "network":
        return _generate_network_code(uid, color, auto_rotate, rotate_speed, background, floating)
    if geometry == "dna":
        return _generate_dna_code(uid, color, auto_rotate, rotate_speed, background, floating, neon_light)
    if geometry == "globe":
        return _generate_globe_code(uid, color, auto_rotate, rotate_speed, background, floating, neon_light)

    geom_code = _geometry_code(geometry)
    bg_alpha = "true" if background == "transparent" else "false"
    bg_clear = "renderer.setClearColor(0x000000, 0);" if background == "transparent" else f'renderer.setClearColor(new THREE.Color("{background}"), 1);'

    if data.get("neonLight", False):
        light_setup = f'''scene.add(new THREE.AmbientLight(0xffffff,0.3));
var d1=new THREE.DirectionalLight(0xffffff,0.5);d1.position.set(2,3,4);scene.add(d1);
var p1=new THREE.PointLight(0x00f3ff,1.5,12);p1.position.set(-3,3,2);scene.add(p1);
var p2=new THREE.PointLight(0xff00a0,1.5,12);p2.position.set(3,-3,2);scene.add(p2);'''
    else:
        light_setup = f'''scene.add(new THREE.AmbientLight(0xffffff,0.5));
var d1=new THREE.DirectionalLight(0xffffff,0.8);d1.position.set(2,3,4);scene.add(d1);
var d2=new THREE.DirectionalLight(0xffffff,0.3);d2.position.set(-2,-1,-3);scene.add(d2);'''

    # 颜色转 0xRRGGBB
    color_hex = color.lstrip("#")
    color_js = f'0x{color_hex}'

    script = f'''(function(){{
var uid="{uid}";
var host=document.querySelector('[data-uid="'+uid+'"]');
if(!host||!window.THREE)return;
if(host.__threeCleanup){{host.__threeCleanup();host.__threeCleanup=null;}}
var canvas=host.querySelector('canvas.three-canvas');
if(!canvas){{canvas=document.createElement('canvas');canvas.className='three-canvas';host.appendChild(canvas);}}
var w=host.clientWidth||240,h=host.clientHeight||240;
var scene=new THREE.Scene();
var camera=new THREE.PerspectiveCamera(50,w/h,0.1,1000);
camera.position.set(0,0,4);
var renderer=new THREE.WebGLRenderer({{canvas:canvas,antialias:true,alpha:{bg_alpha}}});
renderer.setPixelRatio(Math.min(window.devicePixelRatio||1,2));
renderer.setSize(w,h,false);
{bg_clear}
{light_setup}
{geom_code}
var material=new THREE.MeshStandardMaterial({{color:{color_js},metalness:{metalness},roughness:{roughness},wireframe:{wireframe}}});
var mesh=new THREE.Mesh(geometry,material);
scene.add(mesh);
var wireframeGeom=null,wireframeMat=null;
if(geometry instanceof THREE.SphereGeometry&&!{wireframe}){{
wireframeGeom=new THREE.SphereGeometry(1.002,24,16);
wireframeMat=new THREE.MeshBasicMaterial({{color:{color_js},wireframe:true,transparent:true,opacity:0.15}});
var wireframeMesh=new THREE.Mesh(wireframeGeom,wireframeMat);
mesh.add(wireframeMesh);
}}
var autoRotate={auto_rotate},rotateSpeed={rotate_speed},animId=null;
var floating={floating},floatOffset=0;
var isPaused=false,lastFrameTime=performance.now();
var FRAME_MIN=1000/60;
function animate(now){{
animId=requestAnimationFrame(animate);
if(isPaused||document.hidden){{lastFrameTime=now;return;}}
var elapsed=now-lastFrameTime;
if(elapsed<FRAME_MIN)return;
lastFrameTime=now-(elapsed%FRAME_MIN);
var dt=Math.min(elapsed/1000,0.1);
var timeScale=dt*60;
if(autoRotate){{mesh.rotation.x+=rotateSpeed*timeScale;mesh.rotation.y+=rotateSpeed*timeScale;}}
if(floating){{floatOffset+=0.025*timeScale;mesh.position.y=Math.sin(floatOffset)*0.2;}}
renderer.render(scene,camera);
}}
requestAnimationFrame(animate);
function onResize(){{
var rect=host.getBoundingClientRect();
var nw=Math.max(1,Math.round(rect.width));
var nh=Math.max(1,Math.round(rect.height));
var maxSize=1024;
var r=Math.min(1,maxSize/Math.max(nw,nh));
nw=Math.round(nw*r);nh=Math.round(nh*r);
if(nw!==w||nh!==h){{w=nw;h=nh;camera.aspect=w/h;camera.updateProjectionMatrix();renderer.setPixelRatio(Math.min(window.devicePixelRatio||1,2));renderer.setSize(w,h,false);}}
}}
host.__threeResize=onResize;
host.__threePause=function(){{
if(!isPaused){{isPaused=true;if(animId){{cancelAnimationFrame(animId);animId=null;}}}}
}};
host.__threeResume=function(){{
if(isPaused){{isPaused=false;lastFrameTime=performance.now();if(!animId){{animId=requestAnimationFrame(animate);}}}}
}};
host.__threeCleanup=function(){{
if(animId){{cancelAnimationFrame(animId);animId=null;}}
try{{
geometry.dispose();
material.dispose();
if(wireframeGeom)wireframeGeom.dispose();
if(wireframeMat)wireframeMat.dispose();
renderer.dispose();
}}catch(e){{}}
host.__threeResize=null;host.__threePause=null;host.__threeResume=null;
}};
}})();'''

    return ('<div class="three-host" data-uid="' + uid +
            '" style="width:100%;height:100%;position:relative;overflow:hidden;">'
            '<canvas class="three-canvas"></canvas></div>' +
            '<scr' + 'i' + 'pt>' + script + '</scr' + 'i' + 'pt>')


def _generate_particles_code(uid: str, color: str, auto_rotate: str, rotate_speed: float, background: str, floating: str) -> str:
    """生成粒子系统代码。"""
    bg_alpha = "true" if background == "transparent" else "false"
    bg_clear = "renderer.setClearColor(0x000000, 0);" if background == "transparent" else f'renderer.setClearColor(new THREE.Color("{background}"), 1);'
    color_hex = color.lstrip("#")
    color_js = f'0x{color_hex}'

    script = f'''(function(){{
var uid="{uid}";
var host=document.querySelector('[data-uid="'+uid+'"]');
if(!host||!window.THREE)return;
if(host.__threeCleanup){{host.__threeCleanup();host.__threeCleanup=null;}}
var canvas=host.querySelector('canvas.three-canvas');
if(!canvas){{canvas=document.createElement('canvas');canvas.className='three-canvas';host.appendChild(canvas);}}
var w=host.clientWidth||240,h=host.clientHeight||240;
var scene=new THREE.Scene();
var camera=new THREE.PerspectiveCamera(50,w/h,0.1,1000);
camera.position.set(0,0,5.5);
var renderer=new THREE.WebGLRenderer({{canvas:canvas,antialias:true,alpha:{bg_alpha}}});
renderer.setPixelRatio(Math.min(window.devicePixelRatio||1,2));
renderer.setSize(w,h,false);
{bg_clear}
var count=600;
var positions=new Float32Array(count*3);
for(var i=0;i<count;i++){{positions[i*3]=(Math.random()-0.5)*3.2;positions[i*3+1]=(Math.random()-0.5)*3.2;positions[i*3+2]=(Math.random()-0.5)*3.2;}}
var geo=new THREE.BufferGeometry();
geo.setAttribute('position',new THREE.BufferAttribute(positions,3));
var mat=new THREE.PointsMaterial({{color:{color_js},size:0.05,transparent:true,opacity:0.85}});
var points=new THREE.Points(geo,mat);
var group=new THREE.Group();
group.add(points);
scene.add(group);

// 自适应缩放：根据包围盒与相机视锥计算安全比例
(function(){{
  var box = new THREE.Box3().setFromObject(group);
  var center = new THREE.Vector3();
  box.getCenter(center);
  group.position.sub(center);
  var size = new THREE.Vector3();
  box.getSize(size);
  var halfZ = size.z * 0.5;
  var halfX = size.x * 0.5;
  var halfY = size.y * 0.5;
  var frontDist = camera.position.z - halfZ;
  if (frontDist > 0.01 && halfX > 0.001 && halfY > 0.001) {{
    var vFov = camera.fov * Math.PI / 180;
    var visibleHalfH = frontDist * Math.tan(vFov * 0.5);
    var visibleHalfW = visibleHalfH * camera.aspect;
    var scale = Math.min(1, Math.min(
      visibleHalfW * 0.85 / halfX,
      visibleHalfH * 0.85 / halfY
    ));
    if (scale > 0 && isFinite(scale)) {{
      group.scale.setScalar(scale);
    }}
  }}
}})();

var autoRotate={auto_rotate},rotateSpeed={rotate_speed},animId=null;
var floating={floating},floatOffset=0;
var isPaused=false,lastFrameTime=performance.now();
var FRAME_MIN=1000/60;
function animate(now){{
animId=requestAnimationFrame(animate);
if(isPaused||document.hidden){{lastFrameTime=now;return;}}
var elapsed=now-lastFrameTime;
if(elapsed<FRAME_MIN)return;
lastFrameTime=now-(elapsed%FRAME_MIN);
var dt=Math.min(elapsed/1000,0.1);
var timeScale=dt*60;
if(autoRotate){{group.rotation.y+=rotateSpeed*timeScale;group.rotation.x+=rotateSpeed*0.5*timeScale;}}
if(floating){{floatOffset+=0.025*timeScale;group.position.y=Math.sin(floatOffset)*0.2;}}
renderer.render(scene,camera);
}}
requestAnimationFrame(animate);
function onResize(){{
var rect=host.getBoundingClientRect();
var nw=Math.max(1,Math.round(rect.width));
var nh=Math.max(1,Math.round(rect.height));
var maxSize=1024;
var r=Math.min(1,maxSize/Math.max(nw,nh));
nw=Math.round(nw*r);nh=Math.round(nh*r);
if(nw!==w||nh!==h){{w=nw;h=nh;camera.aspect=w/h;camera.updateProjectionMatrix();renderer.setPixelRatio(Math.min(window.devicePixelRatio||1,2));renderer.setSize(w,h,false);}}
}}
host.__threeResize=onResize;
host.__threePause=function(){{
if(!isPaused){{isPaused=true;if(animId){{cancelAnimationFrame(animId);animId=null;}}}}
}};
host.__threeResume=function(){{
if(isPaused){{isPaused=false;lastFrameTime=performance.now();if(!animId){{animId=requestAnimationFrame(animate);}}}}
}};
host.__threeCleanup=function(){{
if(animId){{cancelAnimationFrame(animId);animId=null;}}
try{{geo.dispose();mat.dispose();renderer.dispose();}}catch(e){{}}
host.__threeResize=null;host.__threePause=null;host.__threeResume=null;
}};
}})();'''

    return ('<div class="three-host" data-uid="' + uid +
            '" style="width:100%;height:100%;position:relative;overflow:hidden;">'
            '<canvas class="three-canvas"></canvas></div>' +
            '<scr' + 'i' + 'pt>' + script + '</scr' + 'i' + 'pt>')




def _generate_galaxy_code(uid: str, color: str, auto_rotate: str, rotate_speed: float, background: str, floating: str) -> str:
    bg_alpha = "true" if background == "transparent" else "false"
    bg_clear = "renderer.setClearColor(0x000000, 0);" if background == "transparent" else f'renderer.setClearColor(new THREE.Color("{background}"), 1);'
    color_hex = color.lstrip("#")
    color_js = f'0x{color_hex}'

    script = f'''(function(){{
var uid="{uid}";
var host=document.querySelector('[data-uid="'+uid+'"]');
if(!host||!window.THREE)return;
if(host.__threeCleanup){{host.__threeCleanup();host.__threeCleanup=null;}}
var canvas=host.querySelector('canvas.three-canvas');
if(!canvas){{canvas=document.createElement('canvas');canvas.className='three-canvas';host.appendChild(canvas);}}
var w=host.clientWidth||240,h=host.clientHeight||240;
var scene=new THREE.Scene();
var camera=new THREE.PerspectiveCamera(60,w/h,0.1,1000);
camera.position.set(0,4.5,7.5);
camera.lookAt(0,0,0);
var renderer=new THREE.WebGLRenderer({{canvas:canvas,antialias:true,alpha:{bg_alpha}}});
renderer.setPixelRatio(Math.min(window.devicePixelRatio||1,2));
renderer.setSize(w,h,false);
{bg_clear}
var count=2000;
var positions=new Float32Array(count*3);
var colors=new Float32Array(count*3);
var colorObj=new THREE.Color({color_js});
var branches=3;
for(var i=0;i<count;i++){{
  var radius=Math.random()*4;
  var spinAngle=radius*2;
  var branchAngle=((i%branches)/branches)*Math.PI*2;
  var randomX=Math.pow(Math.random(),3)*(Math.random()<0.5?1:-1)*0.5*(4-radius);
  var randomY=Math.pow(Math.random(),3)*(Math.random()<0.5?1:-1)*0.5*(4-radius);
  var randomZ=Math.pow(Math.random(),3)*(Math.random()<0.5?1:-1)*0.5*(4-radius);
  positions[i*3]=Math.cos(branchAngle+spinAngle)*radius+randomX;
  positions[i*3+1]=randomY;
  positions[i*3+2]=Math.sin(branchAngle+spinAngle)*radius+randomZ;
  
  var mixColor=colorObj.clone();
  mixColor.lerp(new THREE.Color(0xffffff), Math.random()*0.4);
  colors[i*3]=mixColor.r;
  colors[i*3+1]=mixColor.g;
  colors[i*3+2]=mixColor.b;
}}
var geo=new THREE.BufferGeometry();
geo.setAttribute('position',new THREE.BufferAttribute(positions,3));
geo.setAttribute('color',new THREE.BufferAttribute(colors,3));
var mat=new THREE.PointsMaterial({{size:0.04,vertexColors:true,transparent:true,opacity:0.8,blending:THREE.AdditiveBlending,depthWrite:false}});
var points=new THREE.Points(geo,mat);
scene.add(points);
var autoRotate={auto_rotate},rotateSpeed={rotate_speed},animId=null;
var floating={floating},floatOffset=0;
var isPaused=false,lastFrameTime=performance.now();
var FRAME_MIN=1000/60;
function animate(now){{
animId=requestAnimationFrame(animate);
if(isPaused||document.hidden){{lastFrameTime=now;return;}}
var elapsed=now-lastFrameTime;
if(elapsed<FRAME_MIN)return;
lastFrameTime=now-(elapsed%FRAME_MIN);
var dt=Math.min(elapsed/1000,0.1);
var timeScale=dt*60;
if(autoRotate){{points.rotation.y+=rotateSpeed*0.8*timeScale;}}
if(floating){{floatOffset+=0.025*timeScale;points.position.y=Math.sin(floatOffset)*0.2;}}
renderer.render(scene,camera);
}}
requestAnimationFrame(animate);
function onResize(){{
var rect=host.getBoundingClientRect();
var nw=Math.max(1,Math.round(rect.width));
var nh=Math.max(1,Math.round(rect.height));
var maxSize=1024;
var r=Math.min(1,maxSize/Math.max(nw,nh));
nw=Math.round(nw*r);nh=Math.round(nh*r);
if(nw!==w||nh!==h){{w=nw;h=nh;camera.aspect=w/h;camera.updateProjectionMatrix();renderer.setPixelRatio(Math.min(window.devicePixelRatio||1,2));renderer.setSize(w,h,false);}}
}}
host.__threeResize=onResize;
host.__threePause=function(){{
if(!isPaused){{isPaused=true;if(animId){{cancelAnimationFrame(animId);animId=null;}}}}
}};
host.__threeResume=function(){{
if(isPaused){{isPaused=false;lastFrameTime=performance.now();if(!animId){{animId=requestAnimationFrame(animate);}}}}
}};
host.__threeCleanup=function(){{
if(animId){{cancelAnimationFrame(animId);animId=null;}}
try{{geo.dispose();mat.dispose();renderer.dispose();}}catch(e){{}}
host.__threeResize=null;host.__threePause=null;host.__threeResume=null;
}};
}})();'''

    return ('<div class="three-host" data-uid="' + uid +
            '" style="width:100%;height:100%;position:relative;overflow:hidden;">'
            '<canvas class="three-canvas"></canvas></div>' +
            '<scr' + 'i' + 'pt>' + script + '</scr' + 'i' + 'pt>')


def _generate_waves_code(uid: str, color: str, auto_rotate: str, rotate_speed: float, background: str, floating: str) -> str:
    bg_alpha = "true" if background == "transparent" else "false"
    bg_clear = "renderer.setClearColor(0x000000, 0);" if background == "transparent" else f'renderer.setClearColor(new THREE.Color("{background}"), 1);'
    color_hex = color.lstrip("#")
    color_js = f'0x{color_hex}'

    script = f'''(function(){{
var uid="{uid}";
var host=document.querySelector('[data-uid="'+uid+'"]');
if(!host||!window.THREE)return;
if(host.__threeCleanup){{host.__threeCleanup();host.__threeCleanup=null;}}
var canvas=host.querySelector('canvas.three-canvas');
if(!canvas){{canvas=document.createElement('canvas');canvas.className='three-canvas';host.appendChild(canvas);}}
var w=host.clientWidth||240,h=host.clientHeight||240;
var scene=new THREE.Scene();
var camera=new THREE.PerspectiveCamera(45,w/h,0.1,1000);
camera.position.set(0,5,10);
camera.lookAt(0,0,0);
var renderer=new THREE.WebGLRenderer({{canvas:canvas,antialias:true,alpha:{bg_alpha}}});
renderer.setPixelRatio(Math.min(window.devicePixelRatio||1,2));
renderer.setSize(w,h,false);
{bg_clear}
var SEPARATION=0.3, AMOUNTX=30, AMOUNTY=30;
var numParticles=AMOUNTX*AMOUNTY;
var positions=new Float32Array(numParticles*3);
var i=0;
for(var ix=0;ix<AMOUNTX;ix++){{
  for(var iy=0;iy<AMOUNTY;iy++){{
    positions[i]=ix*SEPARATION-((AMOUNTX*SEPARATION)/2);
    positions[i+1]=0;
    positions[i+2]=iy*SEPARATION-((AMOUNTY*SEPARATION)/2);
    i+=3;
  }}
}}
var geo=new THREE.BufferGeometry();
geo.setAttribute('position',new THREE.BufferAttribute(positions,3));
var mat=new THREE.PointsMaterial({{color:{color_js},size:0.08,transparent:true,opacity:0.8}});
var points=new THREE.Points(geo,mat);
scene.add(points);
var autoRotate={auto_rotate},rotateSpeed={rotate_speed},animId=null;
var floating={floating},floatOffset=0;
var count=0;
var isPaused=false,lastFrameTime=performance.now();
var FRAME_MIN=1000/60;
function animate(now){{
animId=requestAnimationFrame(animate);
if(isPaused||document.hidden){{lastFrameTime=now;return;}}
var elapsed=now-lastFrameTime;
if(elapsed<FRAME_MIN)return;
lastFrameTime=now-(elapsed%FRAME_MIN);
var dt=Math.min(elapsed/1000,0.1);
var timeScale=dt*60;
var positions=geo.attributes.position.array;
var i=0;
for(var ix=0;ix<AMOUNTX;ix++){{
  for(var iy=0;iy<AMOUNTY;iy++){{
    positions[i+1]=(Math.sin((ix+count)*0.5)*0.5)+(Math.sin((iy+count)*0.5)*0.5);
    i+=3;
  }}
}}
geo.attributes.position.needsUpdate=true;
count+=0.05*timeScale;
if(autoRotate){{points.rotation.y+=rotateSpeed*0.5*timeScale;}}
if(floating){{floatOffset+=0.025*timeScale;points.position.y=Math.sin(floatOffset)*0.2;}}
renderer.render(scene,camera);
}}
requestAnimationFrame(animate);
function onResize(){{
var rect=host.getBoundingClientRect();
var nw=Math.max(1,Math.round(rect.width));
var nh=Math.max(1,Math.round(rect.height));
var maxSize=1024;
var r=Math.min(1,maxSize/Math.max(nw,nh));
nw=Math.round(nw*r);nh=Math.round(nh*r);
if(nw!==w||nh!==h){{w=nw;h=nh;camera.aspect=w/h;camera.updateProjectionMatrix();renderer.setPixelRatio(Math.min(window.devicePixelRatio||1,2));renderer.setSize(w,h,false);}}
}}
host.__threeResize=onResize;
host.__threePause=function(){{
if(!isPaused){{isPaused=true;if(animId){{cancelAnimationFrame(animId);animId=null;}}}}
}};
host.__threeResume=function(){{
if(isPaused){{isPaused=false;lastFrameTime=performance.now();if(!animId){{animId=requestAnimationFrame(animate);}}}}
}};
host.__threeCleanup=function(){{
if(animId){{cancelAnimationFrame(animId);animId=null;}}
try{{geo.dispose();mat.dispose();renderer.dispose();}}catch(e){{}}
host.__threeResize=null;host.__threePause=null;host.__threeResume=null;
}};
}})();'''

    return ('<div class="three-host" data-uid="' + uid +
            '" style="width:100%;height:100%;position:relative;overflow:hidden;">'
            '<canvas class="three-canvas"></canvas></div>' +
            '<scr' + 'i' + 'pt>' + script + '</scr' + 'i' + 'pt>')


def _generate_network_code(uid: str, color: str, auto_rotate: str, rotate_speed: float, background: str, floating: str) -> str:
    bg_alpha = "true" if background == "transparent" else "false"
    bg_clear = "renderer.setClearColor(0x000000, 0);" if background == "transparent" else f'renderer.setClearColor(new THREE.Color("{background}"), 1);'
    color_hex = color.lstrip("#")
    color_js = f'0x{color_hex}'

    script = f'''(function(){{
var uid="{uid}";
var host=document.querySelector('[data-uid="'+uid+'"]');
if(!host||!window.THREE)return;
if(host.__threeCleanup){{host.__threeCleanup();host.__threeCleanup=null;}}
var canvas=host.querySelector('canvas.three-canvas');
if(!canvas){{canvas=document.createElement('canvas');canvas.className='three-canvas';host.appendChild(canvas);}}
var w=host.clientWidth||240,h=host.clientHeight||240;
var scene=new THREE.Scene();
var camera=new THREE.PerspectiveCamera(50,w/h,0.1,1000);
camera.position.set(0,0,11);
var renderer=new THREE.WebGLRenderer({{canvas:canvas,antialias:true,alpha:{bg_alpha}}});
renderer.setPixelRatio(Math.min(window.devicePixelRatio||1,2));
renderer.setSize(w,h,false);
{bg_clear}
var group=new THREE.Group();
scene.add(group);
var particles=100;
var geometry=new THREE.BufferGeometry();
var positions=new Float32Array(particles*3);
var velocities=[];
for(var i=0;i<particles;i++){{
  positions[i*3]=(Math.random()-0.5)*6.4;
  positions[i*3+1]=(Math.random()-0.5)*6.4;
  positions[i*3+2]=(Math.random()-0.5)*6.4;
  velocities.push({{
    x:(Math.random()-0.5)*0.02,
    y:(Math.random()-0.5)*0.02,
    z:(Math.random()-0.5)*0.02
  }});
}}
geometry.setAttribute('position',new THREE.BufferAttribute(positions,3));
var pMaterial=new THREE.PointsMaterial({{color:{color_js},size:0.08,transparent:true,opacity:0.8}});
var particleSystem=new THREE.Points(geometry,pMaterial);
group.add(particleSystem);
var lineGeometry=new THREE.BufferGeometry();
var linePositions=new Float32Array(particles*particles*3);
lineGeometry.setAttribute('position',new THREE.BufferAttribute(linePositions,3));
var lineMaterial=new THREE.LineBasicMaterial({{color:{color_js},transparent:true,opacity:0.2}});
var lines=new THREE.LineSegments(lineGeometry,lineMaterial);
group.add(lines);

// 自适应缩放：根据包围盒与相机视锥计算安全比例
(function(){{
  var box = new THREE.Box3().setFromObject(group);
  var center = new THREE.Vector3();
  box.getCenter(center);
  group.position.sub(center);
  var size = new THREE.Vector3();
  box.getSize(size);
  var halfZ = size.z * 0.5;
  var halfX = size.x * 0.5;
  var halfY = size.y * 0.5;
  var frontDist = camera.position.z - halfZ;
  if (frontDist > 0.01 && halfX > 0.001 && halfY > 0.001) {{
    var vFov = camera.fov * Math.PI / 180;
    var visibleHalfH = frontDist * Math.tan(vFov * 0.5);
    var visibleHalfW = visibleHalfH * camera.aspect;
    var scale = Math.min(1, Math.min(
      visibleHalfW * 0.85 / halfX,
      visibleHalfH * 0.85 / halfY
    ));
    if (scale > 0 && isFinite(scale)) {{
      group.scale.setScalar(scale);
    }}
  }}
}})();

var autoRotate={auto_rotate},rotateSpeed={rotate_speed},animId=null;
var floating={floating},floatOffset=0;
var isPaused=false,lastFrameTime=performance.now();
var FRAME_MIN=1000/60;
function animate(now){{
animId=requestAnimationFrame(animate);
if(isPaused||document.hidden){{lastFrameTime=now;return;}}
var elapsed=now-lastFrameTime;
if(elapsed<FRAME_MIN)return;
lastFrameTime=now-(elapsed%FRAME_MIN);
var dt=Math.min(elapsed/1000,0.1);
var timeScale=dt*60;
var vertexpos=0;
var pos=geometry.attributes.position.array;
for(var i=0;i<particles;i++){{
  pos[i*3]+=velocities[i].x*timeScale;
  pos[i*3+1]+=velocities[i].y*timeScale;
  pos[i*3+2]+=velocities[i].z*timeScale;
  if(pos[i*3]<-3.2||pos[i*3]>3.2) velocities[i].x*=-1;
  if(pos[i*3+1]<-3.2||pos[i*3+1]>3.2) velocities[i].y*=-1;
  if(pos[i*3+2]<-3.2||pos[i*3+2]>3.2) velocities[i].z*=-1;
}}
geometry.attributes.position.needsUpdate=true;

var numConnected=0;
for(var i=0;i<particles;i++){{
  for(var j=i+1;j<particles;j++){{
    var dx=pos[i*3]-pos[j*3];
    var dy=pos[i*3+1]-pos[j*3+1];
    var dz=pos[i*3+2]-pos[j*3+2];
    var dist=Math.sqrt(dx*dx+dy*dy+dz*dz);
    if(dist<1.2){{
      linePositions[vertexpos++]=pos[i*3];
      linePositions[vertexpos++]=pos[i*3+1];
      linePositions[vertexpos++]=pos[i*3+2];
      linePositions[vertexpos++]=pos[j*3];
      linePositions[vertexpos++]=pos[j*3+1];
      linePositions[vertexpos++]=pos[j*3+2];
      numConnected++;
    }}
  }}
}}
lines.geometry.setDrawRange(0,numConnected*2);
lines.geometry.attributes.position.needsUpdate=true;

if(autoRotate){{group.rotation.y+=rotateSpeed*timeScale;group.rotation.x+=rotateSpeed*0.3*timeScale;}}
if(floating){{floatOffset+=0.025*timeScale;group.position.y=Math.sin(floatOffset)*0.2;}}
renderer.render(scene,camera);
}}
requestAnimationFrame(animate);
function onResize(){{
var rect=host.getBoundingClientRect();
var nw=Math.max(1,Math.round(rect.width));
var nh=Math.max(1,Math.round(rect.height));
var maxSize=1024;
var r=Math.min(1,maxSize/Math.max(nw,nh));
nw=Math.round(nw*r);nh=Math.round(nh*r);
if(nw!==w||nh!==h){{w=nw;h=nh;camera.aspect=w/h;camera.updateProjectionMatrix();renderer.setPixelRatio(Math.min(window.devicePixelRatio||1,2));renderer.setSize(w,h,false);}}
}}
host.__threeResize=onResize;
host.__threePause=function(){{
if(!isPaused){{isPaused=true;if(animId){{cancelAnimationFrame(animId);animId=null;}}}}
}};
host.__threeResume=function(){{
if(isPaused){{isPaused=false;lastFrameTime=performance.now();if(!animId){{animId=requestAnimationFrame(animate);}}}}
}};
host.__threeCleanup=function(){{
if(animId){{cancelAnimationFrame(animId);animId=null;}}
try{{
  geometry.dispose();
  lineGeometry.dispose();
  pMaterial.dispose();
  lineMaterial.dispose();
  renderer.dispose();
}}catch(e){{}}
host.__threeResize=null;host.__threePause=null;host.__threeResume=null;
}};
}})();'''

    return ('<div class="three-host" data-uid="' + uid +
            '" style="width:100%;height:100%;position:relative;overflow:hidden;">'
            '<canvas class="three-canvas"></canvas></div>' +
            '<scr' + 'i' + 'pt>' + script + '</scr' + 'i' + 'pt>')


def _generate_dna_code(uid: str, color: str, auto_rotate: str, rotate_speed: float, background: str, floating: str, neon_light: str) -> str:
    bg_alpha = "true" if background == "transparent" else "false"
    bg_clear = "renderer.setClearColor(0x000000, 0);" if background == "transparent" else f'renderer.setClearColor(new THREE.Color("{background}"), 1);'
    color_hex = color.lstrip("#")
    color_js = f'0x{color_hex}'

    script = f'''(function(){{
var uid="{uid}";
var host=document.querySelector('[data-uid="'+uid+'"]');
if(!host||!window.THREE)return;
if(host.__threeCleanup){{host.__threeCleanup();host.__threeCleanup=null;}}
var canvas=host.querySelector('canvas.three-canvas');
if(!canvas){{canvas=document.createElement('canvas');canvas.className='three-canvas';host.appendChild(canvas);}}
var w=host.clientWidth||240,h=host.clientHeight||240;
var scene=new THREE.Scene();
var camera=new THREE.PerspectiveCamera(50,w/h,0.1,1000);
camera.position.set(0,0,5.5);
var renderer=new THREE.WebGLRenderer({{canvas:canvas,antialias:true,alpha:{bg_alpha}}});
renderer.setPixelRatio(Math.min(window.devicePixelRatio||1,2));
renderer.setSize(w,h,false);
{bg_clear}

if ({neon_light}) {{
  scene.add(new THREE.AmbientLight(0xffffff,0.3));
  var d1=new THREE.DirectionalLight(0xffffff,0.5);d1.position.set(2,3,4);scene.add(d1);
  var p1=new THREE.PointLight(0x00f3ff,1.5,12);p1.position.set(-3,3,2);scene.add(p1);
  var p2=new THREE.PointLight(0xff00a0,1.5,12);p2.position.set(3,-3,2);scene.add(p2);
}} else {{
  scene.add(new THREE.AmbientLight(0xffffff,0.5));
  var d1=new THREE.DirectionalLight(0xffffff,0.8);d1.position.set(2,3,4);scene.add(d1);
  var d2=new THREE.DirectionalLight(0xffffff,0.3);d2.position.set(-2,-1,-3);scene.add(d2);
}}

var group=new THREE.Group();
scene.add(group);

var count=24;
var sphereGeom=new THREE.SphereGeometry(0.12,16,16);
var sphereMat=new THREE.MeshStandardMaterial({{color:{color_js},metalness:0.3,roughness:0.4}});
var lineMat=new THREE.MeshStandardMaterial({{color:{color_js},metalness:0.8,roughness:0.2}});

var nodes=[];
var cylinders=[];

for(var i=0;i<count;i++){{
  var t=(i/count)*Math.PI*4;
  var y=(i/count)*3.2-1.6;
  var x1=Math.cos(t)*0.85;
  var z1=Math.sin(t)*0.85;
  var x2=Math.cos(t+Math.PI)*0.85;
  var z2=Math.sin(t+Math.PI)*0.85;

  var m1=new THREE.Mesh(sphereGeom,sphereMat);
  m1.position.set(x1,y,z1);
  group.add(m1);
  nodes.push(m1);

  var m2=new THREE.Mesh(sphereGeom,sphereMat);
  m2.position.set(x2,y,z2);
  group.add(m2);
  nodes.push(m2);

  if(i%2===0){{
    var dx=x2-x1;
    var dy=0;
    var dz=z2-z1;
    var len=Math.sqrt(dx*dx+dy*dy+dz*dz);
    var cylGeom=new THREE.CylinderGeometry(0.025,0.025,len,8);
    var cyl=new THREE.Mesh(cylGeom,lineMat);
    cyl.position.set((x1+x2)/2,y,(z1+z2)/2);
    var vFrom=new THREE.Vector3(0,1,0);
    var vTo=new THREE.Vector3(dx,dy,dz).normalize();
    cyl.quaternion.setFromUnitVectors(vFrom,vTo);
    group.add(cyl);
    cylinders.push(cyl);
  }}
}}

var autoRotate={auto_rotate},rotateSpeed={rotate_speed},animId=null;
var floating={floating},floatOffset=0;
var isPaused=false,lastFrameTime=performance.now();
var FRAME_MIN=1000/60;

function animate(now){{
  animId=requestAnimationFrame(animate);
  if(isPaused||document.hidden){{lastFrameTime=now;return;}}
  var elapsed=now-lastFrameTime;
  if(elapsed<FRAME_MIN)return;
  lastFrameTime=now-(elapsed%FRAME_MIN);
  var dt=Math.min(elapsed/1000,0.1);
  var timeScale=dt*60;

  if(autoRotate){{
    group.rotation.y+=rotateSpeed*timeScale;
  }}
  if(floating){{
    floatOffset+=0.025*timeScale;
    group.position.y=Math.sin(floatOffset)*0.2;
  }}
  renderer.render(scene,camera);
}}
requestAnimationFrame(animate);

function onResize(){{
  var rect=host.getBoundingClientRect();
  var nw=Math.max(1,Math.round(rect.width));
  var nh=Math.max(1,Math.round(rect.height));
  var maxSize=1024;
  var r=Math.min(1,maxSize/Math.max(nw,nh));
  nw=Math.round(nw*r);nh=Math.round(nh*r);
  if(nw!==w||nh!==h){{w=nw;h=nh;camera.aspect=w/h;camera.updateProjectionMatrix();renderer.setPixelRatio(Math.min(window.devicePixelRatio||1,2));renderer.setSize(w,h,false);}}
}}

host.__threeResize=onResize;
host.__threePause=function(){{
  if(!isPaused){{isPaused=true;if(animId){{cancelAnimationFrame(animId);animId=null;}}}}
}};
host.__threeResume=function(){{
  if(isPaused){{isPaused=false;lastFrameTime=performance.now();if(!animId){{animId=requestAnimationFrame(animate);}}}}
}};
host.__threeCleanup=function(){{
  if(animId){{cancelAnimationFrame(animId);animId=null;}}
  try{{
    sphereGeom.dispose();
    sphereMat.dispose();
    lineMat.dispose();
    cylinders.forEach(function(c){{c.geometry.dispose();}});
    renderer.dispose();
  }}catch(e){{}}
  host.__threeResize=null;host.__threePause=null;host.__threeResume=null;
}};
}})();'''

    return ('<div class="three-host" data-uid="' + uid +
            '" style="width:100%;height:100%;position:relative;overflow:hidden;">'
            '<canvas class="three-canvas"></canvas></div>' +
            '<scr' + 'i' + 'pt>' + script + '</scr' + 'i' + 'pt>')


def _generate_globe_code(uid: str, color: str, auto_rotate: str, rotate_speed: float, background: str, floating: str, neon_light: str) -> str:
    bg_alpha = "true" if background == "transparent" else "false"
    bg_clear = "renderer.setClearColor(0x000000, 0);" if background == "transparent" else f'renderer.setClearColor(new THREE.Color("{background}"), 1);'
    color_hex = color.lstrip("#")
    color_js = f'0x{color_hex}'

    script = f'''(function(){{
var uid="{uid}";
var host=document.querySelector('[data-uid="'+uid+'"]');
if(!host||!window.THREE)return;
if(host.__threeCleanup){{host.__threeCleanup();host.__threeCleanup=null;}}
var canvas=host.querySelector('canvas.three-canvas');
if(!canvas){{canvas=document.createElement('canvas');canvas.className='three-canvas';host.appendChild(canvas);}}
var w=host.clientWidth||240,h=host.clientHeight||240;
var scene=new THREE.Scene();
var camera=new THREE.PerspectiveCamera(50,w/h,0.1,1000);
camera.position.set(0,0,5);

var renderer=new THREE.WebGLRenderer({{canvas:canvas,antialias:true,alpha:{bg_alpha}}});
renderer.setPixelRatio(Math.min(window.devicePixelRatio||1,2));
renderer.setSize(w,h,false);
{bg_clear}

if ({neon_light}) {{
  scene.add(new THREE.AmbientLight(0xffffff,0.3));
  var d1=new THREE.DirectionalLight(0xffffff,0.5);d1.position.set(2,3,4);scene.add(d1);
  var p1=new THREE.PointLight(0x00f3ff,1.5,12);p1.position.set(-3,3,2);scene.add(p1);
  var p2=new THREE.PointLight(0xff00a0,1.5,12);p2.position.set(3,-3,2);scene.add(p2);
}} else {{
  scene.add(new THREE.AmbientLight(0xffffff,0.5));
  var d1=new THREE.DirectionalLight(0xffffff,0.8);d1.position.set(2,3,4);scene.add(d1);
  var d2=new THREE.DirectionalLight(0xffffff,0.3);d2.position.set(-2,-1,-3);scene.add(d2);
}}

var group=new THREE.Group();
scene.add(group);

// 1. Earth wireframe
var earthGeo=new THREE.SphereGeometry(1.0,18,18);
var earthMat=new THREE.MeshStandardMaterial({{
  color:{color_js},
  wireframe:true,
  transparent:true,
  opacity:0.35,
  metalness:0.1,
  roughness:0.9
}});
var earth=new THREE.Mesh(earthGeo,earthMat);
group.add(earth);

// 2. Inner glow-like solid sphere
var coreGeo=new THREE.SphereGeometry(0.95,16,16);
var coreMat=new THREE.MeshStandardMaterial({{
  color:{color_js},
  transparent:true,
  opacity:0.1,
  roughness:0.8
}});
var core=new THREE.Mesh(coreGeo,coreMat);
group.add(core);

// 3. Floating orbit rings
var ring1Geo=new THREE.TorusGeometry(1.35,0.015,8,64);
var ringMat=new THREE.MeshBasicMaterial({{color:{color_js},transparent:true,opacity:0.55}});
var ring1=new THREE.Mesh(ring1Geo,ringMat);
ring1.rotation.x=Math.PI/2.5;
ring1.rotation.y=Math.PI/8;
group.add(ring1);

var ring2Geo=new THREE.TorusGeometry(1.5,0.012,8,64);
var ring2Mat=new THREE.MeshBasicMaterial({{color:{color_js},transparent:true,opacity:0.3}});
var ring2=new THREE.Mesh(ring2Geo,ring2Mat);
ring2.rotation.x=-Math.PI/3;
ring2.rotation.y=-Math.PI/6;
group.add(ring2);

// 4. Satellite (little sphere traveling around ring1)
var satGeo=new THREE.SphereGeometry(0.06,8,8);
var satMat=new THREE.MeshBasicMaterial({{color:0xffffff}});
var sat=new THREE.Mesh(satGeo,satMat);
group.add(sat);

var autoRotate={auto_rotate},rotateSpeed={rotate_speed},animId=null;
var floating={floating},floatOffset=0;
var satAngle=0;
var isPaused=false,lastFrameTime=performance.now();
var FRAME_MIN=1000/60;

function animate(now){{
  animId=requestAnimationFrame(animate);
  if(isPaused||document.hidden){{lastFrameTime=now;return;}}
  var elapsed=now-lastFrameTime;
  if(elapsed<FRAME_MIN)return;
  lastFrameTime=now-(elapsed%FRAME_MIN);
  var dt=Math.min(elapsed/1000,0.1);
  var timeScale=dt*60;

  if(autoRotate){{
    earth.rotation.y+=rotateSpeed*timeScale;
    earth.rotation.x+=rotateSpeed*0.3*timeScale;
    ring1.rotation.z+=rotateSpeed*0.5*timeScale;
    ring2.rotation.z-=rotateSpeed*0.4*timeScale;
  }}
  
  satAngle+=rotateSpeed*2*timeScale;
  var localX = Math.cos(satAngle)*1.35;
  var localY = Math.sin(satAngle)*1.35;
  var pos = new THREE.Vector3(localX, localY, 0);
  pos.applyEuler(ring1.rotation);
  sat.position.copy(pos);

  if(floating){{
    floatOffset+=0.025*timeScale;
    group.position.y=Math.sin(floatOffset)*0.2;
  }}
  renderer.render(scene,camera);
}}
requestAnimationFrame(animate);

function onResize(){{
  var rect=host.getBoundingClientRect();
  var nw=Math.max(1,Math.round(rect.width));
  var nh=Math.max(1,Math.round(rect.height));
  var maxSize=1024;
  var r=Math.min(1,maxSize/Math.max(nw,nh));
  nw=Math.round(nw*r);nh=Math.round(nh*r);
  if(nw!==w||nh!==h){{w=nw;h=nh;camera.aspect=w/h;camera.updateProjectionMatrix();renderer.setPixelRatio(Math.min(window.devicePixelRatio||1,2));renderer.setSize(w,h,false);}}
}}

host.__threeResize=onResize;
host.__threePause=function(){{
  if(!isPaused){{isPaused=true;if(animId){{cancelAnimationFrame(animId);animId=null;}}}}
}};
host.__threeResume=function(){{
  if(isPaused){{isPaused=false;lastFrameTime=performance.now();if(!animId){{animId=requestAnimationFrame(animate);}}}}
}};
host.__threeCleanup=function(){{
  if(animId){{cancelAnimationFrame(animId);animId=null;}}
  try{{
    earthGeo.dispose();
    earthMat.dispose();
    coreGeo.dispose();
    coreMat.dispose();
    ring1Geo.dispose();
    ring2Geo.dispose();
    ringMat.dispose();
    ring2Mat.dispose();
    satGeo.dispose();
    satMat.dispose();
    renderer.dispose();
  }}catch(e){{}}
  host.__threeResize=null;host.__threePause=null;host.__threeResume=null;
}};
}})();'''

    return ('<div class="three-host" data-uid="' + uid +
            '" style="width:100%;height:100%;position:relative;overflow:hidden;">'
            '<canvas class="three-canvas"></canvas></div>' +
            '<scr' + 'i' + 'pt>' + script + '</scr' + 'i' + 'pt>')


def build_3d_element(
    geometry: str = "cube",
    color: str = "#C5E803",
    auto_rotate: bool = True,
    rotate_speed: float = 0.01,
    metalness: float = 0.1,
    roughness: float = 0.85,
    wireframe: bool = False,
    background: str = "transparent",
    width: int = 240,
    height: int = 240,
    uid: str | None = None,
    custom_code: str | None = None,
    floating: bool = True,
    neon_light: bool = False,
) -> dict[str, Any]:
    """构造一个 3D 元素 dict（type='html' + meta.role='3d'）。

    Args:
        custom_code: 自定义 Three.js 代码，若提供则直接作为 html（跳过模板生成）

    Returns:
        元素字典，可直接 POST 到 /api/slides/<slide_id>/elements
    """
    if uid is None:
        uid = _gen_uid()

    data = {
        "geometry": geometry,
        "color": color,
        "autoRotate": auto_rotate,
        "rotateSpeed": rotate_speed,
        "metalness": metalness,
        "roughness": roughness,
        "wireframe": wireframe,
        "background": background,
        "floating": floating,
        "neonLight": neon_light,
    }

    if custom_code:
        html = custom_code
    else:
        if geometry == "custom":
            raise ValueError("geometry='custom' 时必须提供 custom_code 参数")
        html = generate_three_js_code(data, uid)

    return {
        "type": "html",
        "html": html,
        "css": THREE_CSS,
        "meta": {
            "role": "3d",
            "component": geometry if geometry != "custom" else "custom",
            "data": data,
            "uid": uid,
        },
    }


def get_preset_list() -> list[dict[str, Any]]:
    """返回预设列表（供 API 返回）。"""
    return [
        {"name": k, "label": v["label"], "icon": v["icon"], "geometry": v["geometry"]}
        for k, v in PRESETS.items()
    ]
