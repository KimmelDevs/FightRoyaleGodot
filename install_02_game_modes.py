#!/usr/bin/env python3
# -*- coding: utf-8 -*-
r"""Fight Royale Godot | Update 02 - Two Modes, Free Roster, No Shop

Run from the Godot project directory:
    python install_02_game_modes.py

Optional:
    python install_02_game_modes.py --dry-run
    python install_02_game_modes.py --godot "C:\path\Godot.exe"
    python install_02_game_modes.py --restore "C:\...\modes_02_<timestamp>"

Python >= 3.9; no external dependencies. This is not a Godot engine installer.
Only patches scripts/main.gd, scripts/match.gd, scripts/hud.gd and creates
one data/modes_config.json. Backups are stored outside the Godot project.
"""
from __future__ import annotations
import argparse
import base64
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import uuid
import zlib

VERSION = "02.0"
KNOWN_LEGACY_MAIN_SHA = "96d4815d63750130c6aaa6525c0661bbbb6a467f97639fc8afa5d05fcdd3791e"
DEFAULT_PROJECT = Path(r"C:\Users\Admin\OneDrive\Documents\fight-royale-godot")
MAIN_B85 = (
    'c-p-h?QYx1@wfF9dprb?dI~GaPR^&m1!P%CjI$$Ga*|#Rf#AnVVndNSE-Bl0IN%<lK>zn8`oE8IPtuv$U2-YWmfb@e1QxlRotd4T?_GYE@i-9d'
    'LlW@D*I%=@=kMNMJCpGbgNu=KIX)Xroll(}`|a1ivm}o0*;&pbwh?T2^^v)8K)>?U#_5A7V)JmZ%y=r8n{qZ!IfrS2N8Ha`FXA?kVj@dY-e%lS'
    ';$(HtKAyK(#@&@*Ny<c?Zo-Wl*^LH#78xThSpS6m+&HiTpl|h=W$<COVccKm&PF)!gI`Oo;Nvfi#>P#VlZSmaOyVp}A~~>fGk@7<m-r(`mU+-;'
    '@AE*uty8`U`E8%Ql`Fag8R@C;h%8Bd<X8~S=b@iR**$*g%0YkWrjCmP9b>>VAl9M(#Sx*zr+}iw4U#-_+&&wmse8{(*p2m*)n?Wm{_(9@70%lO'
    'mvS$RgD_qgaI;2Zp2t3Zbc6e5i@p34+azJoZyac@PuR-63!7(d=Griy-#N*=d6g#f5cV;0MMi+FHtV$XBo8Jv_55#Gx5Zu<NYX@r9BmQ)#G5d!'
    'i_?m=!c0fF8y@H(jmL!Y9)j`!3fJnU3xSdxPwfQ<23J88#@xvT2Tbs-32@<@SubCLuDsj`{IOUV(?nSNf!tfzT0^C9SY&RRNu5C)Jd#*Q0V?x%'
    '00qZ!u}p5A6_0ZmRFW4ySVt^H|LHWjL+x~d+q6$ShQbNK0NmK;4j4ojG(m@3L?aLFA9J2_2ki@~zzFcH)Z32vts1li2mvrGlT@HW!)sGRT}?*Q'
    '(Y5pT<HdzD84a&th8qMR&M=asq(r?1%5#`RNjd=|*2uku?c*3z-<sCf-EQ}|_njp_K94Z6S`zmbiuMYm3bF<Im-JLfNOK_po=I#DT=QVTaocXJ'
    'h|e>$mK3cVAF^bPKVFh$$;z6cz!e$fFkA8!cgQulapoi&o~B^EO-sT!7N|WUZ?oRf&cY;&THFTLRoQpFs?Fn+1Yf(Un}taXe0F=K7)nAL7)*JV'
    'r!m`Tb<4sm;!T*!<E&2}zs*3ea^7dtECuh-W^>@gLG$c`Y%<u|qYi23h3oOCFWHXp8Cj=6%`%PJ8Nb6>gjJ7~ODV7$YbnMogL-RsF6r9#JQ{?F'
    'S^?*C-Z^%y7R;B+G$cX@OR3OnAsJx%nS$vaw;7S|OX`Lh1g`_m=fK79mRz1Cx2e0<F6kOzraT21*n^MP<Ij`9mGgN#Idi6$gUR*(QQq|XTp@c|'
    '{J4x=A5|LU=|&Nz3T<{91{p-?Ik<WhPVcB=OMN`e!8T(hR*zm#u5!5WQ1Y!RSvBbAkb|t8RTzh>d__V4m`~u}lC;+(x@~rJSYmm)RJ+GA#K`5?'
    ';Kil$CeN*~p^p+g01q0+K(i@f>m({Clp>YyMFgotLW<F(pd=&;^)i&0(H9uvt95oS8B%Ds(*_bOrD;K#GZdj;(Ic!FeSv+RO7bl`4CMOdY!&R;'
    'S10UnA3eZX5>wNId>w_pn^BZQ$NdGpHbMe2pb{sU9I9f3KO5<~AEXGA0nJTk#!gP?sXN2`vpUu*#=6GXV+&E^0H`*}2>fP_1!;GgBoyJG$O$M2'
    'MByTanW(;%Ffq6|fA`^X^x@hW!k^Iu&`IaM0WK(oXEKEcu3lq&kRA@dz8jy7ui5DA{Q7+Sfk9&bPsY0J(-i&;$CsyrYnalbd=BjuXH-&chD!p?'
    'VMUrm3D6rekA*b$ja;=%`!Ur!tl~5i^j(xj=Ji~}Q=VnuOa%KQ`<~xp)+>O5nj=5$%=vR3W(FIWHfEGoL5>xgL<%A9lsVh=%`#b|-uQV6=IlfL'
    'a}TDsve7#nmEp=g_Pz~z7_O8#LjscsPK#~gpVF4K)|kS;pT<E&9$SdEY;y-4n1G29<V)FQk^a*x9C;*3msVfqxn&)&GuwN3cHJr}V+PlC#$xFI'
    'kk+n?Ho@4x|HT+)WmHJske1D0Pme2GIwd;HWg<#4C`Xq(W<GeHFEFIG+6E)cmgUC#Zp@&rKv*W+6=#LGX`^2&yH1l^WcGbsq6go|K|1ruT|l7V'
    'X$H<NGE({J`CmuQ=r31;4`<HX^NR~P=NakYagk5TfCAGMV<5dGqI_gZPdnU6fIYGD=%}L&M8O*if`mN$3DG{jq}_?nl7w8CM55NV08!w|-ofwA'
    'y6__wFZn7Km{zEfM}@j{Dq{V%^^{4Q-AQVxCEJKag|-mm*lwYWR)uR)iq~gnA*Bm$igD6_zX@jwlo|}=;1GSg(BLRZzSuG7YJ1m5*yt^rVGI2~'
    '?k1I>=oE^2e%D<vw0hmtAVv>78w@OuAYvOSu};jDMIbj17C-cLkJ25!>d3Bx1b)88RaJ+uDCST)vSVZYF#c%KqGe#x!A>rkV%WekCXvvs@zvG%'
    '14QLLGf&k_lBZj27jXja=!NLB7XtoU>;=1#Jhj<Y!lnBo=C)eD{o_~b!JV?KS-TQu<feBp#&tU_gC*}NEO`&G<UNI@?xQSq3zq7Gl$6`!x~4;t'
    'T+n{K1SSNJ>+EYs=6h|S2uVtO61ORq!!oBRMXWM1C1f>;5EUpup)r1SUu{oU-vcgu^_jf<)_N2axT;KS)4xh?d5W9NrfbdvdYZWLg45F(pYvF7'
    '&782;2oBkmEf5+XQUu0_K*G+d3D0-);CMc#`kWL^Hdsm1)U)FycjyGv>+?eb`GeB36&@6orhv_%r|+V)?#+V{+zhP%r}Ij91bLpi{uiBoVg-QP'
    '(y4+V!Z6Oc1_Lg!1_a3OIz>8H5e{ZT)7<+61M4Ks%%&l^{^X8AdJRNT7$<kI|4^v-OAuz3Qe6yVdwg!MgFP+nB{mBC7O_Gu`n`%JY#w!re4&6z'
    'Ze!;*Nu$6y3<{2luNi2SkcF}1Eh-!v4KD?)O&LrqCAT`Hr^7SNnEV2|D?&7ig0;gY@YS`EIlEWF&65qb!FmQiB~b~ZNJcuUorNiv1{Yo6SV@~e'
    'z<@K#2%LZ~Ab%AG3oj2}fs9|t*j7U@G6EHkNh?32+(z*xOcSaVH7)pT^Kux7><6+vP}oJ9<XD@^V$7U$`py|%j0O{DIKCK9c4xaQFT_nEE*+8N'
    'slSb4aCv%;b?bEeaWWh|4bgU+nZKTQ(2MMw$3f*6=<+)Daji6As*>e0i30F^AWrN|l^Z6<$zfw*dL`}fJ&jtmIOPnZUz6NzTQNGI`g*L&3bu~t'
    '0H`o;QE!tOKx*fL!)h^CDAp-pDkR|0;yjAVc7@C{2_NQ~YI$@}f@3KbQwU9O+eZxAU7u7A#I{6boFMG_UhLE7>j(Nq7#dAjZ6>zd!oycZ)9XtZ'
    'Md+a+)_@JFpbesIv!ZBjQyo_;;B}Hv(NotjQvMz`=?lNtok<{%b5t~*>2s#E>{S`{F*d%oVo6c{8c{FFg@GQB-5|fZ4+f5~@K1gEOp4G{jLD>^'
    '0`=7id)cKE+3jJH18gbMFu%=kS&Eg$LBRoxDk`#xS7{8GZ2*{I6#Zt2PhZSnW}JA@)?vhjeXllyYx^B24N?!Xhcal_hwH|^GHF}qe$Q4`j#FwX'
    'EcOkv*c8``9jIPc6U#F2v7(MU^~nJfZEAE>8}92O>@<yKjgO{|dy1BRsEf#Cja20kDLqzu<_GHgo?M`NeB5S~3do);zkjp^tC1pyVa8WYRZLJG'
    '36t$Caq{&V_64$jB?cUyktAm(U#cHeM@rgAp~)?C8d6ogB%|$KbtSU!z%7^FgAh~;MTM@?p(>QT+E{zI<!+t?myUT)SBq{buqpb_M>|@iW3qZp'
    '@+VZUWd}^vcku7i6#r6{TI|x(s?WXEAh6jxR0V<k`ThCzsM3YI!iHP6g!MDp8o@v*%KqE+lCwFa71>gLW}(nGOx%qd(y0;462^bb!!<SGs7R`K'
    'osGJ#usztV%6o7Q7OF3FpaCB~!4NmKHW*e6&?u~v+cwzD$Q4My`jDh6H^Qg)ZW>s#o6snX%gZHYo2Gm8%52jZFi&m7{I0?V1+AN`Wse;#4Bg#U'
    'nKQi}Os?haB7imTNT6tSnO|tCd7THtOWCGfW1k&-5JT8Lq*rD~7F+S4wl95IA4Xu)Y$SZPc5}hS8#ZAnC!$<v?Wi`)OA$Vhp_#XQiVpV!vCg~)'
    '@>Jij&c)K<X^NXQbYnc-B0ONzgo)jT*%BfU3joC*6^g$J2=x#F(vS<w^eNRtre|I$QFlr(fovS?-1>R2GlB<z2D}WI;^txCStaUL5B#2n#@j*T'
    ')uX|)2YuWo3Qa<LtkXP|u0`%W=$3JF3Pkg>wdRn6_a(ebezrs?J#3Wt(wx!n>04=oT2OS=7|38T0H|csMijIh94iEb7gV^rg0apo?HyLUZGxw@'
    '1m(e7m7rHo&?^acks#!#Ql;35ygFChHlk76pJPV*vxO2xCMf6t4kbqzQcrCqB1iLIF!{JROAACc%eS_Pp<mAbrE;x_m_%-uIkp<!=K=9w8Ml>}'
    'DDs5zgp!7(WmB2lZ0R|8R_H(;gMq!6ScLlO-70`D+=OAGRVPtnt2mF0RT8XJXL3E#TI*-aCCWQ)w2mzddRGZY<p@q5oId9et~iIqo1>~-N4}|a'
    '<wJG4W*oTDwFnr(e3D!|9<Qk@6XeLTz?qPn$4g%61{}P3)FuyCWcB>$nU*?Rc}{0>vvbr$W&U#yn-2er!zQ}oRWM$AbR;j3V50FozZdpkh{yZW'
    'GIq*iAPIHT#kTCX+gVtpUg%K@QFoL?_~~K~-Ug*Nb-7gBDEyt-Or_xM;xbROJXeCuWc&V$<8iz@C-14s45z@=RvO~9{s-;Y*IRkY1n&-Fr`rXW'
    'B8*!Bv`~4ou=Qr!F4WTWMJHn|O?|0JUveti5^bf}eRXT8l4TSZb}`;a6msfp`&yG_*o<x4mS!T1*Ll|D8>+C+@nwY1+o%5pAtMh#)5FArCgZr;'
    'E%U+<%_acM!AtxgCNfe<*#@S3jI3HO@h;}%)94IINQm|FUZCwc4}rGSMV~4{2-V+@esD(9;oxdSx@s)NkGPvs3Ug4|C>!WR4jxUUDK2NL`tsGK'
    'ZX%B_sNh6aCQmq2dwZ&JP?$lpWP?=Kctxv26s<-ruh@js{lsRAZnV-KI<9b_J`Ezt@#70BI*o}BTh<IRb$M=oXwl6&av3!(xNlBakg-3oj(ybl'
    '4?;A=pa'
)

class InstallError(RuntimeError):
    pass

def new_main_bytes():
    return zlib.decompress(base64.b85decode("".join(MAIN_B85)))

def project_at(root):
    return all((root / x).exists() for x in ("scripts/main.gd", "scripts/match.gd", "scripts/hud.gd", "data/roster.json", "scenes/main.tscn"))

def choose_project(explicit):
    if explicit:
        root = Path(explicit).expanduser().resolve()
        if not project_at(root):
            raise InstallError("Project not found at " + str(root) + ". Expected scripts/main.gd and data/roster.json.")
        return root
    cwd = Path.cwd().resolve()
    if project_at(cwd):
        return cwd
    if project_at(DEFAULT_PROJECT):
        return DEFAULT_PROJECT
    raise InstallError("Project not found. Run from inside your Godot directory, or pass --project PATH.")

def replace_once(src, old, new, label):
    # Idempotency: a replacement can intentionally contain the old anchor.
    if new in src:
        return src
    if old in src:
        if src.count(old) != 1:
            raise InstallError(label + ": expected one matching code block; found multiple.")
        return src.replace(old, new)
    raise InstallError(label + ": source differs from the expected Godot ZIP. No files changed. Upload the current scripts for a compatible patch.")

def patch_match(txt):
    txt = replace_once(txt,
        'func _unhandled_input(e: InputEvent) -> void:\n\t_player_brain.on_event(e)',
        'func _unhandled_input(e: InputEvent) -> void:\n\tif not bool(cfg.get("spectator", false)):\n\t\t_player_brain.on_event(e)',
        'match input spectator guard')
    txt = replace_once(txt,
        """\t\t\tvar won: bool = winner.owner_peer == cfg.local_peer
\t\t\tif not String(winner.owner_peer).begins_with("cpu"): ui_event.emit({"type": "reward", "reason": "duel", "gold": int(Data.economy.win_gold), "peer": winner.owner_peer})
\t\t\tui_event.emit({"type": "over", "text": "VICTORY" if won else "DEFEAT", "sub": "Press R or click Rematch", "color": Color("#ffe08a") if won else Color("#ff7b7b")})""",
        """\t\t\tvar spectator_mode: bool = bool(cfg.get("spectator", false))
\t\t\tvar won: bool = winner.owner_peer == cfg.local_peer
\t\t\tvar result_text: String = ("%s WINS!" % winner.look.name) if spectator_mode else ("VICTORY" if won else "DEFEAT")
\t\t\tvar result_color: Color = Color("#ffe08a") if spectator_mode or won else Color("#ff7b7b")
\t\t\tui_event.emit({"type": "over", "text": result_text, "sub": "Press R or click Rematch", "color": result_color})""",
        'match duel result / no gold payout')
    txt = replace_once(txt,
        """\t\t\t\t\tif not String(x.owner_peer).begins_with("cpu"): ui_event.emit({"type": "reward", "reason": "team", "gold": int(Data.economy.win_gold), "peer": x.owner_peer})""",
        """\t\t\t\t\t# Legacy team mode no longer grants currency.""",
        'disable unused team reward')
    txt = replace_once(txt,
        """func hud() -> Dictionary:
\tvar me := local""",
        """func hud() -> Dictionary:
\t# The spectator has no local fighter; show CPU A/CPU B in the two HUD bars.
\tvar me: Fighter = local if local else (fighters[0] if not fighters.is_empty() else null)""",
        'CPU spectator HUD information')
    return txt

def patch_hud(txt):
    txt = replace_once(txt,
        """\tmatch_node.ui_event.connect(_on_event)""",
        """\tmatch_node.ui_event.connect(_on_event)
\tif bool(match_node.cfg.get("spectator", false)):
\t\t_slots.hide()
\t\t_side_list.hide()
\t\tvar spectator_title := _label(root, 19, Color("#ffe08a"))
\t\tspectator_title.set_anchors_preset(Control.PRESET_CENTER_TOP)
\t\tspectator_title.position = Vector2(-190, 14)
\t\tspectator_title.size = Vector2(380, 32)
\t\tspectator_title.text = "CPU VS CPU  -  SPECTATOR"
""",
        'hide spectator skill UI')
    txt = replace_once(txt,
        """\t\t"reward":
\t\t\tif e.peer == match_node.cfg.local_peer and has_node("/root/Profile"):
\t\t\t\tget_node("/root/Profile").add_gold(int(e.gold))""",
        """\t\t"reward":
\t\t\t# Currency and shop are out of scope. No rewards are paid.
\t\t\tpass""",
        'disable HUD currency')
    return txt

def build_changes(root, force=False):
    cur_main = (root / 'scripts/main.gd').read_bytes()
    before_main = cur_main.decode('utf-8-sig').replace('\r\n','\n')
    expected = new_main_bytes()
    current_hash = hashlib.sha256(before_main.encode('utf-8')).hexdigest()
    if cur_main != expected and current_hash != KNOWN_LEGACY_MAIN_SHA:
        if 'FIGHT_ROYALE_MODES_V02' not in before_main and not force:
            raise InstallError('Your scripts/main.gd was modified from the original ZIP. To protect your changes, no files were touched. Upload it for a tailored installer, or use --force if you want this installer to replace it (a backup is still made).')
        if 'FIGHT_ROYALE_MODES_V02' in before_main and not force:
            raise InstallError('Your Update 02 menu has local modifications. Run with --force to replace it or upload it for a tailored update.')
    match_src = (root / 'scripts/match.gd').read_text(encoding='utf-8-sig').replace('\r\n','\n')
    hud_src = (root / 'scripts/hud.gd').read_text(encoding='utf-8-sig').replace('\r\n','\n')
    new_match = patch_match(match_src).encode('utf-8')
    new_hud = patch_hud(hud_src).encode('utf-8')
    mode_config = {
        'update_version': VERSION,
        'modes': ['duel', 'cpu_vs_cpu'],
        'mode_labels': {'duel': 'Duel vs CPU', 'cpu_vs_cpu': 'CPU vs CPU'},
        'all_characters_unlocked': True,
        'shop_enabled': False, 'currency_rewards_enabled': False,
        'match_engine_mode': 'duel',
        'spectator_implementation': 'Both fighter peers begin with cpu so each receives AiBrain; no local fighter',
        'limits': 'AI personalities, hit timing and balance are inherited from the existing Godot source until later installers.'
    }
    return {
        'scripts/main.gd': expected,
        'scripts/match.gd': new_match,
        'scripts/hud.gd': new_hud,
        'data/modes_config.json': (json.dumps(mode_config,indent=2,ensure_ascii=False)+'\n').encode('utf-8'),
    }

def sha(b):
    return hashlib.sha256(b).hexdigest()

def atomic_write(path, content):
    path.parent.mkdir(parents=True,exist_ok=True)
    temp = path.with_name(path.name+'.tmp-'+uuid.uuid4().hex[:8])
    temp.write_bytes(content)
    os.replace(temp,path)

def install_changes(root, changes, dry_run):
    pending = {p: data for p,data in changes.items() if not (root/p).is_file() or (root/p).read_bytes()!=data}
    for p in changes:
        flag = 'UPDATE' if p in pending else 'unchanged'
        print('  %-9s %s'%(flag,p))
    if dry_run or not pending:
        return None,list(pending)
    stamp=datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')
    backup = root.parent / (root.name+'_backups') / ('modes_02_'+stamp+'_'+uuid.uuid4().hex[:6])
    originals=backup/'originals'
    records=[]
    for p,blob in pending.items():
        target=root/p
        if target.is_file():
            before=target.read_bytes()
            location=originals/p
            location.parent.mkdir(parents=True,exist_ok=True)
            location.write_bytes(before)
            records.append({'path':p,'exists':True,'sha_before':sha(before),'sha_after':sha(blob)})
        else:
            records.append({'path':p,'exists':False,'sha_before':None,'sha_after':sha(blob)})
    (backup/'backup_manifest.json').write_text(json.dumps({'version':VERSION,'project':str(root),'files':records},indent=2)+'\n',encoding='utf-8')
    committed=[]
    try:
        for p,blob in pending.items():
            atomic_write(root/p,blob)
            committed.append(p)
    except Exception:
        print('[!] Write failed, rolling back updated files.')
        for p in reversed(committed):
            original=originals/p
            if original.exists(): atomic_write(root/p,original.read_bytes())
            elif (root/p).is_file(): (root/p).unlink()
        raise
    print('Backup:',backup)
    return backup,list(pending)

def restore(root,backup_dir):
    folder=Path(backup_dir).expanduser().resolve()
    manifest=json.loads((folder/'backup_manifest.json').read_text(encoding='utf-8'))
    if manifest.get('version') != VERSION:
        raise InstallError('Not an Update 02 backup.')
    if Path(manifest.get('project','')).resolve() != root.resolve():
        raise InstallError('Backup belongs to a different project.')
    for rec in manifest['files']:
        rel=Path(rec['path'])
        if rel.is_absolute() or '..' in rel.parts:
            raise InstallError('Unsafe path in backup: '+str(rel))
        target=root/rel
        if rec['exists']:
            source=folder/'originals'/rel
            content=source.read_bytes()
            if sha(content)!=rec['sha_before']:
                raise InstallError('Backup file checksum mismatch: '+str(rel))
            atomic_write(target,content)
        elif target.exists():
            target.unlink()
        print('  Restored:',rel)
    print('Restore complete.')

def find_godot(opt):
    if opt:
        direct=Path(opt).expanduser()
        cmd=str(direct) if direct.is_file() else shutil.which(opt)
        if not cmd: raise InstallError('Godot binary not found: '+opt)
        return cmd
    for name in ('godot','godot4','Godot','Godot.exe','godot.exe'):
        exe=shutil.which(name)
        if exe: return exe
    return None

def validate_godot(root,exe):
    if not exe:
        print('Godot executable not on PATH. Script import validation skipped; please open Godot and press Play.')
        return True
    for label,opts,timeout in (
        ('Import',['--headless','--path',str(root),'--editor','--import','--quit'],240),
        ('Check scripts',['--headless','--path',str(root),'--script','res://tools/check_scripts.gd'],120),
    ):
        print('Godot:',label)
        try:
            result=subprocess.run([exe]+opts, cwd=root, capture_output=True,text=True,errors='replace',timeout=timeout)
        except subprocess.TimeoutExpired:
            print('  FAILED: timed out')
            return False
        stdout=(result.stdout or '')+'\n'+(result.stderr or '')
        failed=result.returncode!=0 or 'SCRIPT ERROR' in stdout or 'Parse Error:' in stdout
        if failed:
            print('  FAILED (exit %d):\n%s'%(result.returncode,stdout[-4500:]))
            return False
        print('  Passed')
    return True

def main():
    parser=argparse.ArgumentParser(description='Fight Royale Godot - Update 02: Two Modes')
    parser.add_argument('--project',help='Project folder. By default the current directory is used.')
    parser.add_argument('--dry-run',action='store_true',help='Show affected files without editing')
    parser.add_argument('--restore',help='Restore from a modes_02 backup directory')
    parser.add_argument('--force',action='store_true',help='Allow overwriting modified scripts/main.gd; a backup is made')
    parser.add_argument('--godot',help='Optional path to Godot executable for script validation')
    parser.add_argument('--skip-godot',action='store_true',help='Skip Godot import and script checks')
    args=parser.parse_args()
    root=choose_project(args.project)
    print('FIGHT ROYALE | UPDATE 02 - TWO MODES / NO SHOP')
    print('Project:',root)
    if args.restore:
        restore(root,args.restore)
        return 0
    changes=build_changes(root,args.force)
    backup,changed=install_changes(root,changes,args.dry_run)
    if args.dry_run:
        print('Dry run complete. No files changed.')
        return 0
    if not changed:
        print('Already up to date. No files changed.')
        return 0
    print('Updated',len(changed),'file(s).')
    if not args.skip_godot and not validate_godot(root,find_godot(args.godot)):
        print('[!] Update files installed; Godot reported errors. Backup above can restore the old files.')
        return 2
    print('DONE. Open Godot and test Duel vs CPU and CPU vs CPU.')
    return 0

if __name__=='__main__':
    try:
        sys.exit(main())
    except (InstallError, OSError, ValueError, KeyError) as exc:
        print('ERROR:',exc,file=sys.stderr)
        sys.exit(1)
