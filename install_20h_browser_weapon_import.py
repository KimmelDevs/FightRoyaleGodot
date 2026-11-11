#!/usr/bin/env python3
"""Fight Royale Godot — Patch 20H: match UI + REAL browser Three.js weapon mesh import.

Usage from the folder containing project.godot (CMD or PowerShell):
    python install_20h_browser_weapon_import.py

This reads the ACTUAL browser src/game/model.ts and roster.ts, runs their existing
Three.js procedural weapon builders in Node, exports the resulting triangles
into glTF binary (.glb), and mounts them on Godot's current hand grips.
It does NOT synthesize replacement weapons in Godot.

Requires Node.js, npm, Git and network only if a local browser source or required
node_modules are absent. No ZIP. Existing Godot project stays untouched if export fails.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import struct
import subprocess
import sys
import tempfile
from datetime import datetime
from pathlib import Path

REPO = 'https://github.com/KimmelDevs/Fight-Royale.git'
JS_EXPORTER = r'''"use strict";
const fs = require('fs');
const path = require('path');
const ts = require('typescript');
const THREE = require('three');
const gameDir = process.argv[2];
const output = process.argv[3];
const tmpDir = path.join(__dirname, 'compiled');
fs.mkdirSync(tmpDir, {recursive: true});
for (const base of ['mat', 'meshgen', 'roster', 'model']) {
  const original = fs.readFileSync(path.join(gameDir, base + '.ts'), 'utf8');
  let source = original;
  if (base === 'model') {
    // VRM body import is irrelevant to geometry export; don't load a model or DOM.
    const vrmImport = 'import { loadVrm, VrmRig } from "./vrm";';
    if(!source.includes(vrmImport)) throw new Error('Unexpected VRM import in model.ts; original source changed.');
    source = source.replace(vrmImport, 'const loadVrm = async () => null;');
    const needle = 'this.traverse((o) => { if ((o as THREE.Mesh).isMesh && !before.has(o)) weapons.add(o); });';
    if (!source.includes(needle)) throw new Error('Cannot identify original browser weapon meshes in model.ts; source format changed.');
    source = source.replace(needle, needle + '\n    this.userData.__browserWeaponList = Array.from(weapons);');

  }
  const result = ts.transpileModule(source, {fileName: base + '.ts', compilerOptions: {
    target: ts.ScriptTarget.ES2022, module: ts.ModuleKind.CommonJS,
    esModuleInterop: true, skipLibCheck: true
  }});
  fs.writeFileSync(path.join(tmpDir, base + '.js'), result.outputText);
}
const { CHARACTERS } = require(path.join(tmpDir, 'roster.js'));
const { FighterModel } = require(path.join(tmpDir, 'model.js'));
const out = {};
for (const fighter of CHARACTERS) {
  const model = new FighterModel({...fighter.look, vrm: ''});
  const list = model.userData.__browserWeaponList;
  if (!Array.isArray(list)) throw new Error('Browser weapon extraction hook failed for ' + fighter.id);
  model.updateMatrixWorld(true);
  const groups = {right: [], left: []};
  const sideOf = (obj) => {
    for(let par=obj; par; par=par.parent) {
      if(par === model.hand_r) return 'right';
      if(par === model.hand_l) return 'left';
    }
    return 'right'; // Detached floating weapons use right-hand rest-pose coordinates.
  };
  let count = 0;
  for(const item of list) {
    if (!item.isMesh || item.userData.outline || !item.geometry) continue;
    const side = sideOf(item);
    const hand = side === 'left' ? model.hand_l : model.hand_r;
    if (!hand) continue;
    const relative = new THREE.Matrix4().copy(hand.matrixWorld).invert().multiply(item.matrixWorld);
    const normalTransform = new THREE.Matrix3().getNormalMatrix(relative);
    const vertices = item.geometry.getAttribute('position');
    if (!vertices) continue;
    const normals = item.geometry.getAttribute('normal');
    const positions = [], ns = [];
    const v = new THREE.Vector3();
    const n = new THREE.Vector3();
    for(let i=0;i<vertices.count;i++) {
      v.set(vertices.getX(i),vertices.getY(i),vertices.getZ(i)).applyMatrix4(relative);
      positions.push(v.x,v.y,v.z);
      if(normals) n.set(normals.getX(i),normals.getY(i),normals.getZ(i)).applyMatrix3(normalTransform).normalize();
      else n.set(0,1,0);
      ns.push(n.x,n.y,n.z);
    }
    const indices = item.geometry.index ? Array.from(item.geometry.index.array) : Array.from({length:vertices.count},(_,i)=>i);
    const mat = Array.isArray(item.material) ? item.material[0] : item.material;
    const color = mat?.uniforms?.albedo?.value || mat?.uniforms?.color?.value || mat?.color || new THREE.Color('#ccd5e6');
    const emission = mat?.uniforms?.emission?.value || mat?.emissive || null;
    const col = [Number(color.r)||0,Number(color.g)||0,Number(color.b)||0].map(x=>Math.max(0,Math.min(1,x)));
    const em = emission ? [emission.r||0,emission.g||0,emission.b||0].map(x=>Math.max(0,Math.min(1,x))) : [0,0,0];
    groups[side].push({positions, normals: ns, indices, color: col, emission: em});
    count++;
  }
  if(count) {out[fighter.id] = groups; console.log(fighter.id + ': ' + count + ' original browser weapon meshes');}
}
fs.writeFileSync(output, JSON.stringify(out));
console.log('SOURCE_EXPORT_SUCCESS: ' + Object.keys(out).length + ' fighters');
'''


def run(args, **kwargs):
    print('$', ' '.join(map(str, args)), flush=True)
    subprocess.run(args, check=True, **kwargs)


def find_browser_project(project: Path, explicit: str | None, allow_clone: bool) -> Path:
    candidates: list[Path] = []
    if explicit:
        candidates += [Path(explicit).expanduser()]
    for root in [project.parent, project.parent.parent, Path.home() / 'OneDrive' / 'Documents', Path.home() / 'Documents']:
        for name in ['fight-royale', 'Fight-Royale', 'Fight-Royale-main', 'Fight Royale']:
            candidates += [root / name / 'web', root / name]
    for candidate in candidates:
        web = candidate / 'web' if (candidate / 'web' / 'src' / 'game' / 'model.ts').is_file() else candidate
        if (web / 'src' / 'game' / 'model.ts').is_file() and (web / 'src' / 'game' / 'roster.ts').is_file():
            print('Browser source:', web.resolve())
            return web.resolve()
    if not allow_clone:
        raise RuntimeError('Browser source not found. Supply --browser-web PATH.')
    cached = project.parent / (project.name + '_web_weapon_source_cache')
    if not (cached / 'web' / 'src' / 'game' / 'model.ts').is_file():
        if cached.exists():
            raise RuntimeError('Incomplete browser source cache at ' + str(cached) + '. Delete or rename it and rerun.')
        if not shutil.which('git'):
            raise RuntimeError('Git not installed and browser source was not found locally.')
        run([shutil.which('git') or 'git', 'clone', '--depth', '1', '--filter=blob:none', '--sparse', REPO, str(cached)])
        run([shutil.which('git') or 'git', '-C', str(cached), 'sparse-checkout', 'set', 'web/src/game'])
    return cached / 'web'


def node_dependencies(web: Path, project: Path) -> Path:
    if not shutil.which('node'):
        raise RuntimeError('Node.js is needed to execute the ORIGINAL browser Three.js weapon builders.')
    candidates = [web / 'node_modules', web.parent / 'node_modules', project.parent / (project.name + '_weapon_tools') / 'node_modules']
    for node_modules in candidates:
        if (node_modules / 'three' / 'package.json').is_file() and (node_modules / 'typescript' / 'package.json').is_file():
            return node_modules
    if not shutil.which('npm'):
        raise RuntimeError('npm is missing; cannot obtain Three.js and TypeScript runtime dependencies.')
    tools_dir = project.parent / (project.name + '_weapon_tools')
    tools_dir.mkdir(exist_ok=True)
    print('Installing minimal exporter dependencies (Three.js + TypeScript) OUTSIDE the Godot repo.')
    run([shutil.which('npm') or 'npm', 'install', '--no-save', '--no-audit', '--no-fund', '--ignore-scripts', '--prefix', str(tools_dir), 'three', 'typescript'])
    node_modules = tools_dir / 'node_modules'
    if not (node_modules / 'three' / 'package.json').is_file() or not (node_modules / 'typescript' / 'package.json').is_file():
        raise RuntimeError('Unable to load Node exporter dependencies.')
    return node_modules


def pad4(data: bytes, pad: bytes = b'\0') -> bytes:
    return data + pad * ((-len(data)) % 4)


def build_glb(shapes: list[dict], asset_id: str) -> bytes:
    buffer = bytearray()
    views, accessors, materials, primitives = [], [], [], []
    matcache = {}

    def view(data: bytes, target: int) -> int:
        buffer.extend(b'\0' * ((-len(buffer)) % 4))
        at = len(buffer)
        buffer.extend(data)
        views.append({'buffer': 0, 'byteOffset': at, 'byteLength': len(data), 'target': target})
        return len(views)-1

    def accessor(v: int, count: int, typ: str, comp: int, mn=None, mx=None) -> int:
        ac = {'bufferView': v, 'componentType': comp, 'count': count, 'type': typ}
        if mn is not None: ac['min'] = mn
        if mx is not None: ac['max'] = mx
        accessors.append(ac)
        return len(accessors) - 1

    for s in shapes:
        positions, normals, indices = s['positions'], s['normals'], s['indices']
        count = len(positions) // 3
        if count < 3 or len(normals) != len(positions) or not indices:
            continue
        if max(indices) >= count or min(indices) < 0 or len(indices) % 3:
            raise ValueError(f'Invalid triangle indices in {asset_id}')
        pos_bytes = struct.pack('<' + 'f'*len(positions), *positions)
        norm_bytes = struct.pack('<' + 'f'*len(normals), *normals)
        ix_bytes = struct.pack('<' + 'I'*len(indices), *indices)
        pos_view = view(pos_bytes, 34962)
        norm_view = view(norm_bytes, 34962)
        ix_view = view(ix_bytes, 34963)
        xyz = (positions[i::3] for i in range(3))
        bounds = [(min(a),max(a)) for a in xyz]
        ap = accessor(pos_view, count, 'VEC3', 5126, [p[0] for p in bounds], [p[1] for p in bounds])
        an = accessor(norm_view, count, 'VEC3', 5126)
        ai = accessor(ix_view, len(indices), 'SCALAR', 5125)
        color = tuple(round(float(n),5) for n in s['color'])
        emission = tuple(round(float(n),5) for n in s['emission'])
        key = color + emission
        if key not in matcache:
            materials.append({
                'name': 'Browser_original_%d'%len(materials),
                'pbrMetallicRoughness': {'baseColorFactor': [*color,1.0], 'metallicFactor':0.0,'roughnessFactor':0.65},
                'emissiveFactor': list(emission),
                'doubleSided': True,
            })
            matcache[key] = len(materials)-1
        primitives.append({'attributes': {'POSITION':ap,'NORMAL':an}, 'indices':ai, 'material':matcache[key], 'mode':4})
    if not primitives:
        raise ValueError(f'No triangles for {asset_id}')
    doc = {
        'asset': {'version': '2.0','generator':'Fight Royale browser-source weapons exporter'},
        'scene':0,'scenes':[{'nodes':[0]}],
        'nodes':[{'name':asset_id, 'mesh':0}],
        'meshes':[{'name':asset_id,'primitives':primitives}],
        'buffers':[{'byteLength':len(buffer)}],
        'bufferViews':views,'accessors':accessors,'materials':materials,
    }
    json_data = pad4(json.dumps(doc,ensure_ascii=False,separators=(',',':')).encode('utf-8'),b' ')
    bin_data = pad4(bytes(buffer))
    total = 12+8+len(json_data)+8+len(bin_data)
    return b''.join([struct.pack('<III',0x46546C67,2,total), struct.pack('<I4s',len(json_data),b'JSON'),json_data,struct.pack('<I4s',len(bin_data),b'BIN\0'),bin_data])


def patch_ui(text: str) -> str:
    marker = '_text(time_row, "Round limit:", 18)'
    fixed_marker = 'round_label.custom_minimum_size = Vector2(145, 36)'
    if fixed_marker in text:
        return text
    if text.count(marker) != 1:
        raise ValueError('Unable to locate unique Round limit label in scripts/main.gd')
    return text.replace('\t\t'+marker, '\t\tvar round_label := '+marker+'\n\t\tround_label.autowrap_mode = TextServer.AUTOWRAP_OFF\n\t\t'+fixed_marker, 1)


def patch_model(text: str) -> str:
    if 'func _install_browser_weapon_meshes()' in text:
        return text
    anchors = [
        ('var shield_node: Node3D', 'var shield_node: Node3D\nvar _browser_weapon_r: Node3D\nvar _browser_weapon_l: Node3D\nvar _browser_old_parts: Array[MeshInstance3D] = []'),
        ('\tmi.mesh = mesh\n', '\tmi.mesh = mesh\n\t_browser_old_parts.append(mi)\n'),
        ('\tvar l: Node3D = WeaponMount.configure_grip(_grip("Left"), mount_profile, "left")\n',
         '\tvar l: Node3D = WeaponMount.configure_grip(_grip("Left"), mount_profile, "left")\n\t_browser_weapon_r = r\n\t_browser_weapon_l = l\n'),
        ('\t_build_weapons()\n', '\t_build_weapons()\n\t_install_browser_weapon_meshes()\n'),
    ]
    for anchor, replace in anchors:
        if text.count(anchor) != 1:
            raise ValueError('Weapon attachment script changed: anchor missing or duplicate: '+repr(anchor))
        text = text.replace(anchor, replace, 1)
    text += '''\n\n# FRG20H - Original Three.js browser weapon meshes (GLB) on existing VRM hand grips.\n# Keep the gameplay anchors (blade_base, blade_tip, shield_node, cast_point) unchanged.\nfunc _install_browser_weapon_meshes() -> void:\n\tvar fid: String = character_id.strip_edges().to_lower()\n\tif fid.is_empty():\n\t\tfid = String(look.get("name", "")).to_lower()\n\tvar installed := false\n\tfor side in ["right", "left"]:\n\t\tvar grip: Node3D = _browser_weapon_r if side == "right" else _browser_weapon_l\n\t\tif not is_instance_valid(grip):\n\t\t\tcontinue\n\t\tvar path: String = "res://weapons/browser/%s_%s.glb" % [fid, side]\n\t\tif not ResourceLoader.exists(path):\n\t\t\tcontinue\n\t\tvar resource: Resource = ResourceLoader.load(path)\n\t\tif not (resource is PackedScene):\n\t\t\tcontinue\n\t\tvar instance: Node = (resource as PackedScene).instantiate()\n\t\tif not (instance is Node3D):\n\t\t\tif is_instance_valid(instance):\n\t\t\t\tinstance.queue_free()\n\t\t\tcontinue\n\t\tgrip.add_child(instance)\n\t\tinstalled = true\n\tif installed:\n\t\tfor old_mesh in _browser_old_parts:\n\t\t\tif is_instance_valid(old_mesh):\n\t\t\t\told_mesh.visible = false\n'''
    return text


def write_preserving(path: Path, content: str):
    original = path.read_bytes()
    bom = b'\xef\xbb\xbf' if original.startswith(b'\xef\xbb\xbf') else b''
    newline = '\r\n' if b'\r\n' in original else '\n'
    buf = content.replace('\r\n','\n').replace('\n',newline).encode('utf-8')
    path.write_bytes(bom+buf)


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--browser-web', help='Path to existing Fight-Royale/web directory')
    p.add_argument('--ui-only', action='store_true', help='Only fix Round limit layout; do not attempt 3D weapon conversion')
    args = p.parse_args()
    project = Path.cwd().resolve()
    print('FIGHT ROYALE — PATCH 20H: UI + BROWSER-SOURCE WEAPONS', flush=True)
    print('Godot project:', project)
    if not (project/'project.godot').is_file():
        print('ERROR: Run from the folder containing project.godot.');return 2
    main_path = project/'scripts'/'main.gd'
    model_path = project/'scripts'/'fighter_model.gd'
    if not main_path.is_file() or not model_path.is_file():
        print('ERROR: Missing scripts/main.gd or scripts/fighter_model.gd.'); return 2
    try:
        main_src = main_path.read_text(encoding='utf-8-sig')
        target_main = patch_ui(main_src)
        model_src = model_path.read_text(encoding='utf-8-sig')
        target_model = model_src if args.ui_only else patch_model(model_src)
        new_assets = {}
        if not args.ui_only:
            browser_web = find_browser_project(project,args.browser_web,True)
            packages = node_dependencies(browser_web,project)
            with tempfile.TemporaryDirectory(prefix='frg20h_', dir=project.parent) as scratch:
                root = Path(scratch)
                js = root/'export.cjs'; out = root/'weapons.json'
                js.write_text(JS_EXPORTER,encoding='utf-8')
                env = os.environ.copy()
                env['NODE_PATH'] = str(packages) + os.pathsep + env.get('NODE_PATH','')
                run(['node',str(js),str(browser_web/'src'/'game'),str(out)],cwd=root,env=env)
                raw = json.loads(out.read_text(encoding='utf-8'))
                # Export every original browser fighter, including alternate character skins;
                # installing them doesn't affect the current Godot roster.
                for fighter, sides in raw.items():
                    if not re.fullmatch('[a-z0-9_-]+',fighter):
                        continue
                    for side in ('right','left'):
                        if sides.get(side):
                            new_assets[f'{fighter}_{side}.glb'] = build_glb(sides[side],fighter+'_'+side)
                if not new_assets:
                    raise RuntimeError('No Three.js weapon geometry was extracted; no code changed.')
        if target_main==main_src and target_model==model_src and all((project/'weapons'/'browser'/key).exists() for key in new_assets):
            print('Already installed: no changes necessary.'); return 0
        backup = project.parent/(project.name+'_backups')/('patch_20h_'+datetime.now().strftime('%Y%m%d_%H%M%S_%f'))
        backup.mkdir(parents=True,exist_ok=False)
        files_changed=[]
        try:
            for path,new,old in ((main_path,target_main,main_src),(model_path,target_model,model_src)):
                if new!=old:
                    shutil.copy2(path,backup/path.name)
                    write_preserving(path,new)
                    files_changed.append(path)
                    print('Patched:',path.relative_to(project))
            directory=project/'weapons'/'browser'
            for name, data in new_assets.items():
                directory.mkdir(parents=True,exist_ok=True)
                target=directory/name
                if target.exists():
                    old=target.read_bytes()
                    if old==data: continue
                    (backup/'old_assets').mkdir(exist_ok=True)
                    shutil.copy2(target,backup/'old_assets'/name)
                target.write_bytes(data)
                if target.read_bytes()!=data: raise IOError('Failed to verify '+str(target))
                print('Imported browser mesh:',name,'(%d KB)'%(len(data)//1024))
            assert main_path.read_text(encoding='utf-8-sig')==target_main
            assert model_path.read_text(encoding='utf-8-sig')==target_model
        except Exception:
            for file in files_changed:
                candidate=backup/file.name
                if candidate.exists(): shutil.copy2(candidate,file)
            raise
        if args.ui_only:
            print('\nRESULT: SUCCESS — Round limit UI fixed (weapons unchanged).')
        else:
            print('\nRESULT: SUCCESS — UI fixed; original browser weapon mesh files exported:',len(new_assets))
        print('Backups:',backup)
        print('Open Godot 4.7 editor and allow .glb resources to import. Then run the game.')
        print('Note: static base geometry is copied; browser-only articulated weapon motion needs a separate animation port.')
        return 0
    except (OSError,ValueError,RuntimeError,subprocess.CalledProcessError,AssertionError) as exc:
        print('ERROR:',exc)
        print('No new code changes are made if source export or preflight fails.')
        print('If you only need the UI fix, run: python install_20h_browser_weapon_import.py --ui-only')
        return 2

if __name__=='__main__':
    sys.exit(main())
