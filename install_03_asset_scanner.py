#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""FIGHT ROYALE GODOT | UPDATE 03: Asset scanner & model audit

Run inside the Godot project folder:
    python install_03_asset_scanner.py

Optional:
    python install_03_asset_scanner.py --dry-run
    python install_03_asset_scanner.py --strict
    python install_03_asset_scanner.py --restore "PATH_TO_ASSETS_03_BACKUP"

Does not edit scripts, scenes, animations, VRMs, or sounds. Scans the
existing models/, animations/, sfx/ and roster, then generates manifests
and readable reports for Update 04 skeleton mapping. No pip packages.
"""
from __future__ import annotations
import argparse
import base64
from collections import Counter
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import struct
import sys
import uuid
import zlib

VERSION = "03.0"
# Exact relative filenames from the user's sound list (compressed for a single-file installer).
EXPECTED_SFX_B85 = (
    'c-ozP>9QNUuHOGVOm-!y+)AECMM;#@Uae;D9+oUWeK3&(NVJwus?M>!g|8<P1VM~pjLWwE6UMMSPuJl-Y+*cI#&r2QonxH;`*Z$Z|1D_DmZoTa'
    'o#$}~(<Ppk7_RUBs^t={@pMkpzMkkeP350sSf+SA4b$m+xW;t4ho^bQB~EKv*2gf@?N4Kx?uI^WZ@%|w9hNu&AeooAq-BYh?G&c<6&HBZS6HqZ'
    'a7}4B$8m(~r~4RB^Agup1L89-_c&ehb7(L$;1-7EeR{%W;T}&@+J@V33EPk+gW9)!8P;vMz+l5jx1)()ZZ1B(!guVSM!0pqT;O^AsNQ#&#>L*J'
    '13kkX-ojv(!H(-QEW`60;2nkyNJMYn__?oe`6$D3^xf$OzsA!R$2dRW4&9^Dc>P43P7g$QFEFPOZ@oSeJpc88!5tg=3U3dCI80kyZUL|@k1lbJ'
    'fxa+vYXey01*Q#{3@#r={Kpx%{qpE1W*yUZdID*H&v*@!gV>fBx6{0z;k|ou9R!y_wgI@4W`Bv_F^q<m-XF$rTXtB~c-4YTPT#n8D`lT(?N9M_'
    '8n*a6bqs01u=H;<ZntsYKHzZa;M#o7@b>sg-E-^0KRw?oOw_yQScO^Qwj_{K!{y5&rVW>$9ffubKe00ihKU$~gxz`n^CvD$f1U?e|M8!2h8YYX'
    'Okj4ez?QF(IcrEQaD=~4ue2a*F99ZQLFAGenEc~(OCWT%(|K5~>j7jM?vG7?2as19zvKD=1M`sfiKOlJ04|Gb8Ri09!Wm?GnTbbOW@mCM{DJ}v'
    '$D?_1{1y_aG^Fs*+X(vw{s(~X4tPDm%2@~@@Aqp*f$SjxAVXG}sYBo`)_EZwb%x{u%k&xW?YCt(!+Ik|ZZNQ3=lAIXf_Q=ToCmsp=w$(Rgr!ZN'
    ';F3UAZ!(GSZc~8Gpm`WiM|ny^T=wS^KZOV7M6$Pqyia2c$O6j_qOb@72S9vaskf9im~#*eAaYk+9INx8ic|CKx`5ZPJ(!<;*nNTb81r-1XMhbj'
    'e8bY4E|2EZAK~>S5BztBe>>C*UhYz1_fN}dy$q+@z{_^qrzwsW_BDaz!_mcEH>E4Tz6`ZLAtOyCtZm?n?U~m35tk0K!G?4)4EY*BBxFW+;m<UE'
    '#W%b%@ZRNNAwrA4LG1yp=?H^M_f+}LeSc=f0-8V(;}!D?&t}e1&aIDSh|S<G0bh8X!WX{vH;y0PVFP*B0AUYaXq%2avOm1r8a@lD^%55Nd>M`H'
    'u|G*{0Oza@@||TxUVt71XMH_H5ci0FDDU1t49%YyX7ay)(4sh64Y)*SVO3eo$bznjlht*Do8lGM^x`pn!s>@vYGnBe5=Qe)zxV}VS?4bx-mQ?$'
    'XkU<3#;e5VhgTTC)V|<-YKCl&CGGde=~}0qN2!6A4Ltt#HgKZTxB~yBF>H}{b4E=A%oCh%?sq&Zpn{nf-8lw$;*!E*k<)#7e<lJKZVBe}3#0%Z'
    'Ceq6RvGfS;O{VmQHE|wro<YS6%U6*wf`Q*AS%2xZ(%^fep3(HSc;4!tMo(G79o|>VH5ZqM#wBh8E@XV+IZRvk!o!_!d@yo_jzhxhxWnXe<pCU~'
    '6%T``+_|W8IKQ)883Qnqi-M&~`!~Ead_Jz^@N|LdaqYJ?kV^suxhzQ^LvwNX>H=C|dn1)6<R#+cV7TUZd^g#Qa9}%L%orIbGy{Zvjh`@2*<X?8'
    '?!)~)9t}r>Kb`~Fa{q<1ZUVLKeS9;6IsRJEoNpu!x;s5kf=#?w=HVWJnSH=z-1(L1G-@$;thy}k=Ev8G|4j$V?a@(bxw=aesVLx{DRsXe{Fc`#'
    '-t>TuhLE+RftvZ{-c+`{mZXHwX?qRLn<I4%S3Img=eYE=X}I08B5_};mZ~svEgGH1@r}1Tg!Hs$Bnu4k^<yWI(6RTmDqzjBz9u-i$CJ|Qw8Af-'
    'tekz&PW}c-I<0}<KthJ~T?FbKmipEp;NW^s@NMT1ddf^vdzff$Ua+Ux@rOmiXERjh;xjfkzr(R`BT=pPJ(!}GearilK!wTgxK1(tiL$=laSC*U'
    'EI;jq^4_5S>|6V8L==u|zwMFN=aLdV)Lk>MDzEXBZiPAFMb;Lvg7&(k4RxykB6)%r-O$)ZwxbW=Iq-m;*urCwN|J)U3?MYObxfyFw5fD}XS@#k'
    '6UG3BllQW`(hgy?5=1Y;?X>}p=?W`hg-zvvlYNNZ@hyBGw_#?Ha42q&2Z?c8NxMGKyi4a&J1y%AZDt2*5$*nb6hoD*r{OVklBLROFk#L+EV<<$'
    'oa7x}8TjHphINf7$YF&T5ZQwo!+4=ti*WvVgA2m?DCR(1-_@`zs51yc<Xf>aEa5sNG#5?lbAaU~wiW?j!WnLa3lPq;@G@)jDHnWu;I9*G#&1{z'
    'pss$k5d1=8cx(uH!ueZ)mxr%takP`+>4DA?APnQY_J|Gl#6{MtA%m8);}Xs8280^`NQSR>{ysj7;}<&^8i+JUGfLO61ypUOXfCndjr?Dop|3&D'
    'Fe)&N*X}JdU>)vL5F6kPj{jNaWEj5TBcS2pv2Q&E&LyzTjKj6R3i$<=5dFJ*Isqo{SJr{ML0J+X8PQk{FPlKP5w}~={#<b#yn-2wID)pgAXC7X'
    '+#~FoPnUcn%b3=5Tg1Adwaq2H;&{#K;W~p%8{_H$(fp314Jz!>iy#CI^cxIE(f1q-zs+e*=oQ-M9+oB`^Fk13%em$D3S9jg70(gO%PB0&@GWNh'
    '3?S<<isxbC<EEAx8d<y#%(T^hSLkSTBLhQOg3UxI2b38I9B=bk_du4$mhbLpBD(RR5T6j{j>^N;z8jIAaYOlgIl>@6o*p3Oi4PcV0mF8Ah>-kF'
    'Ak57>KY(@a`=tB=4Z-L%nU>I%wgCbc>6NttJ7{7+<j2Z-KN8Wf0qrO>0Ya}&YnyLsC0KPw!8ALbGl78+SjDh*@H1~8V?Wn0nz#qVFrzW|k<4e0'
    '1DuNBIFt4zik0IR%n(@y1}nnGd~U;=%q))xhc97)FT+(2Hdkv%-V0%E!a5)|sGgMy20fE-^Zv(mMkj6dOS~SS>^&@M+DRs(7x)H$DlbxoL=a*V'
    '`7Ag1Cupka{w|!cS}0E788lIJj?(PU?e`@17x9AYHq~d^VVu^1MQ?!P<tBD+(!n(p{hMgZ;5$8FURvtqu`j^=?w&_<x)KQ2eFXK-S^bDY<uHN>'
    '^7j=uFkN<HYP$Zku^f5Y%@MhVj=AX?n0LCZBtz(k0k?4wbbesIil}6RQek&Ni(n6Ij~Q0drMLV^s5cl0FgkpMFLHQRr!=fF?*^=mg-g5t$ns~<'
    '?YAMt6*h3tXNg@F_|&CmJP$;SYC+%Vz*}&qeV$Q&ng;_|!!35RCdO&d`hdAkDCxYND4Vb`j)GT6_l{zae)BR0frPSQi-xD!(++2Abb|K#Ig?rT'
    ';G499hv_nmH1G{|!>dSRn)m1I5y=L2MC^axH=5IK&}ayX133RW2KKRqPGTG1{v6(EceMU40HB*<UjJn)lvzRj%%I3g%SVd=$73`*A#B(fa+Ao7'
    'aNFUAJmavtpBt?~hPvu-4sW*@-e^A{a4F*Q1b*(eEP<M()vmjBKVx(Wj1jL~W+#JyBOggk)(Woi3@cp&K(5qX`L@J=cha(We>T7($g*10h%=Ft'
    '4uN7O+HLMTT=pHKrB=`{+mFv72(lB=9@Mcw2AOCB4QP}&dV5PpJ%|Bt3OILSg11Icf<ZWPXiH%@(60;<CxOSfo_e!!#`-s^S%J;<WcbNjjJkv@'
    '6S(989+9@cL5m{+E%zr7K*<FagHpB1X~>kwz*`KymFX%9)c1NKP(Ke85W`|e48`u{+SwptXjwji){$(hVLAfEKu$wtmvBHMZphWnrV-1vC@*O8'
    'gnKDtxCN@{isI@ex2%ip128J$5}q@$_GHa23X$C-7d(vKKo^vq#z4^Iag9%m@1lb+TfzIcufAe($)WSYdee=$&$%uKp|GMWK7H-zt=E9Ip4PB0'
    'z0;~<$doEJru-hF3bx3R>>&JXa=Iw3Rl{&8<H;Mp<{sl3JH(qf7f&AZoON~_c`=76sEQ;qkrx%hhTQyxIqaha$#JXyequ#gv@YpS!U<_ew7QU|'
    '*>Ji}spE+U==TrW`trMlZ3}3xK|3Z|kd58=(}nVmKV3(!LMPfgtie=Fo7bU#xej}5BX+OKhFG`^Z?ByjExtZr-mlj&7B+*~@UK`&zT<%k#?^m`'
    '{Cs*D^kK@IH{iU$#4(I<TT8mvcq(?=`zx+kX6!pnak#fU{|of;;*F(OLc!fFjgd@Fnf-fKHl7%Xa;SD}7iZ)Fg{y!lT3b8@V02DFP2aE83w$KG'
    'N+eDgpRNQq?CR52f5)TvF*IS8*grg!gCu#?gIDqIH`j95q750TRElUa^8fHg9M)rkGF04G3&!o8{P-Th$RrOi4xO|?4fu3VV|-@jZU7P{#Oz31'
    'c!(*?O5hd~1I1#mI;yRNv?!dpiOct>xDGecF&g%1fp8`uLq!gJi=kD|K<AIdqmGdFq9zWhp4P=mOnya=L34-<tsxXww?4K=q47moo_mz?Bw26n'
    'TOY4SiF};{nNNHKNZY8jsf@Xy9`H{X7G4xtMV6muv^2iwjqKM6WS=^%2n3EIFFNX$;3K$M2LSyHHt+#MOtu`RF7)4M2Lzc*hWQzTjT9A~L@#8J'
    'm^}s@bBK|Q5B#RZfH{OPn5Yz?jp$5S(NOTvKd0;ablKVN+I<{R<-DK6$jF00n?aBbOkwAJ0=0q7E_Nu-pcc@<30HdjJ;Px+uW1bczK6XDn2&`R'
    '0oNlSQLlC;E7kcLAeB41lW|7Lk1LX$<hb6;>c|K*<Pk5R@d-8pz4r?SZ$LK2{w2^AP~SnFZG~LIl8Z?k9<a{1v$`-j?p@J++CMCfW0=X1w&IDl'
    'XhBTA!V!;rg~{;5m9}vjt?rK5_azD<eW@X<32x>s(}Zt*%o6ys*fyXht9y~`)gpU%-i5|&xXB<1n=UcBVzH{^?DVPu7fe%LAo<pMDij1r=+has'
    '_w!EsI2z?6y9b7bxhdA8=wEha;77umh8u92!<^<dPb>SjXW45io(JU?7Weo5{>L0&sl@HLtFAp;-pHf&mT4hv-aZ7S11^YL3eR53WZ4m)Ga7Qk'
    '<k0&2iN1VG!{}2`chm8m8GymQAkgbfoXDiqVqorG?QiVy#Z^a97-BH*MonSWp-#~<lXrZ}rvWm=RtLL~@K3U1pa4I8r{QABut9o@MtSzCTwv=P'
    'KFCL2<2U+)Z@~=iJuGK5Pt9aaP?iZHle)#yPcI~52;7rc^3yJ$$+U4*Pw)enjI!Ih(P1Pp6YVn~Ups1<q65nM1m**Ep!yI6Bi=>kVK~McQSsPu'
    ')al<aZEa*HV`L|Ub8P=3yuq@8QnisN?&%<9Ld$WQw4$)NcSA>MLztAccJhZwTl~FgqphM{LEt0vb9!TQb;)^H_cQSKs#nn0j*@B@4wY^2cFSjW'
    '230%1e8x5M9%Gpkcd>LTT(2qkCmBH-0z3S8jl80f%0z<MBVxE*vPU;l7xJ;dUn@Vd9ZrMz%D&=EBU|TZafv=eSpe$DnrR{~#QjU$cpk&m-hjCe'
    'l|pAT&}5JD2ozxNl0ay+Te&u|cf(AyEv2!#AQS}+#`!{I0Pkw@V(_B7EMYd^Nt>bEfLXQk8ffI0?n!W+R45xOWzx~U+hHac%QvPR@Ij&+AehQ}'
    'sjr|jjlMDP)~0hw6$WGqD!J-s7I%$8+DPZ33?Dq6>0i@uix@EgGFjB|4zmVy3tslEqx?zf*$)Y4d`7h?$aKg^D(D)XJNzh<+1*JzRdT-Im5)ar'
    'Ei~2##y9fs?m)2n?<`tvM>xJ@1s(Q8?%gn3;wB1G1nuem&IS;T!SJf~anJO{>aG4U-L`|>OC&Qnmp>}6>ub1Wt)Sc7l{CnP&5s&}#*e(AT^_J2'
    'Jz?s)%}ayfEsO|YT0Y|4#^_K*VEOMn4{^D`<Nb%OjjE@9Wy|Hkm+{QdnOhCQ!aHz}rdM;`0pmfQ-7$oYUVI8`6r4PNvb7DA>$vDmo|MY-g1J}t'
    'ml+UA6|Kh#Z3#7yW!QE>u7<i(G605o@wV#l(e^^0lpI3U@AT$uIPOkH?J@OxSm*_qr91uLrB9)&Ay9lK3NzN?c@i-NR-<raNl9)c1#QgD{$a>;'
    'tWlbI{gCDhDEQN!H1=tF=du!%44$$Fi%Aqj13TxH6GzJEF)_(0L#ske+1K|8!{8`*RtA{EoQCU4KiXTBL?C!Q_`VY8?m({L&!3SbP-91JU>LrV'
    '<8RMJ=P?-MWXd`k!jxP(AB@cI)gVBcVw@;inU3h~=olh!_w3(#frW4#-!NpW_ks6e0Rck;2}cwDp9AAK?{mE0SyRvIvH{WL>f@22%3gW!i6YGL'
    'V;m~oQ)L|qwX&4@wLP}Cr5PB-#X*E;CAQU&dCoj;#&_iK!TpSZC1d|)^yjJ05FSdK4;RRY0o$;fPCCY3BapjJ=&>$gF`8<UwlslF)9({jpg=38'
    '0?;>&5%at$y)AB0^VK8Fm|OoKCwISGnLO|K=edNaGL4pHS%kDN<C@Wse8*FpwC7>A7$-ROF8T(12$4D{=69})VoFFbNz{j2bwsg+skKtVKh>p}'
    '6jgWt^Gcp)dvDReJU+>Z#f3>Z07IwcF%aj7O<p95@KkuUgPtFZhFZ7*NKDO2uejlvi$dAj74%AYe1^${;Ys^yXOwH!%!#T3!Hh=<TCi+kP`qHo'
    ';i|vcLD5h7UMSz-)fcz`^coeVdvxKi9gP`j_>B7W{Jx&fA+koGo=10d7$->_E167=KwJss$G2NAn0IfP&V!lgwMUd12_BLH&_Mf6q$)&U-M{&E'
    'wH&DS(_i39$Z!c(G<Y<+rr|0t)RbY+$TKdGGswM*a{MX}{4th%GN2*O4sQL58>96le+}$y)}O92iqJ=(Sh?`lQ~Zdp9-XWE3RIyBT?kY_s}#=a'
    'G4VGjbgauaWxOmFPJX1@$$sb{e&dLrgV@31>Os&vM@RPf`w`q#1fap#(hPBz$U9*l3NSdoJDgU#$Z%Iho`tOgXfw2&PfEBs!0qzj@X|U5e}_8x'
    '&{1+ZQFyHm8Ml13Klcc@jsjIbE?>I)3G*o2v1an>t|gJlxapCNlav7mWlFS>%>Uty%msgiExR&b^fT`BU9-QM0s(a`4~xPrxo)Mj=W!OlWKH+z'
    'cjPr0C{P-sE<4~APbw_)p2>YZat8h=6&32}KKt`bYQl_j95$Al@BWq8ILwobN1Z#2V1GMtskve-PVtEWfnn2{y+NQ4JYrxisnir;?Q$JUBbH1*'
    '$s}6bs1p^HX#D~6`#mNqFy`Xom2$m?`!u*Cn$K{u*BzA3vsZB1x2gO0`HBIvlvwfhcUlbkBe}B0@U)tufwAgOYCPG#+^?=6R}1Nm2}cNJ$)Qp;'
    '4z5XHBj;?yXfEZ)(pRvuL4gl58Z=6-We*~5p~`-aHcJ17^Ilw}02qz!fDv?IJ;L{zd<WU^dWw|w)XzI*_MnWOm*G$J=(itqj|w@|9~9&xb$uN^'
    'K&*#3+e6bI6sVH+zu5Wc4e5UVqq1UCUg;3Qndj_}{-EheZePh6(lnjRCrYR=+5_Z33I4K|+(s!SNl#DC(gZO|ArLQTy4jMQU4kFqoT2OvAp7Xg'
    '2$<b<^<j*{?<y9!0}N-TtkubMfP-}kJHGdc<Uc^y^LTthq#ZJ!HQo~jHhPK|i6q_&){-vU0I2Fq%~E%$)j;bI_32-evllWeP=|nHu}J0|HaCID'
    '@c`KvsI~Az)Q1Pr;)G3Gg_apQNT)Zc+{Fplko!1s1CT1P%JQYjQ@jVIcloQWfc%=H8k&=@+|!60o6lGX1YU?z);$groXm1sX!rO4thaJ16+3u7'
    'xBu`Vn6!1<M-h3R@SHKZ3k4{d<8cagX1GO8EMev3a~~51M0yfk90C+fc}PYbjsq5s<+a#Z(Fuol>*!n_kPL(Cqq;H-ge(|8npq6YWguk=`8epy'
    '<GnqenCU4x52t+M0(9RmoiW&tH4|6E5VM?;ea=%?s-k*0<m}`;W&<gnTk38c0mKY;h|&h01-?5y59~aDVG3$<9e)HI*l^f(`SX6pIQKybRN{sA'
    '`)iaf_#>)>eHg$`rzHmb-I1BG*Eo;q&5^$ckZ&|!p%XDo7w?hy*RgU2y2OHmObLO<^UfY#vQc8%P6xmhiiZ|-_i;oi%=qfUHVQu04yG0%v_%5f'
    'UG)XlDo!RA#6bP4_%t*|s!{*Eq_tTwYx<u+S?B(Q@%Rkm-BGmevwMgEGFz3HMLz5i1v#D6N%as0E9e=I$sfligAO#d7rDY@V`job9Bzj&iGO;J'
    'a_pfR8kiGYt7D5yB)g_gT~N?r!L;4=fpHsHq&d7>#J(jCS>eJqxqwbZoCAi_Buq-3zE0U~Eg?#uVNxUU2)QLV$8T5<TE<LaB8EeZBL`=3!UJq`'
    'rLvPo0*hnq^HFN}_cPUiVZWW>w3xHv8|sn^7|Q;r$YZ342C4Xz&B|Zs@sHh;c!}T(lPfuA%qs-u2VKTMyfw%U`AX;W7(Jx13pO+mC>IzoJj;ZG'
    '%jcZ}ZCyH90^*$_edk1u>p8R^bU|z3uuu`U2^6ob+71-x5ymgrWhR}D-jL4;&!2I@*rtvyq2@OnJUN<quPkLccsny@6@?jNm_(3t`Ry8(@MF3X'
    'G6sPKMktIXb<5+D5*L1>7^!;n?-A(T;H2`pMJrU!g($U0r07iQzigj*5I?=Ngdx#k|2y6z4WndMQ4Cyj!F9OnY`r^N*D>{VSUC%m-jS9Iri6n|'
    'TrKei{m87ziL^MY-gK7MAX4~|md&Si++H9KVMjcGq+<I74raRDTJnxjdQ_nms}tSZH_JUMD57NJbTT{wyop6yaE`kck#KqrzbOJL%}2=fRpNyV'
    '_0BaQ(ZzZ^z<~P>TZ2)y)r!nn1r)hza%~g_w-MnhZ!ftm6jK6nf-2YJaio_L0=nVUQ{wIcj4Y8Xu8WOFlWX*RUJbqI6VD|Z0A@0*tCBw&hpc?c'
    '46dr>br{%|xmtcWcYqZq^1IeU)3gmEMz~x=)_E&AOYYNs2_1h**}9|0a=1Nclc*ASvVi_2)iSE#tOIQkV@}TJH%~uE4Q|B}gAJ`~uYm)3oVmFT'
    '7XFOziu)2ePR!s;uKBW**_=BbG*>CxU%{8qmJXKrr5ML60#449cAN%hhs=vHeG?NL(zis8O3DgqAe<hJ<(4>y31PX4*XgpKV|M{(6YXry?N>Pa'
    'rbr2*LSJ*_#2I(j<P(K3I9Y*sRDZX)c;$cxmSmKriGP<mRvN0RZq2>=C5Glmh9ub3@D`mO3et_^e!lQo>n8aNq9(Oq&X~rnWel(Bm{-vjFZ}K='
    '`?OHqUd+nY9iwt}mkONW<0<KE4znbUbvHv@##>f=$pxj!=+k)1G1cyT2!)!vbl6PO$T{NZx4j+UuplBAUBO5j<QIA^=VNfo3CkBvTDM3<ou>Hf'
    'UP-}ynr3syL*<)=cQs@h;3hto1AtT|BT;ON-Sr^MVtZ4Kvj!kLx=h1Pb{B7PEb+DschDwrAGBrLG^hxs8BX%=9K+S`JZ#^peAV>#>Y1#)fI2}m'
    'm=!Kxsm>RVNp-s_jGX11ov%l(*s85Wn$sY)pt5v{yRV14KHJ3LDVJeH#@c$e!fH>F2N?W^iQP;(ZXAl~bz~8TvHPWdh9c*t9F!YGM_jTPcLR{Z'
    'jLv>a)m=ncR5?Nok}7-UKuk@;*BJMuWr1}@sg8vjy}`#LwCn(AQlScuEe7<-@o-``3=*sQ^WuzmKLRJRKsnG{zzgMSE{^>PgXQtCh{F*ERdg)t'
    'IQA!sjgKc;K-}O6eINm(7nv>pYg>|4u(Ae$vNK|4EIR?>F;MS_4eAxv2YZynBC5(WYZR3O5v6ZtG2edhE23rXP)U`c`fvu5<%A384C0kfz6TiC'
    '3kE#;bCvU+Z!%7@r%=>4Nc6F?3B#)@DfF756gXwkq`Y?^id^AH)(ljcf*t$=CZBF`d#@*r4)Qh}=wYy&RW9PLBaH<?F+25*#LhGs3<W-wH}an('
    'Ml})=`ZUDEDy5fjMT>4_F#?cQ|HBg=VV^cCn}Y5U2fTV{s&!UWAcJ5pyUGNy1Trb>-=!hbFqzll4dI7(r?>cP%ny@VxF*+}J=bFr0XF2-3nlqb'
    '!zO!RVF=tHpHj;GD3l0QEQ4$+6>?PjJ{ycAK>iJ9cb~@J%n(d<{wG}banp$_^7G@wvE1?ZWu#&Z9KAP}X<`_)I8<eHi^|O8+;EUx7_8VRMTtQZ'
    '=Ha3uGmrxrwm4Fl41}ux1zJ{k4?D_&p*AXF6M4ktd`RTFQ_m<F5(+|0OglZsT+EI2j&a3j*fjzaz`r}qN{J3s3FLy1$ZhofIPN+NA{B1gr+(bF'
    '?|e{sCftgfvEQ%qdX62kAmBPI>G%XTSx|L8_K5N|)EY?=c-WiP64Cv`=Rl0(9pRK2B&=3I10L<4S<Qtb!R66BqvUUGQm(8SVFZj^`nu#9Wy-QW'
    't|8xC^yv~=As|((qb_fisI0L|`ij%18l!^4<T2q*Dm#H34+~>?QW#!bRlYM{QCm_GYhKtkg<)QHiS=1#7i_iKtyq-^11H$qj?PI_c(s9*@{Fpy'
    'gN4kPqhK}|OU^N}M~}d47M=mjIPw5T->`z>y9`tWZ=D@FX6hgpuAnvsIJ3Od?x3hX{OKKD-m}F+*~A+NM)<y*#CDquUQjPy2G6)Xl=anMa$~6F'
    '-3&5iJdp~cN`Glu$xFf<s9}7!04!cC*;9`AsJlZgN#RIM1>=plqMHgfExz=I{o4!5Qv3KCrdkVSiJAwLgmt+tx05Z6&YItKL#u{_Du5l;G)e!C'
    'QxTpOO&Nn0pH+;~H?D0kQ*pczgsZ~{g__Q15dpUt77MAZVTusy0UK5z@J2VwB|2oOcydj~l%&mxIk%WdfmPX4ZD=x59Rc%(*(1iA%e4g+mxXkm'
    'ZKQn$VBJewMY93YV&b(^iZRkYW->$sn|s07tXYlVeq7yrncq#&ztAZeiIu@p_LoVbe!yXBrB$20hPZn4>crtA6?YM+Cw@j>cQ*Z?)?}ls%o>U0'
    'TOy}^WoMci3zD{Vub%le4y$h1LL8FJ-EEzY=9tgrsyHlTIe@c@e~xcgrYMENEcVTOVa{MWqm5^E2o%VM75_rcJhAj#WXKe8%aBs&7v=2zVQ8zW'
    '_@fDtbk%^ZSBLcxukA)A09sEN{YSFC`6z~b*1rYx9AG}V-?_IJ2<mXd%ycZsboj1$Pd=cpDuPFTA9PhzT`RcK(EuVv?AKbyuhg0SdOP@B6)j2v'
    'Ysihn1vY{Xh~u@d*#X-qiB-~Y-HH85B@400?lFoRMz<ozfJpx2QdJIJ6-ZSP-42l35Fb7Y{hOfTexzgUR*q4yrnerPV^==japOZ#I2cKJ)H+Gz'
    'P)pB6Z>U~3x?{#_^<?NmHMhu?%i^IH?-2yKWxqhUc5-27O%{6+?8`Y!-X^HbBI>+K424Z?oGVo3dTq3xN$XtSR1<~;2EIs8=hVdry`S>=uus<('
    'JVl3a7z}L&Qu}Fp7*3<9IhELK{*l$g=1|lgheU_`K&wi8r|WY<iKvbsWznjk$whY)jHl?i_}pt?j`8XOw5L3izTYQ*9QfhR91EqG5?ygFpj@E}'
    't<~<!YuEu|qcR8+R%8mrbDgEXaevp&DEeA<lUpN*=f>tssF>Y(*icl8)nf(rDv=}#m19ZJa2;SbyyQAx4(J-k;X(pdRGAuX;(&2ur<A=8!5iH4'
    'D{-f&o=$3yEz+3jViC%ZQ8eYaH(5HFie3hcX)l(doL0hsUjfd&5iJ76h|$OT5E4ZZRm6zh-lr?Z)G4;_iMtZ2I{Iu~>s90vUVnhG_8jJ!!a-T`'
    '7(B-xkmaU5ac5&SY0ZaJG&nSyXinmBcUU3LJGUYCT000Z^){UH+lhkYI*~(k-~2OT#s^M|oTU`$2ZfB)F?imRol&@B87ZL5kL9dH-J14>FAPvD'
    '3AM*rhdETs2$NOR&WOlL85b^>#9MEK88%isLv)F6vXeNMa&Pv=h{6ir8~*=2Q0$hWO{^%lH=7*e7XF%hl^YGI!5n`8(q8O$LB8l-bjlw_TxiWG'
    'x=pT#)PDb!+KDC1r{6<V1;zdtS&1vjk~2JKZ6LYPh3cr>aA%KLr?89;q%$UE!u7zuSlSQxkECPU0ZkN_BPu)8t1n%sAk)zgDn;Qa*xJxl!AN%#'
    'RfQsTDarl->K;=|a0x>sZOyX+qJithWo)Qg;k=KAF|Zmdhk)cYDizU{f0}@lz*}sh2aBCL^M#S8o)5FlMAGRl*FLO2(R%9->ez|#<I(Z3(wW6<'
    'nC`JZ=eV%~IIIbs>RKSrG0ogfhmHU{3<(ALxCTc7%eM9bfwmJ8eBo*qEyf&?&l=WI|ML{qFm~Iq5LeMC&Z<CU10b8ZLm$Ycbmgwq(jm~i6{r0D'
    'lIHDR!GQ|=SX)kDZTH0IuE`vLlutxv4_r7wskZ`{U?l4+S|YkDFqlikAbuab_Y#1asrsJ=m+ZODNZROHuy{7l*u)8Sq>xb4E@>&Qvs*RraLweM'
    'quVkv0dqvj<g~`1$Y_T>GVfWZMW=j7BvcOIpmT#A%Zwno&mSQ5_oIVK%lv4~gd$e63u`hbPa$TJgCe7+_EMe+6!%kBt13f9^6!=_(#j<{-{C?H'
    'io024UwrnX+;VcL5Gnr9R|N{K(>IC2erNYOZbVa^#l1ox7_lI9GF0mk&CMyB$2t5F0lA`7MJp+w0w8~JSqxMZ)6pYzeKtp4YjXN-j~d!1%|?R*'
    'Yk>hCJ%!1KeqrfPiIdP*(KL{_#k4p|kK}1mlF^9kmI}$2%yJEa6<r){-U~~Wv7uXL?4m$bJZ;oadanbb>f4d3zIqq(w;c|Gz<!ZQ9R!Id$X1FQ'
    '<IEjz7%1M7gVU*@f(HQ==N{`)v9zc*QK`Qzz7Jl;7Cn4%bi;Fo=gkc<6`g`4<Bj69aM#l?a?xG-TG1MVwHRXUnohcrtEfqTPGvUfZsxb})BsqL'
    '+oBwDhZBb1B~q88fE#uLO>-E>(w`%@udNX?gktmI`tKf=E)SRy-{|!GB;MHVELQWjgMfw*pgFMQ>8&vksw|s@6tCX8pI<?G*<)Q)y9uk7bFKMS'
    'k%U#dYdPm&UvhHx)_e&`yUVzrrD(eoGGgU<>!}qg_lRsZEgT!-REkl0noZKk4ScA01Ei#u1|7^36Zw2wref^?{DR$9^=Fvp#NAzMi2id}FSQRT'
    'm47jnR++wB0;=*4VvRZTAJOCzQf_nDS0zxVpj=)?xvvd^>!u7?u42TxL^^<jfrAA9o-hZ2s<bF#_GyPXo5k$!s^${+4$&As+TtX9oz8E%zxwd='
    'em;+HT^+9mKN0}b&zlb3`FHlO;|;LGSDHT(%N}9?qD&TrPKZ>u?^n2dVU8rn)6%|Cs_AJQmoPZSY^((nn-655EKTbb?t#;@q7j?6$aaEM$i$0!'
    'c5HZ5YeZ~=<ds@FKqv^h4-ha+m}OnF1cXYR3xsueM?UY%s&A0OB2~Z8&)9Z777SO1!~i-pylTo++JS)7-0aD()H~?0@Z~vAhl!kKaaB>p{JZ2C'
    'Py<KaB57r<;Z+{N%F=I@zeSf`$s_eZW-WUK5ir}B*~zk6PK=~r&p}UVTLn4?L`&+z7&kgy1$zY-Ja4#z8HYlpk)PL=B5hHE=3=RZM?BEoj>|_|'
    '0TML;&Fg0A!n!pph#>r2sR+<K0t-${9!3oTZvZ-dgMZEbU$M+oN3Kh@CGr_E?l`Ww_@yGy!B|qqDMV7!j2|$EP^#Ma1e3T-G)iLKGEG=0e{G7p'
    'EK=CrUz#QPR_|N^f#eS0$ZM%SQ2cmQwJj>^=RI~9iC=hSHw)9S3L?dTyAzM(YC#~P_?PI+s%6Au;Gv)|m57sY&t+o?0_Uv@N>{m0ZFa@fw&<Cf'
    'i(mVB7z34xo^GgBv0tU8A`vQk8rtZ@$8fpmeNb?%$js;QJ21nQYC7##O-0tt8$>fswDr@NNF6R?I;oIjs;cI^?53@O3&LdGyf@ce`xZs!<eISC'
    'kzWJ07Xy$c(}^WdeEXg89ymlqRMQV1B-O;wCOI!=kC)ucu+*O8R;Ws$F-mN=4ImYn&Ec>EE_!8^ei2;kgHu-&nNktDnP+Xj?HI%~vF=jeENd%9'
    'd<7OoNPCrql5_md{?D{0X%1zQoC!&F9!&nE0s&u!KghPNz@1~bVEBLgv6xsxJV86&%ia=?*d?EITY_GoC03W#dBb&_B_j2$S~<8xYVqnSGNv$A'
    'ZN5@zxr5_K2XrcekS=CVTVPS*aP7|53N1H=_GtXG89PoKS;z3yzj4`o>UnSUU7<V%j7^ETz2m9@iGrj_{iDUAMLn}Hn|pKNBv4~E(gif^0(%aI'
    'qNi)rKf_^?+nBKptwcB(wSx_9j$N0jw8q}RZr5BKZR0?&VX|vaY-8>gPgbr)vTU7)kY-r6WM?m?jfk`s?{eyRF%-4<p1t`(mBKe7xfF#;TX{F!'
    'hFfNJ|9iZ+{&v|nART&aPYJ{s(kiiCAiQ&yOBL%Vi^K)PWUi4a<?Xkd7A2b$BIio&*`>sXG_4AJ59fu27u6hc_866eh>J}T(s-d*{=5a2v??OA'
    'h9EUG?FvUNJclsQB&yF7u3Z&dTpmdRZae;vK0c(*V7VVVpDzr%e#l@^<cofgQKtEKl<fZm3QV}~!-n#Uxf{)3nGqN?6yG1!Fj8^+0-);4RG6gZ'
    'APZ@_N7|4~u9l(U<UW!Z&V^FD%+g5L%XJB^jNM>UD(xAs_T91V^Dk^uR_l{y!n!seKBY~6RqghewZ2ixYYBb0pGtgv{|#peqbmAG`zt-Rd0V04'
    '1gti9lL0kF1;Z@j_6ftc`H09#A|Ek_BxVHr1vCmLs?(^>UP7V}b{bY?lIw_Kbw-i3ygAfJyEq*@hhA%HIo0cj7E#_{IH#0eycG%!k~22Qp^f8)'
    'u>!$<V}X_&PO`86gvqgehftg7+ETf?FTIjW&*_tY^^w`#pL@2iv1T6$7A+$5Mr<n68E?IG;5^KYOx^g6=x@5>rd`@|72J!BZ|&nyk(Z^q3{vAs'
    'NWdYqJ794?^*fjLr%_3upp0WlhZH&`I;g~&GlgQIl+h}1#nKIPsAG=M6#6erX{Y9TSm{MmauaUNt%eTIGkqM@?<BQUXI4dO<Y=ijC1WJ^rFd0^'
    '+8LR<#~NKp(?{G6lya+ny-@!GI{x^8XF8(-&5)+BMuRuqw$wRRQRxWvCa*=JP!)w>Un@PdX3{7URWG3#vzgQiLTMUBdwB(ASz(Y^AZT`~mQ#Y5'
    'Es8l!Cszr5A&WXmbve9is_Z^2r<=uHiL`rB3zDMqIf#93>0C0tHd-_!3`&+8fKbTE=t70%M}>91Bka(@3SL<Qtf%G~^aP3kWoTFcX)?v9_R=B;'
    'K4NdaCa6dNTx_~F@8h4vxW<_+T;g!q$l_u^7#_sMB>P8~_L)^Kch%V%B(YI8%N&B)7@&lJM-?k`DIMZqWWw47L#fA8e+R9D3s8r1@yvAME+6@Q'
    'Sx~~g4DV709gTW}=8mxMApz<1OW6bnPz#mUPtxQ!`fxsKXXy#YNlZ{_^g8o9ZcRB6P{?I!%YptjOoP!VD`vyg?iu~xIfQFHz%jAcL{v4aqp|2A'
    '+Y-<H7jsMv#!)o;Bd?Vl&k}F9XeRV{DV6Z*vM1z<yh2aZM!8=pFm^I{Sj-pOy(6<|!1~4pAf)=|#w*%-OCYJB?s9<as1g)5#dwwQ2ejgT55ORY'
    'V4_kV?Q+T_)C!Vp+tIXPwGiwP+ic8Y(@=_^tiW1pqZfEme%#el3=Lg0S{kooMB_>K66$A94VMU#VZ@tKiV647<7xmHY?CY937!K%$U1WgMp2;>'
    'IrrB2#iaebFXsc{C25A3f5)3fzsc2{Wh!(*Fij@^98X!+qWYQRV^+_HBEqJPp1@&s9a-6YjaGu`ERA&I3udd+Q~A)RG?<CM;aOUyZVxoHbJkTa'
    '5Hv9F#P4=DF4BW+1akOGx7(@2Q88|x$KfW;r|oj%@w=r3yE#ZsA4WHl-LD%?JKAWrs-^@7z-7A*?t;ZnkDl|2cv>oQoK)Afm42#-Qs5X0B2MJI'
    '_(z3nQ=q_Y%(0*uAod03BW<D9s5AB>0xj>mIyfac#2hU%dbsn`q{E#{qc{18V58gtf(=Tb*@o|sJ*CxcT!6eBN`AESyNdh&wU@C~Kw+y%0!+Cf'
    'w*jR$2Z+i$X<F9so*e60qk;<^RtJWb&=)JGR;JejEZYCMhI*DE9Y%VJe<ZfDx5J60O7y|qjwmHK!X40=Kx;$-i9I&p%0bo3?7bbFY~f^?q)7k2'
    'dw6{rdXD*+_wz_DJF19YY#$m{swm+?nl+gYplo6k^P`~-+zM%pfpWldJN3|fPR7;7?P+;7cE$pw)S$Jk9xG((I>eVZ@m(448^#%9f|zS4;#<>6'
    'UgXwp#5#sLNWM;~FG=5SA!U6z&EF3|&io;Sn{v$!Q&NRvE-6a+#N8Wk7IN556NYs;Bwl+Qm+j4mJp^-)cuOx{_N<Pi=e$!Ai!&*7+QX0ya(il5'
    'cLqcdf7AHx7a%8>mGWWTuOvV++qloJP+|*1+wWZ}mri*SnA0aLN2?YD=}qV_B`bON8AT1i_aJ`~Z28ZAerkrnmime1C_Qe^p}3~|E(&P_MIDO^'
    'vxu$1Z#_gw>1XOT1OZYD%#!S*XfGBb`~2x1)ilYyG~3~!ae$%ch#6gPQUL5>btf3z*b*bjolCIg$hVb45*2@z@Yq~{;6R3yBo^|T*hE}Y%0ciQ'
    'A6}Mby%3^AU+N#>dtvigU_64Qp``&f#;?e=2iB|%IslN+S1b<$Txn$)EK#Y$KP&T4CMJq{=k2DR#tSvAIW6Ebg9sqiF>OB-SN>(++`5<<0++E+'
    'Qm$Y{ds1^gPm+rJ)V^*H5HZzp9vVq7eXLz-tF+y%tYWEism5)7AElNlXCi@m%Fg_8m<>NR8V^2&6(pA*rEL+NQHJR|bVD%1u>QtlBkbkN@_|HL'
    '3P;;WH7Z_qB(`B$bd^=C>=T!OQGvD6Y60U8%W)I#f@Q!rntFfR-#H>)YOcT_;_&wTEh2{;Y{VQ(iO|gmUh~xRd`Q0VUvo)TyhS%#<lAMpgVF_y'
    'qavdoEVlEmI#IV@t*)#VUS+cTP6nXVylx40Eo$=buYos$UZ<uzOHvuCqEEIsHoKKV!LfCVsu)2=m@*ru>t6Dvui<?J-1<*oGAXuvwr3eiZ;#=?'
    'B7XEG6o5~AGDd^$=WH&0cVZ>Sx7*q)TnB#0R^yDt1bE>&sV+d8U&FP;ZYcMweuFP>AT{mfO7^_C*6b*QN#nrGrvgh$NS8uJiR$jE`67S*6S!Cs'
    'hTXm5wVI-s2nyVY;pP}_e2(MR(n)5VN789|m@o(G(IVOch?o39pD<~f;-#E*6jBvn;WGaU07DMfOGw7Nq+ju(6BZdni$Cm}JQH-w=RRfA2xt7w'
    'xsDTEfu8igc|YB4y|!5*k|adt%3;`yYIEo#mixoTRkw5z=T1jHyq0G9fGEFn)0`R^D3Eo<7-O*_Is~!<i9V;u@HT0o^r~}|k||6ep(jyarP(Bt'
    'iX^1h<xy1yF&j|v{nq8l2r>A}*R>y%soei9$tn~Y#&KnTg>on;DhCVFO$`lgwv=<Ef5b<yq4I(8dfm4W;A=|f6Q*V>0+-!O%RNk7@vYLXVGCUK'
    '0oD};yrBB?o+Da}^aNe;(7;(xc4ZQQ-H|PU8ITRoEiF4w{b?z!iJHr}iU+a)PgON7GJWCsYf|o8fMj!-J*_7b*U*?%Kyd=!SdX@kZ>Z8+#F93N'
    'iqs)`27y})F6ov+sVp!vgJ!YPyvUA|i4|9yA`_b&fLj{lTS>6nFk;#Wi#KUch2D^&aQ@X@B+}2^?1rZEc~B!pHj1zK=9<s#*AaCLGg?1CgBmH^'
    'P(@{?*2;=>)Fq;&GK+HhUszlSE4DRkkLcXxQSuqm(xz%u3~7G1;x}lh+#W%S`|H7@UwC!B!s7Q=tUz+2B4eEfmt^`TS_UN0j*&R^O)bNbtp91I'
    'xJwiJ8NY~GP#+*00$<uds~Bpf?!&!(iH&V0x*_0xdK;E!Ge{L>{1?r=viU==R<q?F0G{Sm>o7{NX7hbz2+J_(oug2tEp9syg-%|FLuyO#rw<e|'
    'QbVE!Vk0M(l`3n6X`~Ui%912y&PIaBkJQ<zWqejJHrkjQ@zs&U*Ra3=WYoh%E*JHZcAg|XNjbaf&ms5tRo#vpYGWg3M0JB*s8IQg%X6Pygko^B'
    'uziTE9E+?4HJf}lCg+$1%AQNV(Kx92tON+qW~vr<P%k_UUl`P8l)FmhqA^DCYnT}k>N8rllm1kcA@srkkMbH7LwOJ6Y^xz?m5@DhGC&@Lawb{='
    '4O?ONvmVzRBQGMm`68CN9JEv$lPQugwR_pi^xHj<*nS;%W%OZG<QBH9_zBmnPYWom$R#)6;DLnHlChESs%N>^FpM#jXK^jHEa=D9tX|Jl9Y)rv'
    '*txc#bt{2X9+i?Mc8GI>^AzX+3cR&2gLCpn2Q1+!{;1^4xQJ@S5eBPru9rY*tEic-h6Z2KsD*ZK<v4q4Y)Iz;+<*rAsyz3NuK9QSs6ycqR0P@@'
    'nl2u-(T&3JE<ldsyjB$C36mtsf3vPB(L!IH&jZd~P<x`oot#vfGfJh4f=>03+l_&mcQD)VuB|6xQ(jB;vlMVHvd8j#&KROvEOg4QHB|_}ht);|'
    'urbc^Wnp>_`l^bf*^`vHp)41`U-mK7l#LeYbL9_Hdw2>_f*MvlO3kwoIeI_B32wi$A)C!gF~d|Bg?HF=kZmS^gUbTDXD-2P@%JX-4~1td2)6kR'
    '_lcujF4O5aQx7@X{!chbVs+0O+zIP%j5}5pr?R?@jfWA(M@FV|gG_a4&Hnl4|KNtF{O<RC>M%z(F0?Kb=ZU$1cN#f&)`VmS!yX-ny5Lzvty4uj'
    '2Pz0d<qQt)PNOB({Ia$*efYu%iinM3kG_JUol!NMJJKbbDIug}entl({ZfXdR)h5bNYsI$9tI2L8y!_+9+<nz2Cxz$tpnH$xaMJCxV&->_^3RE'
    'D%jcws=iobT#8pT&L6IkEH@nCn#trtM{IDe(~*2wZt{^|gG(e2+lNaywd8?uO=-qetB*476*)VzCf515{1QKnvC8A);B}8-T{t_Fei{@h1;1eS'
    '=K1s!S|WPZO^H4Ygg??455FGcA!J@n0CbNmeb>2nWa}zWPzuSRyg2vWi-nt-{;G&v142%q8yze)jFzb3+Eh%hJ=ke<-nPh+axfS*RU|xdtzolE'
    'U!oP{5nVK5s_iE7>JVF7UL1YuY|^1Vd}dCv#B|tr^gxw~iAvBRVuP=ob6H_a<`|?jl`@3s=AbyTnN3wR*S*eT@GEt;670vX6y)pR`-J=_mwxT2'
    '!tt)0Cjj@1I3B@joiq)FJo(9BjuZW>FZ&NrLtiW20b+;k<FO!RSkmwh%jfr3)gO)|n&eZFc=~iZ3?{?i^%?s?I<lWigpw73LYw$i9n?FQ|2ljj'
    '&YdC)l0P2W>#B+*d9zxfvggvl_7hHOQ~by;%7QIL4(fz|LNnjYq<6kQ0soU%z;U8l936-a+Zff%0f`$NeS8op3~;9IN9X=Xpd)25OYiP!b~3`&'
    'R@l?av7dPP1IuMRoh}ckZ?6HS$DU0&9+MMy49>CnORq)c+%Q)(XT9w|U9_B0R>}`|bO|8CincW6%CKut*^HANsO~yajuEjC{hsOW%OQSApWgl}'
    'kWuzFa2EoYhRx#>fnfoI1IdkTVW@~D#kIUYY|E^{7XIz&@-FpI;zM4M?d3{gQuXHyyy)PAl-N6vV=Tb}XGML~qHNxuy962X^P0&OT0W{40-{%<'
    'q1({R{XW38a>#N1w$~IRzAv~kh6|_q2fc!E*B1-vPc*5uuj}kPAlBhO+-EEUbto*P{_W9N<2bx^*8LH?kZx((sC^!3E)n97Ua`E=^eW?~!MwQb'
    'SgnoW2yLu)AEb6%U*c6G|J|vlm2^q}e)C>)`gVY5K0DS7nf{miFoQvJ{}m|j=qnyTBmqlhqif89;$cIzC62t2i{Ilj@<7X3;uwCHkXrx6*}`5X'
    '3a!%ca`3K8y!zmx#2k_b;7?STi?zyNNLS9H^?+Sh3c+{RgKQEdh|Qs84WM%Y_t3iexO<IN5_~?9kX{a6E{(8ygd`2}(OZgy`PKu*|HyNBm&j3h'
    'B<kEVHXkkXW^u6c*%R=estSBosfS^oGjitJC)<jISNNw|BEFd={QZ-fbA9?eJi=mC)LLHX2w0BbHj~$YHdvH9ADFy*l(CjA@SxzEy=GX(PisO_'
    'H*so?bl?AY`t${#VCe2(+xEfiDQ5-OF#6$cg4Im!ZXsw_kW34zoX6cEKHmL-)@6zw`LJp^`J#ylvh@67Tmi*hf(j)H;(GYF4BS-6pFs?i^nr1N'
    'e51j=54S(j*};bX4I}hSSY#w2myHyVEPfL-G?(JC`l@|kJ>FSXl_X|gSJlrbI1%(T8&h=nAP45%?mJv|%zl0SWGYbpcU;m`ioOHE-bw{0N*#bB'
    'Vl^H*r#b*i7iW)!sVuo|9B0U6Aveh)9a*I82M}u&!*WC_mChZSSeiWsCz7<F;SzVNgZYDtjq_G5_v2cnqGvgC$Mz4XhWY*yjue+wb$*{z)k}q='
    '2=3}S&T56KN3Oun^FC4u=5@e?Wf7vr{^0`mub%*G3lJX}MN;&$Mi}x^QRwAjM0q9V!$<YbT6+C}Q;>eb)R@}E#%ndiN;8KV1Ff()lRW6*721(G'
    'V>ytB2@aUS|0hk+0dzSoJlU#AgvG1R;9SF;!(d^#rGSm-bs=&39+oscjfzdEQq{fG<ZNjad~C%*p&tC4^KX07YO{?LjorCwG(AAOYCd7|NcQYp'
    'gWLTtpkiSp<H81mzg#+YHpS3kVM=x(EQ0Zx{zxio=wGm89?@p&JX?kvet5F~!~cTo!fDhL36)x5q1-hqr&ET}g{bg?PK{yMj;%^qlHvD$@%nC2'
    'yr92JB~NZ7ehcl3vCOwC^$_BjhAM=36B9)bZb2i+Y4)9N$f)L<dYMJ0^)NmYJ#Npbz70S%6{{I)3L{!jk;tp;9i=XY!dAm^c7fG;w=S$y*7hdP'
    '!5u6<Z3d@z^ljmU6+=RCAlIY@<H)U8(;i6C_)I$F%p^&8Tb+%eb64jOl-3m3qKj8!@nrWg@bo|b>;L}OkLackx(l6g{a|C8^#lBUUBW)fdbQ_O'
    '0!UX}yc)ww&k5Vgz^J~dB8x8y(L`I61{t-DbG_5;=71TAJ$d=_S_t+nI^c1!DU#a8Pm<dIcyhzu0qqx~U~4s+Qa`G~bXj(f!F7jF*{2&fzQDM^'
    '5<U@+O1hR>t?8=qWZ~izL9sV~L{SVQeEzK!5OD5DmnE&(+7K4W<$W1r7jaRLLdS2u=g`RY7$-x0jTaE+OK_I815V|}2d``KCe+KrA-^2Ta)l$o'
    'vl0t0=14$5n|qMezy_2q*l(CbN~vzok!Pe&<3vc{G93>7f3L=Xlsk9CYHxvS?{G)OQNWspi)`+Pqml`i!1>%ZS+@n3S_XxC4}e@x&D)+eso&+K'
    'toTn1dIUQaGt)l*c*!ShuE8MMo0L*gm3T#dvI^CGzl3s!#c3I$P`c;kskBYPLml>X!WZ~3kYcV=XRKO4Uv}8lzl0jnwDx`t03mqBDm~}^NSBM?'
    'cbj0pr<R^3WKwqLF&9!O`UsW@Nb57LKLI)ZST;WY614+3M=4PRsF7l>5uvDGuo^i=%9><a>Tn(F8vX!Nt=U~bwiXLtp<S{ClK~hNNneGOj!efp'
    'kF<^Sj~PrP$wP4fC&>x%VXWw9*@I`+>(Db(nXD|o#h&4c@fN){1=~EN*b@%vy4{3-r-b_e$#|bX6(DPQBtcr-hOJbMsO=EaA(fQ;mbjlA!OI7@'
    'Qh2~XQ6)s_&u7yk5nOvOcDiDNq)Gp{#bV@oj`&AoT1yso$mhVo#j>f!pX#vo;euWr&X6qEw_M_}hp_Hb6cGQwp23G3p#au0&r*ZtHpKDTV{>UB'
    '%nI4EWy6JeQ38rwcWPy5;etGectNp|u3yWW6sY=WkSYJ_bYIt$$7fUYi;{X5*Uxls&JmDj92d;>?LyoSLIU+Dxj&HoKg=Q>p(z2yUD3@l<H}d6'
    'a7c^no6;Q^Qy9*slFuVgMM-c0zXI!eEuFh}NTr`sfd3tvVk=mCp8A1N=JpTw;tY%PAnJ6UiGBD-cVaB+F#i7W7y|$@p?1NdLZIT?>;BA%G5B-I'
    '(8e-g?5y%GKTLQ;+5?83+P!e+YExR0=xASf!pKUyFWof3&@pg3jH+$~QER7#i|W$bkc!TMzn2mf`Yqi|KO!V<>}uM4Fkw9DxGhuFfdI>bzJ1AC'
    'v7{H5%BE-o{jqNtsww6sciBsLv(9+{VnJ7#mV=`A04mnLxqiKyBLlzNzL(^Qt)z9!)?WThs?C|(_#z^%6cVA!=NDROj)aW@QE+5C2N1a=JQr2a'
    'Z(e_2U52aU4r_;`K`brkflPaz`e^<v`<9kgoX-jS8Py4~)S6>cNUzdjrw&*)D>$v6Dzy|l=e~O0S3cvqQqRIP+u@NsX2l}*`&AVcwc7!K3ol@m'
    'Uz2T~^P3S->w?#n$J0>@%>nK>Qxu3Lnugb9$ukC0PJh*lucX9I9iQ`eHSoBQU0RF2HHEnx@{8Y<2yGfQB~E`Jqf_`hegM==T%-$YNPUmS$%+6f'
    'd*=?5&IWC&4P;2IzI?nGOnMw9WcDa=&q|itIX%yfugwB-6$~jQor!wi!L;pK1-~F9wHg%uZSM;EH7LjB_YqNZqZ$~W@Qc&Bp{m{1e;8NMqTp64'
    '>)Jkr64Q!B0QJ!9JT8dz8)I4{x3taTBU5wo+Pvo)$c0kkPC$vFLTlVW;DNQgN*(TkrV2@YGdDX0*^z__%>g9dZm1?;;4+oRH^iJ?vcA%yd%0A)'
    'Si(O%fOd=zBTn(gQe~GTvR*OF-CYnhNF#9PMLV)-MP6YtUTphV58t_ZI!tpMht38b{Qfzj3$XjXQt75hR!hP4$J>WLK7_jOQ;jSxlr-Mx*Ut=D'
    'VLZqxWwJov_H}6yjJC~={jtU`f~EJVrE$PGh+H^qEcD5S-ZVkWKlfqhmOKr&$YCHYiKEA{x<GP9N5z&Gr$IyW29>_M_V78Bo|q_&)xF4I-LK~7'
    'K5i74R8^h>UYm#Car{Y2(gURGVWQpiKBip$)&X%Sq&L+Po+~lrvaFlc#4=RLO4&?l*ep`p5Nkngby97RwdOWfuU|cgWGH)v+>FenECL5Vom689'
    '4~KzV&p`7{VbdN)9v*JMgjg}(N4+Q_xRZlC+%hvgGccK_C)cqIm+lsuC}KVfu!RqICW`jB=Qad|UYDH|zWT~~Qi0Gg$!K((&r}(Q=Dg}+jH%b3'
    'C!QCQJvBPBrS8;ksb!F=Srt67>t)A272F{HnJZ3okS%w-{2J;((4y|x6n4eDw@$J!0GlF9Fg%&E90;)jzRo$HA~GF=2GOKjt3($HT7gQNb>a#R'
    '(6=v%%TMw<hP+SsoS_#gqU!OWAZSOVcnjI@x8(5Yi&Tm@UJoAh5)-vGpuDiAO<exT*`Oy5HMF!+r62cYOtDAdiUzuUT5_e5494yhxyZJbBo3K|'
    'u+)v$2=dxtw0k}87cx~DK4HM?j&;o*XhV%z7-bNOJSr8h`egi!0J$cyiWx>F;7vK;zF9`aK4;zc!)D_ZR9h@S_Z2t<QSXrhNZk)V-zpD#SuY);'
    '&Au-Pim~AW&DaB_o0Q8kuu67*i~sk#c@2&yrV%V@8--@ODbia!8XnZv4idC9!ldw9oTOMBd`VpPc~jH=k=Sz$haF}1eRQ{{>Cb%7Q=a4l8b#gh'
    '=@Q?od%hU@%XuJ%xsIXw0}4fAkm^#xeVYm}TO8M9w&m{|;)msU+hZG}n@Q3rFSCuMVOr}+eYB;bVGsC>`ogszRuWxw#bKpA2#jLk(cV%m4uwR!'
    '0yA~_GzZZ&4S@fw)xeJ~pptS}xFoDKEYtx@eRg-;B^oHWY?=!(lCsMJCkDG(B$5aA30#deo~P2OdRF<s>J!TdE`|7E;z?dc`n=3#mR=iS^w(P2'
    '>3{ss|NXx{0a_N2!lA6#8p?B^7FeLtq8`mP!aS)+?nVl-O167I25|B3#-&jO52w3n<}g=t(0GX<mpuc8Qf&lMuxYPDDC*&uTZm;4$Ir3!l?Bk&'
    'g|AR_=@5&dlYQ-pBbQKWCWYNw)JLWrZz6S_ObV6M0aTM?&VqB^ib4BAYlm8t9q*(Jmaga&NQTl}U2D;#2z=O`mR)k2Iwqy+b~K+k>?1TE2M8)e'
    '4|jg&?3xC^Cy+Wp9+}@vis@MZy!ZMVxbaf=>ZK`y?(k!Y-yRcu7!5wpv<<f`^=SKCK_7pMRNdEZH0hATj|K62#=^oWm;WvxERMtbT(?O|0|Mzd'
    'A!?>8o}@2RKini#FX`Fjlv#RX+qJ}ghPls$*-%$+%yU1CQIfC*=}FhHRNhTU?QvA(58AUOsZI@@7TxLCB{ucweWV=*Cee|3^5~Wo_jib%13i7('
    '(M+1MP;ZYRv!=$XTQPsRy1dc!@$CZZTFqmf)_TYE$Iu9B-Dk}q2opIJXMNY**FCaTvSG~wOx}Z1YL=4DcIpWibg8>qOlI+e*^?>Ly@m=&8r5Mi'
    '(ZTjx(?0R%{|6y}dUF'
)
FALLBACK = {"m": "rook", "f": "ember"}  # matches scripts/fighter_model.gd
REQUIRED = ("hips", "spine", "head", "leftUpperArm", "rightUpperArm",
            "leftLowerArm", "rightLowerArm", "leftHand", "rightHand",
            "leftUpperLeg", "rightUpperLeg", "leftLowerLeg", "rightLowerLeg",
            "leftFoot", "rightFoot")
GRIP = tuple(side + bone for side in ("left", "right")
             for bone in ("Hand", "IndexProximal", "MiddleProximal", "LittleProximal"))
SFX_EXTS = {".mp3", ".wav", ".ogg", ".flac"}

class AssetError(Exception):
    pass

def dump(obj):
    return (json.dumps(obj, ensure_ascii=False, indent=2, sort_keys=True) + "\n").encode("utf-8")

def expected_sfx():
    paths = zlib.decompress(base64.b85decode(EXPECTED_SFX_B85)).decode("utf-8").splitlines()
    return sorted(set(p.strip().replace("\\", "/") for p in paths if p.strip()), key=str.casefold)

def project_root(value):
    root = Path(value).expanduser().resolve() if value else Path.cwd().resolve()
    essentials = ["scripts/fighter_model.gd", "data/roster.json", "scenes/main.tscn"]
    missing = [p for p in essentials if not (root / p).is_file()]
    if missing:
        raise AssetError("Run inside the Godot project directory; missing " + ", ".join(missing))
    return root

def read_json(path):
    try:
        return json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise AssetError("Cannot load " + str(path) + ": " + str(exc)) from exc

def inspect_vrm(path):
    info = {"file": path.name, "path": "res://models/" + path.name,
            "size_bytes": path.stat().st_size, "status": "invalid", "errors": [],
            "warnings": [], "human_bones": {}}
    try:
        with path.open("rb") as fh:
            header = fh.read(20)
            if len(header) != 20:
                raise ValueError("File is too short for a GLB/VRM header")
            magic, version, total, chunk_size, chunk_type = struct.unpack("<4sIIII", header)
            if magic != b"glTF" or version != 2:
                raise ValueError("Expected glTF binary version 2 (.vrm GLB)")
            if total != info["size_bytes"]:
                raise ValueError("GLB header length %s disagrees with file size %s" % (total, info["size_bytes"]))
            if chunk_type != 0x4e4f534a:
                raise ValueError("First GLB chunk is not JSON")
            if chunk_size > 64 * 1024 * 1024 or chunk_size + 20 > total:
                raise ValueError("GLB JSON chunk length is invalid or too large")
            data = fh.read(chunk_size)
            if len(data) != chunk_size:
                raise ValueError("Truncated GLB JSON chunk")
            doc = json.loads(data.rstrip(b"\x00 \t\r\n").decode("utf-8"))
            # Inspect the following chunk header without reading bulky textures/meshes.
            next_at = fh.tell()
            if next_at < total:
                if total - next_at < 8:
                    raise ValueError("Truncated next GLB chunk header")
                bin_size, bin_type = struct.unpack("<II", fh.read(8))
                if bin_type != 0x004e4942:
                    info["warnings"].append("Second chunk is not BIN")
                if next_at + 8 + bin_size > total:
                    raise ValueError("GLB BIN chunk extends past file end")
            elif doc.get("buffers"):
                info["warnings"].append("No BIN chunk despite buffer declarations")
        nodes = doc.get("nodes", [])
        skins = doc.get("skins", [])
        info["node_count"] = len(nodes)
        info["mesh_count"] = len(doc.get("meshes", []))
        info["skin_count"] = len(skins)
        info["embedded_animation_count"] = len(doc.get("animations", []))
        info["extensions"] = sorted(doc.get("extensions", {}))
        ext = doc.get("extensions", {})
        if "VRMC_vrm" in ext:
            info["vrm_version"] = "1.0"
            raw_bones = ext["VRMC_vrm"].get("humanoid", {}).get("humanBones", {})
            bone_refs = {name: x.get("node") for name, x in raw_bones.items() if isinstance(x, dict)}
        elif "VRM" in ext:
            info["vrm_version"] = "0.x"
            raw_bones = ext["VRM"].get("humanoid", {}).get("humanBones", [])
            bone_refs = {x["bone"]: x.get("node") for x in raw_bones
                         if isinstance(x, dict) and "bone" in x}
        else:
            info["vrm_version"] = "unknown"
            bone_refs = {}
            info["errors"].append("No VRM humanoid extension found")
        for name, index in bone_refs.items():
            if not isinstance(index, int) or index < 0 or index >= len(nodes):
                info["errors"].append("Humanoid %s points to invalid node %r" % (name, index))
                continue
            info["human_bones"][name] = {"node": index, "gltf_name": nodes[index].get("name", "")}
        info["missing_required_bones"] = [x for x in REQUIRED if x not in info["human_bones"]]
        info["missing_grip_bones"] = [x for x in GRIP if x not in info["human_bones"]]
        if info["missing_required_bones"]:
            info["errors"].append("Missing required humanoid bones: " + ", ".join(info["missing_required_bones"]))
        if info["missing_grip_bones"]:
            info["warnings"].append("Weapon grip finger mapping incomplete: " + ", ".join(info["missing_grip_bones"]))
        if not skins:
            info["errors"].append("No glTF skin (skinned mesh) defined")
        else:
            # Validate references rather than trying to compute Blender-like skin weights.
            for i, skin in enumerate(skins):
                for idx in skin.get("joints", []):
                    if not isinstance(idx, int) or idx < 0 or idx >= len(nodes):
                        info["errors"].append("Skin %d has invalid joint index %r" % (i, idx))
                        break
        info["status"] = "valid" if not info["errors"] else "invalid"
    except (OSError, ValueError, UnicodeError, json.JSONDecodeError, KeyError, TypeError) as exc:
        info["errors"].append(str(exc))
    return info

def inspect_animations(root, roster):
    kits = sorted(set(str(x.get("look", {}).get("kit", "")) for x in roster if isinstance(x, dict)))
    entries = {}
    for kit in kits:
        rel = "animations/" + kit + ".tres"
        target = root / rel
        result = {"file": rel, "exists": target.is_file(), "animation_names": [],
                  "bone_tracks": [], "warnings": [], "errors": []}
        if target.is_file():
            contents = target.read_text(encoding="utf-8-sig", errors="replace")
            if '[gd_resource type="AnimationLibrary"' not in contents:
                result["errors"].append("File does not declare an AnimationLibrary")
            # In these files animation names are declared as &"name": SubResource(...).
            result["animation_names"] = sorted(set(re.findall(r'&"([^"\r\n]+)"\s*:\s*SubResource\(', contents)))
            result["bone_tracks"] = sorted(set(re.findall(r'NodePath\("GeneralSkeleton:([^"\r\n]+)"\)', contents)))
            for essential in ("idle", "hit", "block"):
                if essential not in result["animation_names"]:
                    result["warnings"].append("Missing common pose " + essential)
            if not result["animation_names"]:
                result["errors"].append("No named animations could be found")
        else:
            result["errors"].append("Referenced animation library is missing")
        entries[kit] = result
    extras = sorted(p.name for p in (root / "animations").glob("*.tres") if p.stem not in entries)
    return entries, extras

def inspect_sfx(root, expected):
    root_rel = "sfx" if (root / "sfx").is_dir() else "audio/sfx" if (root / "audio/sfx").is_dir() else "sfx"
    audio_root = root / root_rel
    available = {}
    bad_headers = []
    warnings = []
    if audio_root.is_dir():
        for base, dirs, files in os.walk(audio_root):
            dirs[:] = sorted(d for d in dirs if not d.startswith("."))
            for filename in sorted(files):
                p = Path(base) / filename
                if p.suffix.lower() not in SFX_EXTS:
                    continue
                rel = p.relative_to(audio_root).as_posix()
                if rel.casefold() in available:
                    warnings.append("Audio case collision: " + rel)
                    continue
                available[rel.casefold()] = rel
                try:
                    with p.open("rb") as f:
                        sig = f.read(12)
                    valid = (sig[:3] == b"ID3" or (len(sig) >= 2 and sig[0] == 255 and sig[1] & 0xe0 == 0xe0)) if p.suffix.lower() == ".mp3" else (
                        sig[:4] == b"RIFF" and sig[8:12] == b"WAVE") if p.suffix.lower() == ".wav" else (
                        sig[:4] == b"OggS") if p.suffix.lower() == ".ogg" else sig[:4] == b"fLaC"
                    if not valid:
                        bad_headers.append(rel)
                except OSError:
                    bad_headers.append(rel)
    matched = {}
    missing = []
    for name in expected:
        actual = available.get(name.casefold())
        if actual is not None:
            matched[name] = "res://" + root_rel + "/" + actual
        else:
            missing.append(name)
    expected_keys = {x.casefold() for x in expected}
    extra = sorted((n for key, n in available.items() if key not in expected_keys), key=str.casefold)
    by_cat = Counter(x.split("/")[0] for x in matched)
    catalog = {"schema": 1, "sfx_root": "res://" + root_rel,
               "note": "Available sound files only; Update 18 will map game events to sounds.",
               "available": matched, "expected_count": len(expected),
               "missing_count": len(missing), "unlisted_count": len(extra)}
    report = {"directory": root_rel, "expected_count": len(expected),
              "present_count": len(matched), "missing_count": len(missing),
              "unlisted_count": len(extra), "missing": missing, "unlisted": extra,
              "available_count": len(available), "suspect_audio_headers": bad_headers,
              "by_category_present": dict(sorted(by_cat.items())), "warnings": warnings}
    return catalog, report

def scan(root):
    roster = read_json(root / "data/roster.json")
    if not isinstance(roster, list):
        raise AssetError("data/roster.json must contain an array of fighters")
    vrms = {p.stem.casefold(): inspect_vrm(p) for p in sorted((root / "models").glob("*.vrm"))}
    animations, unreferenced = inspect_animations(root, roster)
    fighters = []
    for c in roster:
        if not isinstance(c, dict):
            continue
        look = c.get("look", {}) or {}
        fid = str(c.get("id", "unknown"))
        requested = str(look.get("vrm") or "").strip()
        chosen = requested if requested.casefold() in vrms and vrms[requested.casefold()]["status"] == "valid" else FALLBACK.get(look.get("body", "f"), "ember")
        fallback_used = (chosen != requested)
        chosen_info = vrms.get(chosen.casefold())
        fighters.append({"id": fid, "title": c.get("title", fid), "kit": look.get("kit", ""),
                         "requested_model": requested or None, "resolved_model": chosen if chosen_info and chosen_info["status"] == "valid" else None,
                         "fallback_used": fallback_used,
                         "model_status": "own_model" if not fallback_used else "fallback" if chosen_info and chosen_info["status"] == "valid" else "unavailable",
                         "animation_status": "available" if animations.get(look.get("kit", ""), {}).get("exists") else "missing"})
    expected = expected_sfx()
    catalog, audio = inspect_sfx(root, expected)
    errors = []
    warnings = []
    for mid, info in vrms.items():
        if info["errors"]:
            errors.extend(mid + ": " + x for x in info["errors"])
        warnings.extend(mid + ": " + x for x in info["warnings"])
    for kit, item in animations.items():
        errors.extend("animation " + kit + ": " + x for x in item["errors"])
        warnings.extend("animation " + kit + ": " + x for x in item["warnings"])
    for f in fighters:
        if f["model_status"] == "unavailable":
            errors.append(f["id"] + ": no usable VRM or matching fallback")
    if audio["suspect_audio_headers"]:
        warnings.append(str(len(audio["suspect_audio_headers"])) + " audio files have unusual/invalid container headers")
    if audio["missing_count"]:
        warnings.append(str(audio["missing_count"]) + " entries from the provided sound list are not currently in the project")
    generated = datetime.now(timezone.utc).isoformat(timespec="seconds")
    manifest = {"schema": 1, "update": VERSION, "generated_utc": generated,
                "project_modes": ["duel_vs_cpu", "cpu_vs_cpu"],
                "models": vrms, "fighters": fighters, "animations": animations,
                "unreferenced_animation_libraries": unreferenced,
                "audio": {"sfx_root": catalog["sfx_root"], "expected_count": audio["expected_count"],
                          "present_count": audio["present_count"], "missing_count": audio["missing_count"],
                          "available": catalog["available"]}}
    audit = {"schema": 1, "update": VERSION, "generated_utc": generated,
             "project": str(root), "counts": {
                 "fighters": len(fighters), "own_models": sum(f["model_status"] == "own_model" for f in fighters),
                 "fallback_fighters": sum(f["model_status"] == "fallback" for f in fighters),
                 "unavailable_fighters": sum(f["model_status"] == "unavailable" for f in fighters),
                 "model_files": len(vrms), "invalid_models": sum(v["status"] != "valid" for v in vrms.values()),
                 "animation_libraries": len(animations), "audio_present": audio["present_count"],
                 "audio_missing_from_list": audio["missing_count"],
                 "audio_unlisted": audio["unlisted_count"]},
             "errors": errors, "warnings": warnings, "audio": audio, "fighters": fighters,
             "models": {k: {"status": v["status"], "vrm_version": v.get("vrm_version"),
                            "missing_required_bones": v.get("missing_required_bones", []),
                            "missing_grip_bones": v.get("missing_grip_bones", []),
                            "errors": v["errors"]} for k, v in vrms.items()},
             "animations": animations}
    # Stable output when assets are unchanged: repeat runs do not rewrite reports
    # or create new backups simply because the clock advanced.
    previous_path = root / "data/asset_manifest.json"
    if previous_path.is_file():
        try:
            previous = read_json(previous_path)
            before = {k: v for k, v in previous.items() if k != "generated_utc"}
            after = {k: v for k, v in manifest.items() if k != "generated_utc"}
            if before == after and isinstance(previous.get("generated_utc"), str):
                generated = previous["generated_utc"]
                manifest["generated_utc"] = generated
                audit["generated_utc"] = generated
        except (AssetError, AttributeError):
            pass
    lines = ["FIGHT ROYALE GODOT - ASSET AUDIT 03", "Generated: " + generated,
             "Project: " + str(root), "", "MODELS / FIGHTERS",
             "VRM files: %d, invalid: %d" % (audit["counts"]["model_files"], audit["counts"]["invalid_models"]),
             "Fighters: %d, own models: %d, fallbacks: %d, unavailable: %d" %
             (audit["counts"]["fighters"], audit["counts"]["own_models"], audit["counts"]["fallback_fighters"], audit["counts"]["unavailable_fighters"])]
    for f in fighters:
        lines.append("  %-14s kit=%-12s model=%-12s [%s]" % (f["id"], f["kit"], str(f["resolved_model"]), f["model_status"]))
    lines += ["", "ANIMATIONS", "Kits: %d" % len(animations)]
    for kit, item in animations.items():
        lines.append("  %-14s %2d animations, %2d bone tracks [%s]" %
                     (kit, len(item["animation_names"]), len(item["bone_tracks"]), "OK" if not item["errors"] else "ERROR"))
    lines += ["", "SOUNDS", "Search folder: " + audio["directory"],
              "Present from supplied list: %d / %d" % (audio["present_count"], audio["expected_count"]),
              "Additional unlisted files: %d" % audio["unlisted_count"],
              "Suspect audio headers: %d" % len(audio["suspect_audio_headers"]),
              "", "ERRORS (%d)" % len(errors)]
    lines.extend("  - " + x for x in errors[:100])
    lines.append("WARNINGS (%d)" % len(warnings))
    lines.extend("  - " + x for x in warnings[:100])
    lines += ["", "NOTES", "This is a static asset audit; only opening Godot can verify imported rigs, skins and animation playback.",
              "Missing roster-specific models use the same male/female stand-ins as the existing game.",
              "No game scripts, scenes, VRMs, sound files or animation sources were modified.",
              "Full details, including missing sound paths, are in reports/asset_audit_03.json.", ""]
    return {"data/asset_manifest.json": dump(manifest), "data/sfx_catalog.json": dump(catalog),
            "reports/asset_audit_03.json": dump(audit),
            "reports/asset_audit_03.txt": ("\n".join(lines)).encode("utf-8")}, audit

def hash_bytes(data):
    return hashlib.sha256(data).hexdigest()

def atomic_write(path, blob):
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_name(path.name + ".tmp-" + uuid.uuid4().hex[:8])
    try:
        temp.write_bytes(blob)
        os.replace(temp, path)
    finally:
        if temp.exists():
            temp.unlink()

def install(root, changes, dry_run=False):
    pending = {rel: blob for rel, blob in changes.items()
               if not (root / rel).is_file() or (root / rel).read_bytes() != blob}
    for rel in changes:
        print("  %-9s %s" % ("UPDATE" if rel in pending else "unchanged", rel))
    if dry_run or not pending:
        return None, len(pending)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    backup = root.parent / (root.name + "_backups") / ("assets_03_" + stamp + "_" + uuid.uuid4().hex[:6])
    originals = backup / "originals"
    records = []
    for rel, blob in pending.items():
        file = root / rel
        existed = file.is_file()
        orig = file.read_bytes() if existed else b""
        if existed:
            (originals / rel).parent.mkdir(parents=True, exist_ok=True)
            (originals / rel).write_bytes(orig)
        records.append({"path": rel, "exists": existed,
                        "sha_before": hash_bytes(orig) if existed else None,
                        "sha_after": hash_bytes(blob)})
    (backup / "backup_manifest.json").write_bytes(dump({"version": VERSION, "project": str(root), "files": records}))
    committed = []
    try:
        for rel, blob in pending.items():
            atomic_write(root / rel, blob)
            committed.append(rel)
    except Exception:
        for rel in reversed(committed):
            old = originals / rel
            if old.is_file():
                atomic_write(root / rel, old.read_bytes())
            elif (root / rel).exists():
                (root / rel).unlink()
        raise
    print("Backup: " + str(backup))
    return backup, len(pending)

def restore(root, folder):
    b = Path(folder).expanduser().resolve()
    manifest = read_json(b / "backup_manifest.json")
    if manifest.get("version") != VERSION or Path(manifest.get("project", "")).resolve() != root:
        raise AssetError("Backup is not an Update 03 backup for this project")
    for item in manifest["files"]:
        rel = Path(item["path"])
        if rel.is_absolute() or ".." in rel.parts:
            raise AssetError("Unsafe backup relative path")
        orig = b / "originals" / rel
        if item["exists"]:
            blob = orig.read_bytes()
            if hash_bytes(blob) != item["sha_before"]:
                raise AssetError("Backup checksum mismatch: " + str(rel))
            atomic_write(root / rel, blob)
        elif (root / rel).exists():
            (root / rel).unlink()
        print("  Restored " + str(rel))
    print("Restoration finished.")

def main(argv=None):
    ap = argparse.ArgumentParser(description="Fight Royale Godot | Update 03 asset audit")
    ap.add_argument("--project", help="Project directory; defaults to current directory")
    ap.add_argument("--dry-run", action="store_true", help="Scan but write nothing")
    ap.add_argument("--strict", action="store_true", help="Return nonzero if assets have critical errors")
    ap.add_argument("--restore", metavar="BACKUP", help="Restore generated files from a previous Update 03 backup")
    args = ap.parse_args(argv)
    root = project_root(args.project)
    print("FIGHT ROYALE GODOT | UPDATE 03 - ASSET AUDIT")
    print("Project:", root)
    if args.restore:
        restore(root, args.restore)
        return 0
    changes, audit = scan(root)
    counts = audit["counts"]
    print("Fighters: %d | Own models: %d | Fallbacks: %d | Unavailable: %d" %
          (counts["fighters"], counts["own_models"], counts["fallback_fighters"], counts["unavailable_fighters"]))
    print("VRMs: %d | Invalid: %d | Animation kits: %d" %
          (counts["model_files"], counts["invalid_models"], counts["animation_libraries"]))
    print("Sounds from list: %d / %d | Unlisted: %d" %
          (counts["audio_present"], counts["audio_present"] + counts["audio_missing_from_list"], counts["audio_unlisted"]))
    print("Critical issues:", len(audit["errors"]), "| Warnings:", len(audit["warnings"]))
    backup, pending = install(root, changes, args.dry_run)
    if args.dry_run:
        print("Dry run: nothing written.")
    else:
        print("Files changed:", pending)
        print("Report:", root / "reports/asset_audit_03.txt")
        print("JSON report:", root / "reports/asset_audit_03.json")
        print("DONE. No game assets or gameplay code were changed.")
    if args.strict and audit["errors"]:
        return 2
    return 0

if __name__ == "__main__":
    try:
        sys.exit(main())
    except (AssetError, OSError, ValueError) as exc:
        print("ERROR:", exc, file=sys.stderr)
        sys.exit(1)
