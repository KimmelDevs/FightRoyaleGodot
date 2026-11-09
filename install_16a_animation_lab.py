#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Fight Royale Godot — Update 16A: Interactive Animation Lab.

Run from inside Godot project:
  python install_16a_animation_lab.py

Makes a new main-menu Animation Lab for rotating existing VRM humanoid joints,
previewing idle/walk/run, adjusting gait and saving per-fighter settings that
also apply to live gameplay. No VRM, texture, sound, or weapon asset is changed.

Safe repeat execution, backups, --dry-run, --restore BACKUP_DIR, --check-godot.
"""
from __future__ import annotations

import argparse
import base64
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import sys
import uuid
import zlib

VERSION = "16A.1"
FLAG = "# FRG16A - interactive animation lab"
PACKED = {'scripts/animation_lab_profiles.gd': 'c-pmB-ESf{5PuGT#dPzssAO~8NqwNDQhKH8-NWSsxl}4e$gF3<cZ<EXy$~+S|K73p14E!nTQv`?cjtTN=a~sUSd`qr7_+ykloomC@)AB3oLPkacQ*;#qc%cG<UL4NOtaLYzA^=-A`>a(DphM`i2>9GwH6#r;#9nofLvImuQ_foSH&8og+(cHvS!d)A(sZ2Mo3j5kb_mA(G0Gy$uzrWQmmO%JI~o-UTBqxoHTznN_zFBK~21Sqrmc9ZJmp9NpECRf{?&SDdSg4<~zWLLTQQ+mTZklr;{paEPNc_z8}54n}58y`xOR5h+gJJREvL_jK+J}+N~GJP3~^)MiVDAjRemz>Or(+`4{)prHp2sj<KX8g{+h*%yY%~oU62Sd5jBYR|A+>O<C;1)sOJANS!^VcZ1G_$UrI!zmU<JG(}?)XMc_l!dT;FyTo;&(Uw}m<5TBi!!&SA6-PdRd!_}WVh!Q_<n}{SFl}&dysbFUxkNkndYNgcUUk<yP-_EW0^fj1-cX!;9A#p;B0w1m`|+uJ$Q}4t%X9*t57OhalPMjy5S<HtK0!X*I+ugczu|GB+w#^?)!!3g=D05GF7}yhK0lWa(bcUCHz6MxZdISiOC`8rd5K|p8YV9iMqUe%!(QfWTH}h$LUK3ZWs!@N8bEAyiQThFm$+@P9Y4=;BNP?Npos=_@;Il%Q-k&T?C|c6?!08edS(YH?%4auEBgLL;{Ju{wP{}#YEhk^j{I`~rEWksFRtATQ{Dr|iw#J6u%IS)0GWGCseiqx@#4ccs#&eJDp?h0P%o8b)aahcI5scg?FalUtZgmq8J%Z6n7(r1Hb1j&d(UI$3VfqA+jT*ap2Uc+t|Z?K;Z0EOI-cbB(fGD=^fAr|w>D-|Qrv^)r60b$p3&7lNN`d9>jd|p5*#!R_>6B9-P$&;Cc7(Un(X@ce9Sd*S`%i6827jG8OyNkb$?ULmVNJsubA_~2Nd|=2vh&@r2UY*x9va7T{2EWqZaVis~jac%B5Y+&7URBOHPIT!6AVD`p!(CFG0-=db|)kFgJL_Fm=DqnW>SiD3E7yZR5eAs!!!UChX1;zE*_eLABL_teu=xy^~GXSAL;XUSBkt;M6DFWDJIlDo}b|z3}UA<9BzX>LS!q!y(8r&jZwFjMC7#sOX6ythK|;kGJY9vR&LbM?K{aOHliko-*pTvT08BiTC}`b;rZt4cp+^G1P+-m&6BO(JSDGl1EdfHXD6VdoEg~a=Jh?PNT!I=JNOd&axM&c#JmH{^(jXCAOVwzTf|cf!MrH!-UO(p8RZzHTtG|U9(__h766*j^1zkz%jJjeC~05P^Zy&d^;Wh?bSK=3LHG#p8Jw5@!}GGLfR8CBRtW4DXW#-t`N-1wE-9CXDYp4(qOxyeV68_Bp^Yi)tWY6=Pp~&rASwpeo>`OoYqme1sfWYlA1<N>v77YbJ7P{uj16ROWW?+!Y$cbwxdUBSITL(Vnds>OVDw0La?04&xF#!fx?4`?pjz!cl984cIgzx*^N5?Ox&&U;I{woTRoY|IZ@jG3rOc*uz+UJ', 'scripts/animation_lab.gd': 'c-pNy+j84Dvd{KcU^ul^(jJADWhZe|>#cHPCGk1Fq$GPX6PJqxk&whOMQVBRWvAw!_HEzi%T8Ya5~L`{o|+d+0ve6(Mt7qxuzJW<9Ax4{66a|WZU6YAxLO4=S7P_gk$5HU!mN;ySQJYcCt)CdO~N=AVVtd$pC_r1aUi0^PnJm@Cb3wh$t;YNP(cW@E}_d*Ch~<6sRBeF!}%gt=~)t}s3*eZDoJw{h@Zx1Sx=~kFw4VuE^fmdFo#QtNHf~xj5auxkBZTLh(iBXNZ}_@k^+Y8Rz)fY5|%Q(RjB~licHbQ(<D}61>h>};Xo|XBu5tSLMeXU`DN#u$f7V%Y36Qk`><gyzAzt|I0Tkdl*pjtq$(Tk>|}l#uJUZBB+rZF)YE)t?mTe18prtL)8^%AIQN!vwE}LeC1)4Mqlp+EifbnfBIWdib1$P?{7j43x!K;nld16hg-oRnVjPN#71Hp&$bog9%#gLV2^2%yxCE&W#Zj8d$Lr4%62uJ<etlC-dv`J_R0(w|rz)~x<}%EO;yCmXw@e>l>bKu{DvW2zP|yk<;PY7@zYEp<P)v&HPw)lRq8bL$A8J#mtul;N$}smy8U;gf4obCmtVJZ3DwRX=fj-UX64h>4Q^FciF^psz7$ME~z(y)LO!5@8)fPksN(cuN&=KK5I!<GPl(B7s&W&d1=y_J_)drG+FwGxv$xKF>;<3C)V>F@q=%c*Hk=+BgU!9l-I%Qz<v{2jIvm*9|2ZkCvcDmx#KgAu`{BV0KQ@JN&f03jakfh*eM>`Dn%Xl;yU3wp{PEWn@=)+}qd&`>^VH9{p*nuD6OdQKxx@nSu$X(DSwOr+Z9?)))7Pz^3$bl>8JP|WKnM}-*0*pS41^6PlqZj|0C9wm`QiWW?Mx`OREXGd1%cJpJRg*ZXS<CXrNO`znXC+e==d3k75uqZ|1SlFEYY%9E1JA;LgZR<uf%x9^*x!I&;Rg)SXUF+5@YS1{bh;!p(rVxjB~6G?!Zhf{>K>&+qlWQnZ!;l_Jh@NhiWC+gE@5t>(mP=E=<4#~>-gx4_w{0Y>`l&&#+T))An?GwEtOYN?j^7$1(WVL<(Ok})?Hsq3^v!%prg5mMJzm8<uBl{JA?%$_-L3VBlIabn})!BNsg$JwlAY-D*aou*$CE0ie$;2N(*zE$0$l3GqQw1BT0>v$NVD8lcl!|!BZDYVi!PuqI+x5>G#Cmej6vSR3k-A&s5-oZ;ny9422b&097$*bl$QXq8V1qQ&Q)l)|WA0E2%H1UB97IyZzm_gLh6H=w+s8u~nkzGF{;E<{^pmjJ}mV)lkL&FWhhj9Auz3Xu8)<q-Hr?UTD_%B~MoPF-_nAm(C6P0KJW^fN&K`P`XM78OC$O{}A#XSYnMip6?oqdrXQP8T<S`d01nMr=Q+0Q=k@fyE}R>i%O&Lh(>P-w|Wwhl~3r~+NKQf9hKaB3rg9qpviz|k(|T*tI|9K{UhyQ;ZIJ!jl9v%Uyja?y^klSr!~%)M#iIQT*;Un(NAqsq1o@zw?AO|82AMew3w=>BP{5zYfd@FxX?K|KRG+PJh?a*r$_Gr!{A-7G>h3xy^(Lg)wVAkLFn0xS1I1ZP|_7&A)eZSi%%r88R#+um#GpEh(#d;kq|zDhQd@8ib7~RmAP0Y5XQR5%ie~4bx?sIue<i$1QN7^uDZl4aa0Sm8C3|tmaIFJF3#%aLkwZAmK}DaooXgZl3RBU_UgnC1)=vYr^2Aytr6)WiZU1}UEbPVy6L=3G%P5LDTTm6%`*i+z?ylw_<(PUh>2sGt++)17yNyg%Lvr8(=E6A4l8DtHa7m3w58+g+(M@kKnA7};QTNc?Fl-Y1QbFnRI0kj>^_A(7}`CPSA;cdzC*AEMX6vcj^ym2M9`=g5UOqTbZfgJbeCmWvW{ataMfSJ++T<t@iY48Um#rE5x?NqF*>##@y)rp#@%l;v$Q*81-SV-I;ZdU|M(9Hrm|ak5WJhs$ZlbE&Aq|p68;;>f7-#(vI^FNlb^>+MX}lEi}A^~i}TB)Q}5{X<kR`t=={=y6zuaQGHfL=E@oYE(1Blu56=Ebj-3CL666^d93roVjb6P2=Bz3CP)^lnz*bi<*mqxBV=w2qd5DauYq&D(RKt2JB1-F!rBslx(z0m?i}2efKZ=f0_>Vqh^FC9T;ej5sI$~7LS*W6b@BJ*tTL9JPHdgd0(`Cjt|CF!&zfyaDGaC+tGof!HQt>=rloY_k|G}q-LJmlX92h)Gmm<3dw`pjDvCrX3Od(M6mGk>GG1XN1LTym{UANzVcv|fX^(Pe{7XBI4f3bdV)b2s6a`#_9t)rM|YAIr#%riZf;>~lk6%nwu5|*wGXQa=yp-t-3BuT?_dP@0-9)V+<$U7yf``gRlcPro+!(Yf)_=@u=8m=ys4d6#nQ~^th$0+X=hoa5yK9CGJF40#`CW<%@BVp4i;3hB$3WX(=#!U}`H~s+!NM-KD$lpU203i;9{CKyjxIoHuPJ>dVKz(D7NV9)Jeb?6gxp0=yAX8QesUbuHK|WDsgCxfS9$&1OP;xYwi9h};J|*C*%$(A3V#9LnK+}|=U`<;c%1Ee$0|S8^5pGmnTCrzdEWg&Z&yr!a^6Ak2bstiX{XxGxWGhrLC~EA@ixA|$g7YbD^-c?g#|?B{U^O|pbt1yfJEY>x+kOd<+{awp^Y((eBwfhb!Ebmu<Yi!11=Xxgxy0V^>dW!b<p><(*P~x1HU|w3aZlO`)^j1TPOAk@U=%%5aS;zdR~gGCJmb!iJDA-kmuki!lL#qNHjM9eU>-Ej9lVA!a0ewNwd8;nTd0@v7W`$AV)eq_5`%tE=A9BZV&28Pt!MTFnV3}BnEP><DlRZar#M!zLLjb5pu9lMQ$=-gv%#x<AbW7YnIS{dUr&Ku%&}a#OYApUinKK&9kY<L=Zj?=HulG<HkrK|pwI^H0sa{nz{bvf_ifA02&p$_<x=q-?*0{jjN-d6P3UShB$Pm|swM&Zb3xsz_F^>DUi$u%_u=C7V*HHN%?i<Ae{X+(>TKLtE~g=UdMuVKDN?_=`_b9^6O0!o7gysCqo*mUqiYfq?5W+^+vgJVoii#?=!2>%XlE*0oKU^Nw~Ul39FgSO`WO6yaAh!n0}Xf68KC~4((20E5*A>?24PK!jEn>B`#6wka0V_W4P{jA3IMK*rYcC*q_OvU|J~~Y$3m}Hmqii)hOrjjYh}7TfxvrXl+$$91Z~~>^c#y4a0qz4VXd;$9dbi}!nYRS3CHdY*mv!~7*VVP?;f;6!^u2CHu*(jZ|*C%w#ucop2VSule|9GNL0*SKcPEZoCJ~T5l&3d$3@%|GWZp4J$>uz)}I|ixniPntnxs#6=eyPfgY*pP^hS^_UHodT2}!=QuRQs0lVZI&IC<}e~3O3!ax3bSnGmhRIwOZtqk^pL{+2NL+cv5k|b)arbAsv?`R}g;Q=7ik3B3qnl5%DJ;>KObqw69F$<b~nif2ufo7QQA8tmOt`iq=%KAyI!N$RU#;8$V8H5aM(3ot5RL=!yn%~ktgv{t(?z;af6r>6>xQ04bFvyr8Ta~G9JFTPT{vUHhU)ONqAn;%}2+KR2SCl8=g#iVhwh-HHZr-z84@p3=Do+V-Yn-#1ixm%C9I{z5I83km2e6VN!d4T>8`q<>A@_6NUz~H{jN^KhCDEM<OuGdrM<A>VvM$sS_l!0nMhG1AG&ZgEkz;O$6dA+~h1uG|nn4(2ytY+mPuDB#4G0-?+pK0<^M0x*#-sCY&V#+G^^W4@0<xr8l`u*4?!H<;@Q>DiLeCFi6d0THD+ElA@bQ8OAx~h(;W|}Mk#ap<sdUTa0Z*ne1P0$1NEC%d06^Z%mP5nBh<mGxxn-CCXryGZ-b<!dGK{7Q)Hqvs`Y8h`kQqZSN(1EK;0C@^b&Z<o)|Ll;IartDM?EdrK(Yk{=B4;hYM^wV63Dm2h#r2R6w$+T_1%<@P>}8CgsV_1vBA^uV{1k1hTH1G5(hK7T5=5g-zv4Dqr`oU53i{Zo`W%nX4h^-ly3|-XqwCi$S1P{D$WS4qgz5NEDlrnK;P_egy-B;24Ru$HN5w>99}4j%4zuRzS&DhCk#`DClpb9H%6fmH(S7d@!W)<?`5Ve=*j1!<CF7G9v0lat8@H0I<{7C2y@=_g8^2zN;2D{92#r!j<l%h#jjDISS_O2#{J6{*nammA5$E1`{3G-<Z>1ABFIyEJgjeF@k;D=Z?@YFsAey9LdY&(7z5NCz<Lm{X4y9UHDS4_mp@7in&_27vY`edv=D(dBFwWX@J66VVv1!FHd3&d>>hgnPOB)&ry-4rhS`8*@YU4NiWBD4KgQvXxjcH!XD_`5#a&@MW^LH=ne1ClLi=qrzTl7}EZZYg=DrSZsDaJp#W?Y@a1J?chY5n&ZlgPZ3ye(v=I+k^_>Uw0CQ5J{FZvd$DjhyeYEyRXj2nW>bRgOY{>pfaJRq(F5BS^f&5Aoez_JU}LotIu580s4j=@ieXdTuC`rUd9WM~S+xV2Tez3$&=IC|Kj-)%L4cCC7Do6zYuZdiN$0%9J_9#G0OZ=|LB6djwJp5V7?>*lsm_{|vmuTs$MEv*yO6azMx_^lG_s(3lpo+ghxkEN5eM~hnOJ;@<({9S3AuADdIM<>;G=hbA07wZ!;e6g;Y1yvuwP_CC;Gx!ZvWEpn*S?czrCbbL39<%QblfUR9W6ir>#n=)EIGjL7N|pDukV8K>g}=To;)88YWuBu#I2*1Ld#rJXY)WA0L9CA4^ut>#6R1tN*6URJjDlhXHvwLy$Zz#NPBzG(I0JZ<b5%1M1Z>G7d%{W(N|9;=?o`czArG#ZMaLP9#}{L#+Yq$|t$b$LVd<=gXqkFi2MNL`A^o^+Sl|u6rnD51*KqU!-!{YrZHiSkc<OrfjMVvAp?lkw7?am_LtmCtHtU*r$yc%R^2DRv%2&uRnC&cO7`u7q$4-f{Uc~RHJ9@Hrf<H$1y`iFb@i7plR~6V<0=B?UAlBRmzpemf;&pPvx)MLZo5y(c_<{zwvgC1W^#g`_SCf(V{_67b;@mqOeY~{yEi)Z)$cBP=n%VSWWkWW-^o)rbzO^=t*eNTCRX0Ny?P5sTRYv*40H544-wRNvSik+P<?Hq5$NHwlAHzoaff~LZDRUJCMTLXzU6_RsmQWgQW#MEp;RCu;O*dlGU4tS9ef$-MJyUA$5UzQYOd*&zgI)1=7Kg?cgjrri8id`&F>+aX!kST5@4HMW0zhP}Wkh5ec^%Ru5zfNm<ciKukNkk*Gcw}CA2tH(88(X<TyI$h;Qe7$YS78HDX29v?s8cAzFOrTu~Jzch|33s>;#7Y7Q=Y509D5Py0p@0u(;&S9_4*iJg`flmY*jFkM-25Lsll)EfBgqr>F403pmphwFp4xPv$W?N88-T(exHEcXl?d!~a*%1rS`;QoL$0x9=JSk3HKg$c{k6|I)G-J?aG&!2%$vUL6N%AFB{<)8!YgxA????Gk7(t5G3YLCwfNw1!%Ct5-KHQLJyQA@Wql88Ej5TU`Tz>w&hau&IvTyXz*vXc(80=A?btQd*##o~T+&_le-AO9r!9Am0ug%JJy14-cCOE9uQziQ)eNF)X!H', 'scenes/animation_lab.tscn': 'c-l43v2Fq}3<lu+o+8Rb7p{Q1RLW4HZk@`As>tNryGXe>a!d<-`uZSj&S&ROd>jW~17<XdKuf_=-PU{)&meC1)pbX_h-a*H=72`71)V(vjzz2~Ad|D&eC_*sv)V(BdNoq^2~O*AuqF=9ZkCf>;xY|rGRzwD_89%pUW?vS7N(@539fV&KQHsn>^jI{BCfvZdnihqmu8;hINfCZ{Gbzw(A;cf`t_>uPtzf(ZtwPkEHN~>Z=mJ-MLyfYtM>D!?jOpRW(E', 'data/animation_lab_profiles.json': 'c-pJxQczGTOD!tS%+FJ@QZUp3@zXNXGfIGBK!NI7u39bt#mNek'}


def patch_once(source: str, anchor: str, replacement: str, label: str) -> str:
    count = source.count(anchor)
    if count != 1:
        raise ValueError(f"{label}: expected one anchor; found {count}. No files changed.")
    return source.replace(anchor, replacement, 1)


def patch_motion(s: str) -> str:
    if FLAG in s:
        if 'var lab_profile: Dictionary' in s and 'func _lab_offsets' in s:
            return s
        raise ValueError("Incomplete 16A patch: motion_layer.gd")
    s = patch_once(s, 'var bone_map: Dictionary = {}  # FRG04 - dynamic humanoid lookups',
        'var bone_map: Dictionary = {}  # FRG04 - dynamic humanoid lookups\n'
        + FLAG + '\nvar lab_profile: Dictionary = {}  # per-fighter, persisted locomotion settings',
        'MotionLayer profile property')
    s = patch_once(s, 'func _process_modification() -> void:', """func _lab_offsets(table: Dictionary, role: String) -> Vector3:
	var raw: Variant = table.get(role, [0.0, 0.0, 0.0])
	if not (raw is Array) or raw.size() != 3:
		return Vector3.ZERO
	return Vector3(float(raw[0]), float(raw[1]), float(raw[2]))

func _process_modification() -> void:""", 'MotionLayer interpolation helper')
    s = patch_once(s, 'var stride := (0.48 + 0.22 * sprint) * gait', """var gait_settings: Dictionary = lab_profile.get("gait", {})
	var stride := (0.48 + 0.22 * sprint) * gait * clampf(float(gait_settings.get("stride", 1.0)), 0.0, 2.0)""",
        'MotionLayer stride tuning')
    s = patch_once(s, 'var bob := absf(s) * (0.025 + 0.018 * sprint) * gait',
        'var bob := absf(s) * (0.025 + 0.018 * sprint) * gait * clampf(float(gait_settings.get("bob", 1.0)), 0.0, 2.0)',
        'MotionLayer hip bob')
    s = patch_once(s, 'maxf(0.0, -stepping) * 0.42 * gait + (0.16 if airborne else 0.0)',
        'maxf(0.0, -stepping) * 0.42 * gait * clampf(float(gait_settings.get("knee", 1.0)), 0.0, 2.0) + (0.16 if airborne else 0.0)',
        'MotionLayer knees')
    s = patch_once(s, '-stepping * 0.10 * gait * (0.7 if heavy else 1.0)',
        '-stepping * 0.10 * gait * (0.7 if heavy else 1.0) * clampf(float(gait_settings.get("arms", 1.0)), 0.0, 2.0)',
        'MotionLayer arm swing')
    s += """
	# FRG16A: user-authored joint offsets blend into the existing procedural gait.
	# No changes to humanoid rest poses, skin weights, or combat animation tracks.
	var pose_states: Dictionary = lab_profile.get("poses", {})
	var idle_offsets: Dictionary = pose_states.get("idle", {})
	var walk_offsets: Dictionary = pose_states.get("walk", {})
	var run_offsets: Dictionary = pose_states.get("run", {})
	var blend_walk: float = clampf(walk, 0.0, 1.0)
	var blend_run: float = clampf(run, 0.0, 1.0) * blend_walk
	for key in bone_map.keys():
		var role: String = String(key)
		var bone_id: int = _bone_name(sk, role)
		if bone_id < 0:
			continue
		var euler: Vector3 = _lab_offsets(idle_offsets, role).lerp(_lab_offsets(walk_offsets, role), blend_walk)
		euler = euler.lerp(_lab_offsets(run_offsets, role), blend_run)
		if euler.length_squared() < 0.000001:
			continue
		var radians := Vector3(deg_to_rad(euler.x), deg_to_rad(euler.y), deg_to_rad(euler.z))
		var adjustment := Quaternion.from_euler(radians)
		sk.set_bone_pose_rotation(bone_id, (sk.get_bone_pose_rotation(bone_id) * adjustment).normalized())
"""
    return s


def patch_model(s: str) -> str:
    if FLAG in s:
        if 'var lab_paused := false' in s and 'motion.lab_profile' in s:
            return s
        raise ValueError("Incomplete 16A patch: fighter_model.gd")
    s = patch_once(s, 'class_name FighterModel\nextends Node3D',
        'class_name FighterModel\nextends Node3D\n' + FLAG +
        '\nconst LAB_PROFILES = preload("res://scripts/animation_lab_profiles.gd")',
        'Model profile dependency')
    s = patch_once(s, 'var look: Dictionary',
        'var character_id := ""  # canonical fighter ID, not shared kit ID\nvar lab_paused := false\nvar look: Dictionary',
        'Model fighter identity')
    s = patch_once(s, 'motion.bone_map = FighterRig.runtime_bone_map(skeleton, rig_profile)\n\tskeleton.add_child(motion)',
        'motion.bone_map = FighterRig.runtime_bone_map(skeleton, rig_profile)\n'
        '	motion.lab_profile = LAB_PROFILES.load_for(character_id if not character_id.is_empty() else String(look.get("vrm", "")))\n'
        '	skeleton.add_child(motion)', 'Model motion profile initialization')
    s = patch_once(s, '_phase += dt * (10.0 + 6.0 * run) * walk',
        'if not lab_paused:\n\t\t_phase += dt * (10.0 + 6.0 * run) * walk',
        'Model gait pause')
    return s


def patch_fighter(s: str) -> str:
    if FLAG in s:
        if 'model.character_id = String(c.id)' in s:
            return s
        raise ValueError("Incomplete 16A patch: fighter.gd")
    return patch_once(s, 'model = FighterModel.new()\n\tadd_child(model)\n\tmodel.setup(look)',
        'model = FighterModel.new()\n\tadd_child(model)\n'
        '	' + FLAG + '\n\tmodel.character_id = String(c.id)\n\tmodel.setup(look)',
        'Fighter runtime profile key')


def patch_main(s: str) -> str:
    if FLAG in s:
        if 'Animation Lab' in s and 'scenes/animation_lab.tscn' in s:
            return s
        raise ValueError("Incomplete 16A patch: main.gd")
    return patch_once(s, '	_btn(v, "Settings / Keybinds", show_settings, 320)',
        '	' + FLAG + '\n'
        '	_btn(v, "Animation Lab  ·  Edit Walk & Joints", func(): get_tree().change_scene_to_file("res://scenes/animation_lab.tscn"), 320)\n'
        '	_btn(v, "Settings / Keybinds", show_settings, 320)',
        'Main menu Animation Lab button')


def digest(data: bytes | None) -> str | None:
    return hashlib.sha256(data).hexdigest() if data is not None else None


def build_changes(root: Path) -> dict[str, bytes]:
    if not (root / "project.godot").is_file():
        raise ValueError("No project.godot here. Run inside your Godot project directory.")
    changes = {}
    for path, patch in [
        ("scripts/motion_layer.gd", patch_motion),
        ("scripts/fighter_model.gd", patch_model),
        ("scripts/fighter.gd", patch_fighter),
        ("scripts/main.gd", patch_main),
    ]:
        source = root / path
        if not source.is_file():
            raise ValueError("Missing required project file: " + path)
        current = source.read_text(encoding="utf-8-sig")
        updated = patch(current)
        if current != updated:
            changes[path] = updated.encode("utf-8")
    for path, packed in PACKED.items():
        target = root / path
        if path == "data/animation_lab_profiles.json" and target.is_file():
            # Never replace existing saved profiles with empty defaults.
            current = json.loads(target.read_text(encoding="utf-8-sig"))
            if not isinstance(current, dict) or not isinstance(current.get("fighters", {}), dict):
                raise ValueError("Existing animation profile JSON is malformed: " + path)
            continue
        data = zlib.decompress(base64.b85decode(packed.encode("ascii")))
        if not target.is_file() or target.read_bytes() != data:
            changes[path] = data
    report = ("Fight Royale - Update 16A: Animation Lab\n\n"
              "Open the Godot project and use the Animation Lab button in the main menu.\n"
              "Select a fighter and Idle/Walk/Run; click joint markers or use the bone list.\n"
              "Use X, Y, Z sliders for joint offsets, gait sliders for stride, knees, arms, hip bob.\n"
              "Save Fighter persists settings to user://animation_lab_profiles.json and (if writable)\n"
              "res://data/animation_lab_profiles.json. Battles use the character's saved profile.\n"
              "This is a live locomotion offset editor, not an AnimationPlayer keyframe timeline.\n"
              "It does not modify VRM skeletons, skin weights, weapons, combat, sound, or other modes.\n"
              "Godot in-engine rendering/playability still requires your local test.\n").encode('utf-8')
    if not (root / "reports/animation_lab_16a.txt").is_file() or (root / "reports/animation_lab_16a.txt").read_bytes() != report:
        changes["reports/animation_lab_16a.txt"] = report
    return changes


def atomic_write(dest: Path, data: bytes) -> None:
    dest.parent.mkdir(parents=True, exist_ok=True)
    tmp = dest.with_name(dest.name + ".tmp16a_" + uuid.uuid4().hex[:7])
    try:
        tmp.write_bytes(data)
        tmp.replace(dest)
    finally:
        tmp.unlink(missing_ok=True)


def install(root: Path, changes: dict[str, bytes], dry_run: bool) -> None:
    if not changes:
        print("Update 16A already installed; nothing to modify.")
        return
    print("Update 16A will change:")
    for f in changes:
        print(" -", f)
    if dry_run:
        print("Dry run complete; nothing written.")
        return
    folder = (root.parent / (root.name + "_backups") /
              ("animation_lab_16a_" + datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S") + "_" + uuid.uuid4().hex[:6]))
    folder.mkdir(parents=True, exist_ok=False)
    manifest = {"version": VERSION, "root": str(root), "files": {}}
    for f, data in changes.items():
        path = root / f
        before = path.read_bytes() if path.is_file() else None
        manifest["files"][f] = {"before": digest(before), "after": digest(data)}
        if before is not None:
            old = folder / "originals" / f
            old.parent.mkdir(parents=True, exist_ok=True)
            old.write_bytes(before)
    (folder / "manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    committed = []
    try:
        for f, data in changes.items():
            atomic_write(root / f, data)
            committed.append(f)
    except Exception:
        for f in reversed(committed):
            old = folder / "originals" / f
            if old.is_file():
                atomic_write(root / f, old.read_bytes())
            else:
                (root / f).unlink(missing_ok=True)
        raise
    print("Installed Update 16A. Backup:", folder)
    print("Open Godot -> Main Menu -> Animation Lab (VRM assets must be imported first).")


def restore(root: Path, folder_path: str) -> None:
    folder = Path(folder_path).expanduser().resolve()
    manifest = json.loads((folder / "manifest.json").read_text(encoding="utf-8"))
    if manifest.get("version") != VERSION or Path(manifest.get("root", "")).resolve() != root:
        raise ValueError("Backup belongs to a different project or version")
    for f, hashes in manifest["files"].items():
        now = (root / f).read_bytes() if (root / f).is_file() else None
        if digest(now) != hashes["after"]:
            raise ValueError("Refusing restore: a file was modified since installation: " + f)
        if hashes["before"] is not None:
            old = folder / "originals" / f
            if not old.is_file() or digest(old.read_bytes()) != hashes["before"]:
                raise ValueError("Backup corrupted: " + f)
    for f in manifest["files"]:
        old = folder / "originals" / f
        if old.is_file():
            atomic_write(root / f, old.read_bytes())
        else:
            (root / f).unlink(missing_ok=True)
    print("Restored:", folder)


def check_godot(root: Path) -> None:
    executable = shutil.which("godot") or shutil.which("godot4")
    if not executable:
        print("Godot not on PATH; open project in Godot editor to import/validate.")
        return
    result = subprocess.run([executable, "--headless", "--editor", "--path", str(root), "--quit"],
                            capture_output=True, text=True, timeout=120)
    print((result.stdout + "\n" + result.stderr)[-8000:])
    if result.returncode:
        raise RuntimeError("Godot validation failed (exit " + str(result.returncode) + ")")


def main() -> int:
    parser = argparse.ArgumentParser(description="Fight Royale Update 16A - visual animation lab")
    parser.add_argument("--project", type=Path, default=Path.cwd())
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--check-godot", action="store_true")
    parser.add_argument("--restore", metavar="BACKUP_DIR")
    args = parser.parse_args()
    root = args.project.expanduser().resolve()
    try:
        if args.restore:
            restore(root, args.restore)
        else:
            install(root, build_changes(root), args.dry_run)
            if args.check_godot and not args.dry_run:
                check_godot(root)
        return 0
    except Exception as exc:
        print("ERROR:", exc, file=sys.stderr)
        return 1

if __name__ == "__main__":
    raise SystemExit(main())
