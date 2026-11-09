#!/usr/bin/env python3
# -*- coding: utf-8 -*-
r"""Fight Royale Godot | Foundation Update 01

One-file installer (Python 3.9+) for the already-existing Godot project.
No third-party Python packages are required.

Examples (Windows PowerShell):
    python install_01_foundation.py
    python install_01_foundation.py --project "C:\Games\fight-royale-godot"
    python install_01_foundation.py --godot "C:\Path\Godot_v4.4-stable_win64.exe"
    python install_01_foundation.py --dry-run
    python install_01_foundation.py --restore "C:\...\fight-royale-godot_backups\foundation_01_..."

Assumes scripts/, scenes/, addons/ and data/ from your current Godot ZIP
are already in the target folder. Does NOT overwrite them.
VRMs should be in models/. Your existing sfx/ tree is used without moving audio.
Stage 02 will remove the legacy shop/team/survival menus; this stage does
not falsely claim those features are already migrated.
"""

from __future__ import annotations
import argparse
import base64
import datetime as dt
import json
import os
import re
import shutil
import subprocess
import sys
import uuid
import zlib
from collections import Counter
from pathlib import Path

VERSION = "01.0"
DEFAULT_PROJECT = Path(r"C:\Users\Admin\OneDrive\Documents\fight-royale-godot")
SFX_PATHS_B85 = (
    "c-ozP>#pOvj^?}c@4*zN8{L?BmcbxU5+!jh$M&}Dl}bJR@Ft0pC}*7p&Z(*$e!fW*Me+K7|ILkl-NG+7y7hUw4)<Ym<LNTam#@>=`{jQ=m;d"

    ";;|52j0dGgio%Q6mby7<%T-"

    "Sur<xnA7WpU(5NhZFr)(wX4hI{E8qm`>lr)z7E9dsa`n_$kb5cnk|Y<TTFHy+RDzo1btB!|Er1%+<?W=5_U#?c}EL@+-Xa%dOWEa-"

    "HY(?8g!AG2KUhT2>!I3Gq+A-u-lmPou#pAvZUy@6!`5b$5T7=54qQ7q<=bRN?k*Ux%;_7nlMV|8|6NB#IlHUhdml&m?5nFBf>KHPZJTrg$yy"

    "Wx$^94sTPS)}bEjr(1{T*}=OE8xRT6zWZ|zaEnofsXq$y4Sx5h&5wS0z+H?7&g1o%KAj$jv0r4FM|?nd%<vws2MqYwAOd^|4D2v%e!V$Bx4g"

    "Xi#XI`m$kh!b_zO%ZFe2Py81WxxSQ(dxHDO_#x6>1d1ANkJm`u#JdcU2P{S04V0rH@97-$=Si-|W@|LxsaQRnyJxNhqX0s*gFaY4`*2V-"

    "UJ6G@KAzfQyEpQnaxD>#Ua8;#^`+_ys{E;U@y&jr2%KhJo278<ALJHQ0KEzVY`)o<$z(r&nX)tG6+C0mY3JF3Tw4`O8^HX*Tj-"

    "v9pfYeYQH1IP~l%bj6v9S9?s`71E*Yh>OV<`z1_-"

    ">28S;v!fbOz4W(b#8$2kJD`iv9+Df!+H%}&@|j1n?Spu*F1jvaEOB0nfHmL_x1oj^g#`Mg0AiiJ4KqGhg%nO+Vce$6pJ`I%_rb@k$|Q_hDYB"

    "<*op8z0Dd>&;RNe!C5*i1?;QoajRlAdp=P!QgSQFGN_=b%&;^$E)8Th)>u`qkN$lRBV2v;D(**?k3Q`~rz4hqJ3M>l(fj*`~1nIxY<ia~n4z"

    "`%)kvvK1Sq*vJpHKWO9;6dV@)q<yjou-9tUHKQB|HoW@kmX-"

    "&GQEQ03rnhc)*1e%+FT*9Ou0Qc@5ix`Mw9dukb!&d|G%q*zDamEY<1qXa?fpUSIOqe|Gq{Nx$GNI&{!D=JgaV!|68gQs4Gz@?#DBnm~Tyh~o"

    "}F&sY8s8UEfhjWo$15rAv9=Ny)YUk%U(+uf;P+SdT0Brb@~1<!f<@^5%`;LgjV1_{;w0ksP>w>}D&`zdo~=S!Gf6Kn#7kXP5sJsWO7Ss5Pd;"

    "G5xI9lm;)+!wz8H;yOXWdoVnKw-CENhR<+)*s(7xKBbZT-*wSA!D;W_9qD(;HzL_-%-"

    "lM1#5$lAHo5KcuVwE`HBWqP<zwGi{VEgT0Z@CgNu3*b`}AEOxh8XvKDV}W4z`%zj&0NATwa@n!O=_bkba9i44J%jP)aseLG}C+G}J@@_Op=%"

    "FB&kYOk?BJA$^yI`8+#>6#gW$E>*^sS5s&ttt?LMjAMD9^K|yZ-"

    "}^QfZ2mn+5L{^8dP}W5<Pnd&s}G?*4XL3zCV$HPq!K7`U_+S9(?AP31hkAIyai;H>{rXfE)m-rdz+1bP^Q&I>~ySUx6mXo{5O3_r}wr^-"

    "Ox!>hAF7S~7N!ai}`vZNSBkufDixGhThT^X<E1nGiTcy!H)L9BUrZVG4MpMJ2O?JG=8c%B0Z&qjhkw+(}n}*N4Ht)$g7isCsDoofYUZgX*pp"

    "v5le`I`{~It+08Ly5;h6vXL-+i$A)fY;!o&2ERs>j2jv{+#dWf>M46Ta^-!v-"

    "^c#oR976$3vBHFz}bBU<?(%V!vb~m<)G8wNQ@YFd!P)QcwsHW-2=<_AeV9Hm#1@ejl$#LWqmh4zfSybIv8&cgHB7lvz(ERV)8l92BrIJT-"

    "|u<E&@$I!JvZb`_;L%Y^yC%39!@l8k+AwdT>`XMm!h4TGVN{-J$|>U$yqEP;xz*-^THcw>$t@)Tbxw6Rv{CP6EYP4A-"

    "m*HX`9V?`IeSrDc|f6M;oV@lZGV36`|&>Vg}{TNmC*K;J=3Yz+pE;`bT8^X!~OTWBvBCYrMs?40$iz{2A5C90PG>6=H~;efl*2B7v=n7UW}z"

    "V~Sc6)L`Mn7se%WmUfY<meVr8rPS~7k~n`Z|yr0S-"

    "7(O&PQC?>pat=JF5)V^VOf`TVi2&q0nLiXx8hzp^oQ3%un#j8=4@=es&0791q}$?OPRANoLUJ0ft6MgDn+~wk!kk^w(j3!ic~C^L`mu<^hn_"

    "jOb>#l{e6FzQURbuw`}m-3DnbqrPAtw_#ynav-jdONqT(*&QBe7^ib~Jz3#}R>ZDyMmh%{CQ*U3sCa0eWO=iiE~xVki*)^k46x(t1J~R~7lO"

    "wP0#;K6Ba2w$W=Pc9o*oGsT;#$dnM+YFXw$sl&LC2ezr~`my6Z5b$!rSG0hVL3G70?R&TunavT#O+mkP~iUGPhQ2T!p5zhS|EGX2$p@OvxsY"

    "(<Lfz+VnrKYaNbNjoN<c<B5CLe($9!fd$zuCmH20O(pfF6`*g!3!z~$d#{m{93j(;P;y-"

    "8kl+U)wo^V=1{?!e05prM~eStm_aN20;2>&do|uSLc(yLoY+WjepON{0`XlR4ox+WeY0qArh-ju9In=t$WgHD=-"

    "<X$5M;7{XHDH0rgi2+FghRL#b*$cv^Hwk{tUQoUalG*KY}K^BHO@s-97Bk&ko>57Q<2>uQ6dmOJs-m^5ZqCu3-"

    "WBIQn2i(W!y60BUysg%E^}j}3-LX`%*--"

    "|Do?=#kqO3ph^z;DsaZt#i9JGBosVmi%@wUnjS&!*_CrL<m{nQS1*BAEUL@DY41J!|bi?n+bsiNiwOVh1*Pzasd{@f^$%P;@y!=w&l({n#*o"

    "{(8cGt#h~*5wr@$qr{7SjU-"

    "~HI+tUMf5aJTPpoR?F<sm}%dxmYIdjAJ7*L|M~ze`1`G^<FR(Y3h&2AB7hHIjND#nj4=7irNK{jkmLD24$<pF(nhZ(Pg5>=FbfF#VVU1Q8O%"

    "?ARsn_B2|Y03(b$jCTtf!yj`s2;%_fJ2;fh`|8EU^BZQ4Y#~D}499p9#TzXw)d-"

    "2NQbS(_=RMf;UxMPk3o9B{4Jl;$)R$1`JBCMCKZga~>e2u6dVmW0sBzOyk{-"

    "SHH~6#g;zf`LVK|Xrd4qp~COzNZiEly;#;HAnri^ZE;*6#Jwwb+kyhx2r{5kJ1a$#U$?%?RWiQj<E3ndu6&}hfuyFFmGTKeU&udq@&yDK5+Y"

    "9L+r5!6ysav%=XRu5vVw{O9*@3Is7(>+cb%b{nz5hGX8QGUKU<}G8RiXb{1!L3XToqL$`JRS%@rK$JZ62ty-3pE7N`?vUcsIyccSQ79-J)y-"

    "jKFve$ai3xB&|TX7O#}zSZhtDG51=-H)=liR!iTRGb6PNB=Nk5nZq*g{_2(INxn-yz!QH$upJMC>Z4?;rgc8%<>!MQt<7Id~8E-"

    "2F{x>gw5Naq_HeYc+M@<aR1)bHF4#5DHUie0>=wgHnElo#5-|$M(-j@Bj*krO1_Q@7y-)P2-fuuoEuKW1==-Bh=jGdr}*jU_q-"

    "p$iW6WC#}0LzcG?aF+i##rIVway2l0Y_-"

    "8c3n^uF#KvJm(6X5n=(g$R&j207MX&qSDGuKM)Ageh`}X{%Nls!*cb&|EXQ`WhW(6jMKET(=9%Rx3>;)h3bQ_P^=FV0B?M$s)&p*<|7Rzik2"

    "Qh{nnYq$&>F!glGh|rY)reMe!I)QV@zED?YA9_7-Ay39qn@lgG5*nOHx8A)snuXMxaK<5IDV@4MD>jF(~UGY&p0oF(qhw6&5FlM_!-"

    "pqp7O&D`kTUJ4MJ4mNzkV5!q#MnL0e`Z9l_{+Xnq3ClF$D2bPR%+IFcy(@f^_WIor7nQ?I7(B~LM7$_);MVFY~JGaoz9T8>gdJGFAS*P99hj"

    "~Yi-NGhgz(!O7v@KF&)@xFr&{z!jD_jjFR7KJxH$6GiJ7_E1CSxw{xzG}rYV(uAM90(xkJ&fSP}5FUfY9V~^-qiiq@zB27_9HezJ79-"

    "qQj_+ji?Nx#+5Prh!t^((<oi^`6@VB%)#xe<wDFTGDC~iExwH?r!96QD-gc{IlKyuS_5(Mqjdql>+XH<2IfuNjpwChiKh#ki)1QPU=>?d#n@"

    "yJo5JJQ#xS22CPzkVG>BPcnRkePXPl;nNNW)}pN-C8nhkz=z-i<`n`?Yaw`~rsR%rc2TYP1KKe|-j_4AeVLUdBU!-"

    "}1gLHIgYuh^iEEbZoX(Toij;v-5&Qhh~!$g*Frqfbl-^V7Q~&|ZPZK^W!UtHigUS3*y-d_e<`OHo|<7}>YZ_Z(}-"

    "K^VQYnXFRfn@xVWx9j3JoE(z(oL&q!0Am4-WO|EB#A5cs_a!kb+9zNl3kgC&N+7^Odj*Es7!F&F*ss}l-"

    "<NqQ7R!y#&Q4IUbB`K&dnrX4qPaK4j-"

    "tT<<j*S~8dJPRb2SIR)*(WfPEl^fUUG0V4(=*~Z&YMp3r8h_qB3k!A<b;aI2ck2wer(_9{n>efd(QWW6ZL|sRyXU(gbf&-"

    "cfcy&{2>om`Ndv8+BF)D$>J^G@6RNS}2@b$Rra(CB18vLpYUq;$&0Y+mSI{x~=oE;uK%jX5$zlMQaYl-OY+MQ+Rx3-WzOMdY-"

    "J%&ify&VTrO{9GQ%I7?9jvYjPQNL#^YN8&+OIS#cM_g4WpgvXK{H1{qqMtpo(erWYOFQ$QNr(13u32&%$>fkj(Rq!7d(w331ZCuhfk0cZss9"

    "ds{bAs_uQ9KDKhu@C&dwSsdfs;lCWggT=0DxfjsQ4;3s`*hjaR&9JL(Z!+>gAU0*Lz|3C8>B)n`vi&#o15z4J%buT$32u1{?7u(|11qO1Xc;"

    "`eZZnD3<(<gP@-S!S<ZCx%Yc~f+nJ;@?kTvEIn)7Vg<4G!gGNr`6*R)Z7E@{)g2J1S9oBjobhG4lDbDHwNa69xy#S913-"

    "00_pd44P=<2o}Igg`T$ha8re6F-G23+BYN`BnA;+ZR{4m5toeWMpr6ju7~3ZSOHnbSxW9`B)6#~;b|4>gU(3q{`|`4-"

    "|%H)fMngh?QOiVsiLy9|iVM;%(jRONq@FV|;V!GPpHo$-`$-bs5vM~7$E%g`(YitS0dV7-"

    "#?lR+N9O*mO+nU@f!oZ}Ogw43ECc#v*x?NF?z9IcN`r?r8*c(B;_M*hvWOc$Lx>PMk;!3A`i-"

    "P4j(QTq7jf<|yRnN;hpqSfE#VeHXRqbwtdBLqXvVYA3{bRxrAi-LK5wZF2j9#<<x-G~dq7)gaLj;D$mmxRINe1ahpwhovOBK}F18{8aD-"

    "}7*(0k9?83r+c4vt(hrBtEW(z4~wT<lkI1<af88(NwpP<)pC02!K>TmZs(MBc{RKk9QW@Wl8{TlG%s<0A{2NP-DCpODspb8Axq|o+htL3r}E"

    "EP)D?nS5V^rWsZ02vl2It9cP374O8025i?45UO1s!Kf{}>8z_1k33&?v(#o}*sfhuF*4-FRN}Izp#b8J>CT{-"

    "ER+_vO^$J@GE*DM_Ztjq>c*1^$^$^N+_qC(k+l8BD<GtOob%J5plOmsV^}LtWY>a#6d`hdNq~V`rIBrPnj^%ar@|DCVBFrt3-"

    "Q|*f@sYlgcMJXs{OER&3(Qyc^+zh%hd&8n^z+J+DGuh5Dndt`_r$m7(Ov7CFrT8@YHm0hVACFsQbamL5P_{Kq1_k8@Dp{L=TW<R6b()9@nU2"

    "V`wrwa;^lf--BNuwZNYLAW^2Pcqp{<Bp9N`1mb9f)?kVl~25N#4eq$O9ABWU2i0Q0D_YN0Kr7w28nU<N_3I(zWmGXkX0<=<|8_Ay(`0i^k;%"

    "gdi9%Dj4-pfJ4Km~`++snQgw7>KGv<8WDslD2GWSV4j3vh7H9e$RHHtr^VLpdk0<iI0bDR{yI<7k=E85nlao<$2cNJp0i(78|Kpm$46-"

    "b8Wppw->q(HvBwFeI;i>~sENg}nTEzHQyzQsh1b3Vcwu!)v%j-"

    "NaBYlthV!;SaiwzGCDJ^zwim@CnmuY?T@g?^1~nrp6=eZS*ExgkSINm%*<Wc#Yn}L!*wW-"

    "`V=x{Z5`UvNoteS$Xfb@br@AyI@4n(>PMmv64@ijmj10R<_cCvWM4F%^>ynykdSL{#6Z;BxL6UQfXB#K<lvWf(;dYr!*G~66EdN<hAXEUP3u"

    "=7ZmymHp(~Wz4lQ4J*@O1%>IUs^3o^nP?0Du7)2wWLwJHQ>Ab|@c#~@1N*huNsy(U#&{0jDEAmG*UqhkC^{Hu}rgtnFL!}z#>{(<Y1y{j-"

    "edVMnHKI(O<-}B~XH46}`-"

    "Fj&6wWQf&S7!GHPDas?NV|ayeNEaO4l$!SNHetNRq6vO;<n+XNoc5XQhJ`DCBy|#~a)<cMyEot9Hr?0}>jel+ha3N3^3=kYOb(y$7tYaIWJU"

    "1~J&5dmmO1Q#816%;Nu<K+aG&`}>_w8Ck_IU^MaNk*}c3?%e%g*(UJAOgi1U$jK9WX1n6|+HBF5TVWiR1rqL-DC-Kq^J#NFzAuNU?q>`z8m)"

    "JvKTmn?@BrQngn&j&G=Lp^Dzip326^y=Q3xtjO4F+}M@?ck!25(XX3!>FK<EockChlGLDX-"

    ")<i3YnuqMWXf)}iX&VXgdKhG*ynyIv))8Zw40M}UwiuXO$DX=zb^L~PJ{#xFIk5f_+siJU|q^d{^6GerIb%zw=6t$O9@Nsc5rVb_^!K|w1xx"

    "T+>hBha~ME}Ij9DY+KxiS=IkBx*R((v4St*0Ws02;yJCLn=Jc6<2^&yo}x*{-_Rj79^PXc(?}5A|$wU8`lLYGS|-"

    "UIJBWwkdGD#Kd)8j(~xqpW^*cR>DWDa0zHwMeKO*(%(B8cIM#|?)WX*%3BB690h$IJ7dL2Nn8qKLh8e~BGM1uGF-"

    "4?M$MKMu!w?u_*C=6!cq_;oEBzMQarHt&&EM58>%GtBV-C@S0S;*6==quhpW6+Q(8r1&$y7zAU!Y2m0v_z^wH!a1HE-Ik>Sg4jMo?a3sB1|a"

    "CBXziXB454v4p({D&*Dhwa*V5vl=*t{W=Or;75mDE|kPOFnlrr2<PdoMcJQl>OGk{J}XmJFyh{V1v+<NyZ8P=ixf54PZlMaV*HYL~#mhQ9#N"

    "0Z6LMsM@CL9FiT(<K$D{7e^P?cgl?Ay2Q}w;`6=$y1CNp`je;+j08}rO7GPoES_+Z=u-"

    "xexC(IJ+j6VZHXWfZx#|@S2!=!kaxS~KL?H?cCthnTd=(O+iWj{fFx^s*|pwQB?c29}JO+Rncw3l-"

    "Aja0>;#lJnTVMk&77};w;uXwUznfaVMuSt&EAIMdO>)&gCo=G8DaPHm4viEJh8k^a9^6_|fhY_`IDGtw$81$2WVu-"

    "2R%F{=I!Po|mf!(C+Q}};}D_NGYT>C81NFbmlmK3q@5%uRi&Q!**gY;L*g&gkF&>7=+29;g3TgtP%hRZP&6-"

    "hr`Ghn_R9|(FoIfjvvMB2Q2*4k<T<f924F~}0w8G#Jz=se9qrjJopEGl4SBCAwSa;$rd0xZ0W`WjYkD9~j=(~ZhrZehepRBzPOis|2QR`shC"

    "7^Kl2Fc#B={uS04qXBJr4~o&Y)!;j2wV||M*5R+W5x0-"

    "JP6i!lD+=_19$p8J5$kHsX3~fUg)GhckM>o1SGs5Kfl;AKuXcdp$`Bk^aHwrcMy$%3(^Q=SD+;l&;sd0I3L7jhx{Xo-"

    "m)>DE7c+=s3U_&#tib+&=&t?n4Gd;S3t5tXf`NGtp$B9fextHTc2Jys6|{@5gM^h0x`q9@<eS0Zf$`{UOM7rU54|T0owXG|5^21<1eKOvL8u"

    "0lt|4L2wL#k;mo^Ozh+g8Tz8yf0#4DMw*w_Xl%Z5ZFsXikd;0_;03mO!JA~3N)fP{O~fk3%tD}a^JP(Y;Wbz%S0fXUyT(*1htGr@Yblr=aeB"

    "X-VCVgxv2*&lc@Dkoucp&*3==9TuPLukI8S-;)5f^88WKMB(qZ~G{M(-y-ECOo1jCdUR&ZCR_K#7-"

    "=&<*areXAHWv_Xu&ZP|)rH0Ch<YM>&%JVvj~=DBjUPaN$xim4=6Q6BQt`(fq)mQ~*2dr3^kFCSrZOx5pE6r$yu9Bx+o+o%fv27(B`vQAe*4^"

    "Q4lX=CcFUi9VPHc0eDoh?EXbm38_MF#{gpv`K4)QJ9}y%hr#~Uv;MN4<KEu729-"

    "wvR^W?^SBw*^_BIDtC!9G15Snb6p+uSJcj(#2*Bv8U&i^(QRrRJH=6IzrR%1P{b2m-NJ#_@X2pT01ll8>U{5^RZZTQSfZ(deV-"

    "~tyIffayA#{Kn1;m#Qy&5CbRnjdwsuQeloMtR^gIb{S6ls)H?*EA((8ktyA~}Y|Q^7IH=0wcXKry{9or4zu*rvt|bhz^*>~vD6?gJpKx2Hb>"

    "d>E?;>*|g#azTm;z=TI~cXoji755&~agA!@VE%pXC?K+x?7n3(jsg!WCdY>d#^qoUd-rZJ`!;ik5|_EkWwkQq>@bjO#zgPw>lA|wQo!0VP^!"

    "81vD-Y1Sk_?N(-"

    "<n0#}Jos<j_4%;(={cRfW@7SPIxlVwBz~*8Ej)*w+_0_2z076@86mR?{A=0Hde)6sZ>%P4QnCvEhy9@p8gfCx?HoWT7yaA$J)a@!lZ2@M}Jw"

    "M{i>*YiUIVVRV53#PgTy-eTD)#JhtaTZg|>tobrikip{GkGr51by%tF;{?jzrtKpN_Hg4D>|aw^9HIi8XFN;$6(ijYgd|1Wa5&{?X}`Rb;Nk"

    "7EG9@Y0=-"

    "nhj$f!7>fir%XQADc1U>P9_oSKcLbeU%^IY}{d+PKkT&}+oS9ke>2a51|l)fke(Q?vDz`@+L|{Q44%M#hY9fA=)7l50rulFcR8;jS}W?{KBT"

    "{MR9HJ~O>5EiEj|0NT3tXB7BHWM58H$Jw^0Ikj_=GPShCj@N#Di8$&_u>z8g?JzjF^X=9Gc8u(#O4L}r?B2d%>?lO>LK`Pr;z8w2Ox(g_CV+"

    "^N({uPkad7j}$A*`R6f5X=u2_pM@1r3H<hR=@RAGb8*q9YVvC&m-"

    "nL^>_BwT0jP`8!hg+RVgcMv>0S<*#dH)IM*kM9D>PRqhyS+_JGXL`g{V~J1kA+vd7A?HL<2uvf9;ZJcH6csxg6m0+8m&Bb7NWdxn))f~ub;C"

    "#?F7=Xi@eGJN!Rfv_gNvnTX8-Y=90J-csvx!up?^u`n`}ljV4KHyqVxI9%mMO-8)|u1hhWxMt^VQ{Zd-"

    ";Wj6J;SzB+?jBRm3fMmkj#h&^YT>y$+_U7-S(8errm<zC2`FVCs|^I-15arw^Q#2^QVZ6>EN<-"

    "#=}E>3`j**J#}fw3as>9U`_aS7+q?QH(G<N|vGNdcp>fs5z#u+F~BXCGMzWc}iC{?j7;l|xoo7E-"

    "=5{;g`@X|Sr@w^$0G80bA2(O|>G+ZcK=NJx(H`obrMO)_spMQh<)uK+i!(Y>Z4ZbqMmtcsqnm{+P=j&%`q-"

    "@shUDMJ?+3QEOX+#+d|#tl)2vX>xVc0oxr_Ncs>RaG`^5G6l!5U^p-BiCy{kNT~P#8RzXUJ0YAkelfB%n!rO%&lKEnZ|+=RiEPjE!7A$0-"

    "EO?kH&A_478!QfNtW~>O!Q}Aqn=n$Yu+}{LVL3Pi!EfKgi_lWNES&(&}&Pa0lHMciOr*q=qHIwz!otZYYk=+SAy|mpQNM{%EmbeF^pEX;1-"

    "f5vXDykC1kUE0ml>jh)rP25j+}vL0y2T3A}{v<j{VItJSY;aQhqM8?}Jw!^w`k}vCej}!}{^hG)l`e9@-"

    "iJ2v;9*zRU=1G(RN5^%tu^YoNy9L8EC>eeg#kI(UtFTlZFbDB!D!$IRuPu9o1@{RoBWq6yngwK6K@$>Hplwm0-"

    ";M_pwqd|v*6mkw7TOUxkp<2K$0C3zqhl+9V-%L<#1brh6doe5?CfZreKtN!MbUCwVQcJ34(V7~7C)~WS7x}fgMpegV!k;$RQwTC@3{@`<-"

    "&vgcVaaziq>l!75fqObK#An{rHzhE8~IUEJJsAdX(jd%j^t-n$PiF6znep8aB9BgvC`6Dfxo9c{Et`ezU2@u6-"

    "+roQdZ+xwk4o(ZDD+iDRN8w8*4wE;vNRlR7FB`BY?p-UW}^C@g^&+hUZl?1G^ft^8(UWt%D#1-_*>>pf2lj3i#lGaQq%)L-"

    "2d?cbUS2|_22kI#9yecGr<5;~s@c(CzQJuxX@6^3IYiX5hrM27g1BJKEwsd_=)Xg+=iz0bdZ`Z(c<uVPj0vp(JtWJ8|5Q1Tiz?5mGh41$})b"

    "5*)01(BheS7ED~shnG}FBM8sg@3jNn$P6#k02~6@XKBIaVwLrgzz|V27&)`8L5B@M|m!4`WQ%UbXC!CrP4DXwzFmD5UW*%s>ZMhGuu&(8pzE"

    "Ln<%Ml6^N>jI$DT$pL*m4MXj*J2K4aj`GCw7>z+R4@+c6oJLwh}NwYK-O-"

    "3gFt<hpuAph(%TPd2fDBmC$$rwOCo9QwwVWdv3`(%ye_8pH`&l$J<W=8g_yr^lXO&GWqi_JcPjaF3ck37|U6*a|^lr;8bwq$g*@p%>_#YZ?X"

    "yA-l5umMdM&!~dK@#XSpo|N(xHz|YIj5<O_ZV#Yx=pt?19#<D1AsWAmmJygLz>~#-"

    "Dg#iW*ZIp&$2F1#i7Au9!BjK`*9I)2^+^GnJ`@!N_?q0Hkl6Ra7CH?5tCwV(U3tNF;KnLfsa$X-"

    "zwPKOuF6PPz*IE0D9BQR7R;fkHm?#8qp$l9!dxt#70jfwA^q<Opq8%#72gbtiNLHg<kSF)tb>!*d)`ePb=)|;-"

    "OGLl@fkO9BZ87OlFpKQU49|qUc6+UetRfub%ly80@rsl^pw#@DpXNSP*YRJ9p?BA<GY1m@pj1&G=)#zcXBxyQvxd>Z~GbFRIsYANWIK|eo0!"

    "IA6}-Y%tSfW#Y0q~2)QygKv#`1D@xhmup*+;QIGRHNuQ-"

    "t62lo!8MO5kQME~(N85H`8Ohs=yP8ar==1q3!sF)MT7z<vuO!4Q$c9xx>=BQWjSh)LW`hP`vfXCpKa?m>L3TN^prFdw86?cZXMZGbT-"

    "O$sTtd<>z1c$|1Z(w{wSOBZEk0gpsa!1WlvRF{pkq(3GUvR+aHmFNCJRcHmLdpBwPW>El{#mls6KEU47AqgufYc!k)39IDCDj!+OEO)>(1sc"

    ")ZNOcyJ}5&^661nMrM4Puo@;!P+#prDUnz=r!1u-1rv-d+R$dB-JvLZ&1en>&YKG7Togt*g~Q4bTlKXuOYe+Uu3(ZV*b!@wx|}^#B4XLGs#s"

    "(MrSj$|weOFL8dUAClH^H`cGxC-2oHa4H%o!g3dERE+CiF6WYDK`g20{w%rzy?boLm*9c;}JfkoR6-"

    "a6_4T|_9Nw}dk2YR_ez^o&5$k2D7fxt?gMr~UOduZT4ly(E3ZVW#4U5wubq!97Gbd84>yS;bXi_A8Z9#lqr8xNV;%auHTStALRN%jNA1gev@"

    "8<Q5oEJbi|v2cq{G6z~rSjOmLpC$&+sg~v#x4|m=8Nawm^D-R4)iXE#FvCtLuHbD2+sI9~dUa4Xq*}+-3=;B?1A@}(gh-yQs?5t^H7nprLyU"

    "E^cl|e|I!inLqNtt<#suMv+v5FX${LUq5SYbMnJT^~`jL~~HpLVTc2yz9*0CC_GZ8B0FZhKU`NK<xF83Oz>tE|<Lu070&W_w7@M-"

    "Jm`!pTvh(1O%PTTTf`+N7W?)w6R&?Ci35f9*iZNQX%LexG{d!Y^TRfY6fBwX;bGELO8ayMO0HG_Z@=s4&Tdwc1>YIf%PT5xSuJS?Q}e$e}d;"

    "*Z~N95tYt74;u<yvGoLCKov8ja4~8KT>uXD+)J(zXuz(194;iRMUm2>MFt#I2})u$Fua9Mzh~|gXdy`Ps>{blgxJO6!wRYjz^HQ2A|3rWm~D"

    "|PW;sQQA-"

    "^4*={?#$lHtaR_983_Gpb+Xjr~<ugvyg&zcKE5sBV?kgIrf8o>i^GS83B?o=O}RC0BI?$CQxms<kOZ!#`>E2Xr*CG~0DdQ|s*JLSA-"

    "i2Ht6~BhcBhW2IkD6jW&lEkg9nU?XNO;e^SFupoX^4_P^c=dRHqh`VAXL6osJo%g6y-`;Re0Ts)M?uXf+4wOVfMFrY0x3Y@J4Im_q-"

    "5z%aj@h!}JLET6iOkEl0Uy&Ckyr_R!~eeritekZ6D#!XEhp3Lhrdhgcd4s2sH4w8>We*I$T`MKPw_*EUu#2>Zuu@^+S>D_nrjOAvi2xd)73g"

    "2XL2BkbcUye1{B*6<sND+AGeq=xpg!_hIuWLu3d|4Y5~)GG#x~{R8gS%bPkZvu@ORtJp=vLQgo8S|0{$lY1`ShRViCt?$$b9o5ye!R>UAl<+"

    "N?4X#RU~$ttRwy6j`cI#_3#1ApTBmL3yDlmS60Jw92KyTXEczPgcFgOBUYB-"

    "4pCS7OaS(mJ&a6W9Ux!=boaHL*r*n8LI_7r(J`I)oX+BuY`g_<7-"

    "eX>@qmVTdU7t7D`UxNM?_7_=afAa&PjxnndMMIXT0vj~$5ZZs4DAqUZG&P4&+3PL^!6ETo`54I+ddz*Bjt=^B5W3iT4>MPgeG-"

    "c?A>XiblJN7>J62QS}@oZP^xhp5<S+<WNRIT>ftsb3382l$<6~7j~VRgXxRC%<7r~J~!%-m>zu-rD=497{Qq#99ENAAE?WsGa+!77V;ld&m9"

    "5@uVIIWBlt0MMe{H;0zaB0~w1h`AWLL#Lj4d?SW-75*6Md*V&pye^N{v?`)Hx)rDDY%Sy{xKQX=bZZY`5=Dfib*>85ku<&Ky4!M5%-"

    "z9~^Asvs&oD<>L_gLor&<e{B3pZ^NTM2gG0`}NpmQy^8_Q0AOCb@I*iQ_(taX{@5tPMd9&Cw(e3Pmys+4Mhkmo-wA1dK%>N2|Sqq!4k!2I1F"

    "nRJW+n@qa4k^<U)76T6a`_d^HC&#M#TY&uL=halfB<GpZ>_%Mk)T~2QdC)MB2gwy`zq-"

    "^b9E`=u?jbxv%xF#_S86)s<w}}##0d7K{GA6wBEa9|xByXPi^M=thn%ry4+_QhaykVyxv@c@Y~6icS~b<HZCg4Pi06rye~ll$IGW|Tz*CooJ"

    "SVM&<m`>2`*43Pf#gWNv~~1L6xLDk8-+@~C|w=&w2ty9eWR5D$+)52T)Kq7GTv6@G(DI|{6>-"

    "E9FyKKBxu6JIHs;ju?@S9p&}fcUBf@STaBE1#(bl*`dCbI5P|q5+WsvXM3Cmt6{kK&y%c31OHlH@hW-3<?~??RwA;RFW7-<S6;T-"

    "4xSlg;_B9qr*qW~*sd*Xqv$Vl5!-"

    "mRTqV={5o%<9w8zYVuaWuuUJ*y45kUIEq@xG+8d>YoBK_>G#K21?DApEMvcKCN#mYMsK>qL|15H7i2HWh!W>P9nSy*NC8JcxOg%%?<^%SZ{&"

    "L4%n@ed1z?sUj$$z;Lak0gKO!Si7tY;bG_?0qG~qtD*W#1v$nlxFwqqONy$|#+{!^6d&PndcIEQH$9~oi1U6vk8fR>QwQ1-"

    "1dBpYV0<&qDS`rTf}J7f<pWvmQ3XVlU8QIWnW~5Wc9$>AH|FSW+Lu%{PmSc#BS)x>HFjDS0~vWSM!jJH<P59<<Tl=p+o@CGGB4`0wBg~i5!)"

    "4(*Ldp7Q-"

    "IKIgOFjuY6m*+Md;K!Mwp9rfb+hF@+PxerIsN2hN<BrD5UlKNEKTQ$wWhTNt;q5Cy>Kid7@R7N?J6GL(WxWGN%$<i<oz&Nd62p6y^<?R%39l"

    "^dMH-{uKF*bn%sZg%4zEwHFZyGyR$2YIcl?#uR2el+#_;#*cyfl9n_2jZTWLzJ{AdG~C0iMM3?@`Jtsrdn;G+yHw*O9x-"

    "mph4o7j<Vy&;Gm1qIE52HD1mfpQ1&`)ISdL#Zj&kZk11Xc0`1k0|7h9Ef%A0_?6$yjJ9mhMC?JY=T1dyT*6qH+13*T)F+bw#K5Ktn5(X5Nr5"

    "lhlaS)Y^NWqE^c@hX{@Z}^TiOh|eGl6=m^=Zfc*YDIcwMZS9jC6Ozy?Dk?R)@h~ug$`pNAlpxfEWSTFmzPrJG4RmPcS{VCyXW%Q1cLM91tqr"

    "JOE*PidR<_#n4{nOc^DlP(VuRp>9Lnfr|1zbdV1<u*vD|Wl)J7VTOk}R5O-jfD^-"

    "NsuO%JXJZ?bE$dT$nqa^kHDl<|B9nn>l`*klG%XDCvC?9nKT^Xask*QuM%Qt}6fXyiZRs!hU71^TwYJYbeG9)VW;m1kELbT~FYo%XE_On}4v"

    "Th@)rJNy^pr{)YD*(G4V830<)tLJDaB&|_-YNi;Zewr;pG4YTaZDAPIrUg9t?+n-"

    "h9<?Vj294E%$Gg)2(<f^+{{Ed@shefRQbsY1|01EB8#_zeDUsr$t~^2W1<=H4ehY6`o?HfNEzJQ>dM8PqRB~4H2ld~Qc^dsm8`3$*5w_wswl"

    "drn`vcg>?}NzS%Qk1%$I5pU134v5boyJ3zfIA9+e5zh;r&w7~Qk{m7A0Rb2b{f&>jQEF8SDcIFyi?0{lrqrA1b5Cd~9~N{_|YK&{$HA1Q$s*"

    "xfL(V!ry40EcF7hsjpQ6d_lsKx~{eE#^$8_4x+IyvD+e8;2GSQ@w7*lGsr)$R4;#uDkgt(qEH0VCn(1>5&#?--3D*4M~;1=Qs|bOMxtrgawT"

    "X=h?U2hFe@5y|1%!S6b0g!F0HMebOP`k=DKKqT(GpU0$%4vd&yEpz7+Wisyd2l_F`A<__EqBf9+f09vXe-@|!jVMrCr%-"

    "u|7`QjoiNb`81jFq_Us#HV*u%05dfolnYXNVZgLK9qktZ;ZxjB|O+5*BW7kaTY&^$N>`)pPyA)PaW#AH_(Ok1LJ=k%D{2FGm3?_kGw<8uD5|"

    "vtecwh7HMYOO?=yY!!h}wR$R3q$>mnak_ij{;E93f{IiBn3JnQXt|d<%|O0IS?({QH`oGG)8K3U9cOnv{l-?8x*BsNg-"

    "{K|G;ifM=1#;>GaXYYKS2!lQ_3N+zUM4Kc}g3qf2YScZ!UD4nows=GbE>NVdxE3NIOFDtv+C4!qf-"

    "U0g+jy{u&yW6V;n7PL@KX^b8v8!l2oZ#k!B;Z+&yPTIsGfuHY1clAi1u`q65ms8F2OO`p(;l?uywOBA?(BZ-"

    "kBuKwNxPWjX1(fEvt@uUafI_bQobM<q2wGJXCEdTI>W0;3q&~p7=fO}M~o}kf2L~q8%MV&!v$rjFj-pH+h-"

    ";4ghE2;{ronu12*ksv06ptaYz}F$wj}s#B5A8izinO3`qZJyZ8Pue4RO!cppcEgKc6O%VK9p0X%AV15(-"

    ">@<<AnwB8_QBqBUh{kRnk`1aB8R!@Z74mu%eLkD|(G9Vk4PTRXZ6svBUXm(Hw)Zu{V05yOoF$H=9BgSHEAVy9^!ZdXVRQMx~!YRe7D}ilR4T"

    "acWm|IvBpme>77tQ-NXcIXzlunkgdHHKN(9Yab{Or7I;Z>g5W16T`$3L-UsPEfs`c;+P-H<U~QN<j0`hLJSurU3NH@{*7SBWZEUEsg%-"

    "34a~l@2yWPsoBmcr45^o!fKbULC4>$Omr8Sed(aD9EzD)rus$7U*A_|wmBC^$Rstx7+LAai1Q)x(HX&&O;j;a@VJs8GD9L$WT&Q*3$P!h-"

    "Ftm)z<XW$gT0LiZZ`6&fu*7Q7V08dzbBGcmHeGD_si2UFlBsN$7?lW^+PjqJ27&4jL7p)~ct(RqPm-h{!h*}Gds>Nm!+8UN-"

    "@^>V)9=D2LXg}NB7a^9c%ygigT^>N;kb;6TaCV1P;d*(DYpVh)1FKjw_zG8jW?q<EX%N9q(ck}3|%CXEnP^}(Cd#)3))tHw!WX^uP~yf*^hZ"

    "`#h535yZLIej}~7_7Dzizu3IjM8Efj9D+|U`1{BMlyNTJUgoHOXcA`T|Y_V0^#R(>zD>@t^ySM}!PTpT73<mAv-vcnv0i5V)wRh?iO}GFuao"

    "f?vQ|dz4_q<UD#ImClQdzaR@{T1srPV`6TPmpNI4dQ57(E)2jF(Xa``93{MZ<`<ro=1m*2=X$Ff1!q=9DWqJc#U77gwoERA}qoIx3mCpZE3L"

    "6@rr3iy5xGC0W~Pt}#FbZwOcd$g9ee8MQiVPWjMiajOW!X`|<G0H*;^_VhwC!c?zDPVyy7eG;MK$xmr6=KsJGODVlQ(7D06i>){*p>g+rw;D"

    "i_KV%(|Bkg><om4y?Bll$-"

    "ZW~u{s+TB_>1|%I50B)|Vtg&xON}8e=Ku|R+KggAxO`yuPFM!I|FoCKb6?sYNWBiNBvqx_97og$c_Js$FO_^iK_a&?$0tXK*jAX+v=^Ynov~"

    "LPXrJHNQ7s8m)uB1!hdV!0`l)uP^hO^rY{Kkf*whC4xBGU{>#aiq5|kH@s%l_RRG!Q4U5&Sb3gb-"

    "@_zcSO)ZB4?bI`K9TS<+2=aXZPbsT#_z*@q<Bl`Zr^%xQPh>m_2?q88*P=neYyDFjEBe(LrL5dwuwA8&GWlAiDyPzY7R+I$4+f2e0$#M*V{g"

    "!Zghg0(`EmZ#5-RrAD#5ka3Kab>OrCt=u_M?HRRvRw7r3BFNnoYA}xUJ{|x62FOQBEZ(5oJV3g^VMMC*NmdpG{y&r3-"

    "CkZ2?e6I=)2{F&H6#VC*rHjJb-"

    "k7fJ+4o7g~<SgWEBlG&E(=+a2kptK^noU8psHO!n@1aWi6rD0vF63>N|Df8cW6RsKHw$p@xf+msIE9V#3^Hd)61NxpGH6q1RM0IF>E;}W6nU"

    "h85R}A4H*L4}p5Fs7}=`_BrMav1Bs-$7_I|-o3Se<vsU}Bq!y5F0m$TD3}fJW!Z97UZlq{E@#oBR;QCnfa*--"

    "mpBplCd;dCNI9+iXob$Aog@CB;|9H&VzX94xRjJBw@`UfF__<bTe_RwGbq*{qV{6!pbIXkU)+lTEtZ|G6D58W)%lj;ktb>k5QD<(<jLFa?Rz"

    "<sMboSn9i$Ws>o6mhkOZXrwEHQfe1@t;$6Cs)&nR(eUbJZB`dyR1~oO8NMDiw-"

    "v_6)l{^vz!v=FxyDGyDyjhisei@NQoy^lOoW9kol=&<U>3<UWpnU$rtJ=iK8KhB^NE23GUst_KO3dSW#2mWfFlSlWx-ZB_7(L>En;oSEbi~}"

    "#Vv>kJA*&bOoXYJ?eYxLXg)JjO<z*?gNiarb!X1q1NE5$H^yP9__or#@L8;?b@*1A+tCSYn7*AcBnu4oA3O|$2C=S(MB-"

    ";SxO=Kr^QuQ?8`f3VpT>G&esvgys%uauIPT~iIn!C_4EaX0`JbA?*&b4-"

    "35FGi+*%7Fw#WfW%(JRU@`z!1fs&e<&~?T#7OckG7_&$|dUo|F4OO{^BJRPPLEOV9>T|CZrchsy<$UMe3W!oYjb&>zD~puZz*~%^{nPy=K@%"

    "0_C);S79Z})nNWS@^@JPfI#dl8EJ=Ht7x_2MCS)aoIQoY%d!7`b?0|VDZfRz_fiV5ie7@54EqpA6Ah^3gfQC4f>-"

    "W)@=z(+I|wGgh9Dk7wfHoQ#?iTg>`u<#=)P)-E9lGW1(ol#hz=5b*5RAJ64Fi>H=WF{Du(2<9KIWEhFVVy63)y6p{gF-oC@&pFQpZ&PC2$DD"

    "Fk#uezHq04(w3xcI>m`5O5o(?$e^Dnjg;gb+xG75kfr)^7NI1^2&cFSoObuoj2@SVz@?_9?pZgTeLYz;#<hpTm4aP_O>^*Z2-"

    "m)zp5hVdRRx`wAhMS2Pv2ZE2KD^DB<X&q42iFq^bjd>DHflNoRX`zNM7&sBO%hqeM87Nm@LuyuNr`8l3M?^+gr`Ifs`kiCOfr>ToyWQ;1zf?"

    "B|6VU@#)w-"

    "*zP0_lNavoTb6UGX#W=v|Au60Viq2uFbnA+Wc5lkhD}TmEv3d7_5uwJH5#(!{&nGOZP>{HQ=)B(D#5F24_3AdqbzfjLVh|LnVeiGG1+ARCD;"

    "{<@cd%a5L}K@GOJZhalYUE$j_=--rB-"

    "&$rCj9)*@P!jn`0TV^88k%G+KycL{__J3n1R2anz9H%)hbLU%y60Pd%kd;wJI9We8}2!EFqMLQA6rFPOEVWX9C;t{%H0^P$*;nOx<&+~(20l"

    "|;M^Bc@QXxRhpx=!sGa@sI8!v82WAZs?d;hGGQCKJ(?@TvxySPNI))LCf(cSS8&Xx+wSOu@XNA{eNmYvofdHy0rsh<y!}Z5`sGuOAgPxw#iB"

    "vMH=ZXd1)Ftx4MzGEaiaGZ@eO3Zte8~&QNlHBkP@p4zcL)TQe!ac8t=>?_9Ga?IoY*ko)|xSNMyV3AGWjobbgBI195@mOnZVN%7hZ8&o9R#c"

    "#v<Y=$l43a?Rfzi0r`YrIl8I*@1e(s^hlP`LTpG^}ah%DpMkr7e6rFbP3^o&$PIvZof*L{f)*3B`thEP0D8E~b+9-"

    "l}hs6une3NPea+f$c(JMQ0<Gpb>)&QT#hA9HGW?=*aD*Ubvn^N$4xwkeT3O&-"

    "<cZo<VQC5RAz#$_urQSa4zQO9!JCL?sq%kgT>En@bBfS)>ezQ7V*|I{!g~YRQi&6oj^KB^q4u>eKLrVUmUFsp(vHs!&WD)<=x`q?SFU_aSA{"

    "y)eipy^cmvwhy^ObwFb#MX#w0nGK?Bp_W8LnU=@79POC-"

    "A=^RoeJsm4%uP4MR76<<ol9Ru_xbK_V0YUnOks@k+{T^NQsJxctRZvEBa!@<?qdn7Wo@&6Foa&-"

    "Zc@o8$}qaBx;FH4?Y_w8L<1!&Tx@}xE44iVWp0+@M)j}@Zk!z*vw{CsUJRW6WI$86Qg4)EzNtsmrjNop#o^*8jU2V-"

    "P*LHlDwVa~&pCgDn(@+U2DiDPere{6MjQU=-mP%Ba0?P`K2;AV-"

    "4sosc$c9tfVj2_&=aOl4la#Mpadg*hj^AT?}Yjs9bDzS)tt04LJk#FgTCE%sC5%F7V8V;1Z~ROTo9ySev)AI3W<4jRKbaC3%UvuLHJnS2oN@"

    "2)*PG`35O15)wbIEl+h(EFu3Bfk4~p6)z}{Yew_G&la$&5Kwh96K39TE?|V4??N?WTYFkw7GUa7tAE*s%TdAW$#*M&YK|yW)&nAH{iMurnRE"

    "!Pxq5h5<5p*!i$F<VuLP$v}@0^*q>*CK0U*!RUN|ZPDFUA}lhZ(`mpNq?LcHFQ3jhm~At+?-"

    "#f$CWU(Ym5sSj8p0m&vJGmkuyc>|ZnKE1su{^{vQfM+K#*cuDseG=AbeQL9lShA)ht@z^fC|3ws?k80~;5HIdb=};;6+M6KhqcyC$lC}jwav"

    "7X#p|H_OrAKSj12f6lRG5PL%YeuNo^y{d0i<xq*tj^kMT&q8RXrF-zb2oyUk<O5Y*8F@o$qIZK^Wljdv$oFZSxdghKtY-"

    "+u=o=SoOdtxOu^KULMBGYhpIEPExgz@l`&Lxyp>?1Pq&{%?sGI_j!P%WygxS(&y7>yhMA2tq`6X3V+O_KNty&fsxrR!t^cdzR0<o`yjWj83m"

    "?LEy^tId`0pfATyQ`;sp$Ogl^Vdlo%nC(+j8^XnRD}__!gGEvY*+IX%ifaaCdi=bk)F*git^b*e!rvhDz#8yxjNdnwWd4?j63GGj8j?>|=MJ"

    "EH=2fZ5=Smt3a31aO?%Jf*^_^UcI@<UO13hzl%jtGFUi=R`q&_+r7ny5A~*zqvqmLzk7&*)s^jJ%NtKG~08FW^}d;W;jPD|L`mSCEQ^3^Dv;"

    "p;txlLlyoVianSOly)OUImxz*WNW$&-"

    "mKcVJNf!%tH8yt=DwIst5(<CgS2l6)Scvf8#W=5!>}b8w(cW@Ze$Afk43<5e4(i89sYdeyUQ*rwDO-"

    "{m;TX?6wU7q<K8F5lFM^{+m3RyoI|(q_o&#MsIH>htq?&|>Iac?_44PRK*Yp*(W+`J{+frLZGHMXNAF^b;f=<X?`rB&gY%_3G$g9XAJ%Y!~l"

    "GW1QV)kT5$VaX5Uti>$b(zYy8wd$H#Jb<a423zoz(wO#bar=EoN_^lZS2oNPgoDGSm)#K_;O^#z75<(2Bv1Sc}Rd*hNQa(V52Z9)k{%L@58O"

    "1wdus;7DC=BADnuimuJ6&Qq_tInZ*U^WH3lc(5@6@`R6!C@PqzV=F4^#EQ5Zsx?;_y4~mSy=+$T_H*^!cyU1FGnXdZ!s^k#qiM@#8^3lD+X+"

    "m|@B8&TDs&qstyP+5`K3^Q(YfJ-oAY`OIcz^tHT;94qMxU8T%Prb>ej0r)3)CCWWTB>sFHFA$>ctH%bM+f@1HfJ+PHI|OC9gI1pPjlS(k?~;"

    "{<MRgzD+0^5RddzM*MiMXE>ZHemly#`|@3oq$3t}A~b46v9h76<VRK*#G~{H+tsaBKe|6Dkh}K@?4wB2hqiopNqFbgUwiPRI2`~6;9*qam6f"

    "hQk^UY<beE+ArHyn}j%++C@X??~ZNqTZx8S^~b@s4QCFyaIgp+d^y=t!5VkFg;O$kzzuxAzFD}KP0ap#FKog^+h76U#S#|@|}FW95<uPY{er"

    "pkx<9@oUo&|?dd1kUu%=0tuoyYzNwYWsNnsdx~_deFHPSs$8A3U$VO0o!01?|i_s?~}$~w%Bgr$?~dU9gkO!q(I|@_4V=p#<c27j)CYtVqZX"

    "aR+Zz2E1rG4qoDOt=xj@9F_D}hs_4nReLg(lfmV2m4?0}soJQ0{gq4W+f?V^cvtSiY6xDF>&<Nd%V9^3IP!bcyq4Ld!&b_$NRhflfAiiP5o-"

    ">vbnvn}f3Wyg!6q@5zk!^k5KJY2ST!NV>hVjl(B;w%AVo}SOvV+GNK>L>8?y_S}`RlU@M8!*>5TJG-"

    "1`PIZDjTCJb@a&Dlxm(w0m>4h!|2rhp>A4Q0LZIQr9U+Qk=KVX)?<dXPgH#+464}W?WI6OX+g%NHiL=!i_4QU!RwWRE1b$J#vHY>yGwRzSQl"

    "{ygRH{y`&3l$RY=My$Zq|p$P_&v6#RMKM=D$&1}qOC!nm^Xn9%*}GbFSS@kdfjj5V8tB2OR%@vha@kje3&q`l=OB7e-"

    "uVSf{hY``4B4%%O{sao3a=s0|Z#u?^`a4*-"

    "6)EP_tcudd1+8Tf7$(xWSdyCniXzo*9p+1Q7a&!Jo35*S2>gaJ3<frdpou_A|{u3^B(ohwKYbu4j*McO`yM&nAZV^MBU#F<-"

    "Vpk(<L+UkljEbXcF@8?I=zR?pA|zSqHkg$4VlaNub^;c&<l@4D8L#tSNey?_i>6#V+SbiCkV$|ap6pZVeam&_;sq25H@AXDIl}@cBD=8zQeh"

    "#63dO)38&R<|#Bcv%xzOTR5PYY)#FVk*ZmxYn-bu>UeE_nJVi`mnjOo_h+t8SD=?g<sWnA@rmfR!Pgd3kTJ#^2h^c6(4sni*p3MG12lJG(HB"

    "vs)?p|hzyx*T=2Zxfh06xfq$AiIlIyAbGIdwv8$i>V~J_H!am<y_C`s#Tn#^67erxp<NS8qDpc2`7kQMXh<X#wS0~YVQSo=;`18>;L@M5AZQ"

    "N`|I%L3$8S5Xci7HcwbkykFvh&lQ%)67d+kp1C-A*wh@C-epBV8o-jpIc2ZJg3^%T@FyC$_oUz!Co<Fn&VJExpIuKhcDUbX->A`}hPVD2-"

    "emx4tT9Z=M<}y$>zOWa8?r|;pKofK!KrX?C&&30tuG6S%R_iOs#>XkNVxj+lqli}+id!pG;EXh1);VCCU06()_hs}(%uK=x0>A$rgK5JNQU?"

    "F(FR(4F&J+U%d`>s-zIJ&<73gOnk(Um31%)Jm6^O~#>exciGCw9NqYZ4ncsH>wo4Sc`^dV{aI5iR+Psf-4{`DAMbm#7g?M-l%9_-"

    "dQB3NB@6$Rp8gd*wUxN<_7_TIu%jgiFNT_{&*w6}jvwDwME%J7+id%#mNuI<YYE;>fXDk-"

    "8lN_jO^bzI~xt8K<uNaBE7&1O#ur+YG=Qu{nSh+>yNe2K$h6{Dp(5#}}}vU7*tMbvJr^_FM|2+%WD=Q>-"

    "*(AZ?8*;uW;I`yO?(|c!bV}X;T_h7M(IXvg^8Ol-ZvYGZSQag!x>=RXk+W6)=E{gsIE0-"

    "hUYU5K)AFg9w@rOX}V|N6JHg(}Tw9~e5GLoYr+f!ksH{a1tCM}G6hae`C%%Yf$lVmUTfP4UnQVY-A*TG`8G>LH^5L-=WJE-"

    "xYDgS6;#Y%F3&<%ikcbjofq1~d#!wM2LOp-e-a>FLzg}^p2(%GAi9xZu4R|1?5oT>y!0Y;S+_Yyu=_eFW`{oClO4VKv9!v>DI5;5-"

    "tjfpKlSS6la9XAr7dZI;t&Vx%V)jWdY9<k+evn`0Vt)%SqOb-"

    "!$u*nJ}Bo2@oQ@6p7R|_3Wf??*;7OgfNpdHhp09hMQ#w0Gkb#R5?*i31y{!NP4eK0$ve>Hk|$DGNhYV=K$a_Pe-gv|{IiM)VI>-"

    "z41Iv<B5>L+!7;4(R!T`~huqEtr;REv@;;}u1JYHZu!v}-"

    "Kl3)m3!X*Q^+5H9(bV{NlVa9<^<>~(VRzaukshHKBBHB8D)ad<z@`8f}w;OE)dhhMq_uu{*F^5L)r5Hc<s0mee2rUYSs<}@xOq`C)KHjrI{_"

    "AL%lf06otDWO(f8|NvOg>DIfR+A@;x3q&So75BtOb>8lQPqX$xx3A!=ssT&m9B%7R7j?L<4%?<k!Eg8UNvE2(s<HwdsVd+f~+e>V@QrwO?+_"

    "+0g4kTKmQE_IQiH%HF{}pbtnZuu`IPrS+|V{z>?*2(c{s{>jFyIi<!LRni#fd8RyTY3c|TfJz{*Iz!u$>L{U>iJZwmd!YA8vfXt0GxXelU9h"

    "nk3%$a8dRvk$c`pOKT{k0ed{><`?YibG+n6ZDIo~)9t^TQJHm71sNVT{HTv;AMDrzR2HwblOWrw@U;<jzYyWKtDCF;YDusy0%wy8?+zqF_by"

    "qN+o#7l4@DLm{tQo+w?$5|Bsv)Id&=Q@pNKzCI9R!g#rKQyTeXtPTFo<`Tb>RlgLfVRlP0XDH7&k?H~kRFL2hfbRQme+bce?1&Hsk_tVI8yq"

    "22VzV=NI%~SB{E<Pq3jNU%DiT96VcEio6J2sU&-"

    "3%#csxr;tXz}I>qoNQ>98n*?l6)tQnUaLE8A`q6s>Tk1NIQ3Gyf_eTQpRtK}A=)eeaQ6dym4VsZe$MEK0>pRuI&fv#UR0=06xM?YU8V7DAC8"

    "6E>GUSAkEo6k!C46%}vfb}bLA1gN?dBs^73Yuka=6BFHcsAP3P{&qu!1%u_O^+-jI$x-1ouVp{3j1aHF;bUlDI-CcJaF=@G9Hsa2ZZYnJI6A"

    "-fUbz8q1K**2qKqKhf5O4rXKzx~^vpo8!3#%Y@#v5>zBSdgQqsDl;hN<QsyAMQyYG{ZWlywuywUHU*fs-"

    "s;EPn^1cHa;#YjNfsEwt9HO&z&9lL8PCog~yheOj!15hEFwwaO8ra{zzX}Ea~_i2fo%YaorW^=q$u7h&RR8)JYX(V!&wgYL5<p;1bAUOamIq"

    "=-ajl$Hj3fASwW%%RA&oY-DBNbR@+Q0APoJ)KgFb=7;89_q9C8t3ILbLu@CM(G+TQ?13jn$Ud+;pHglULZ>nE-"

    "o&1REsT{<c9pVq?)6$Kh}%)#S%UVwm645hqaCzKxPsa5rF7>_*bVy(k9Vkf=NbGG7*>Fn}j5*4lL!<2IY9hCTLRizx1W6xDOjZC?^1FI6d#_"

    "mwra1fqeH(J|Ht(`8(mv$=^X4ClT1<M|@#rQ>~T`c7T;YWC4OUb=#q`m$r!AoN5I(=*qEX+T@-"

    "z5F%kV{VDNV?*<Rxu1qyVhH>mBvFHmeI|$)1z+o&Pe2iYVW(&w*LCv~4eeuW7{L%P<QYyPsb3cttmG&SaR=)0jb7Y{)5n^Gp`DlFX++1^W|N"

    "y=q|Es7+I`$hO#ih(>4lZ6{Q4_qPoFqkwWg*{D5wWuSql`@XwclJHCG#oaO@Qn8xfRp$N<owsvaB~L;h6E#L$+G1fbgLCk(9Ku{PoZEzv%Uv"

    "j{`cNo_Y&_oAO*Ksu(F*9fF$8b$eYtA$ZUKNsDZsm@MKxVl(J*~6s^qaIORP~LMt-"

    "7ZdrT3rpMt$UF$6ko+<>ak~)F;$m!VD<3)7Qg*>^Ew>MPGhQ4j}o=)-AixtX!ulHd`N85sMGPJMoNlM_pAK6FPmbC4`hq0I0P-S`NMb!F-"

    "PPQi}oaM+$id}g^;-NvS(L;c$p8zfa=j{4@{y-Oj=%is3}k(`WngA>FdTK75Q)x-*(?dhDV|_U5%_&Q!zFCqz0j;qd64#k-"

    "CbupP5p)bhY(Da}glrY@p>yTUrv4_8eXU=|fFS)1n3bGxtvDUqYoSvG|Y+IqcYkOOK1rY)EXF>o9aI3QNj33oY;J^(9eVunXZT*0Eg~K~?tB"

    "$7+vd#Be#*L$)CK>*-@7C)SAEp2)hsq@MoQzyIfd979?Lk#fhZdRMgPKn)Q==|+8@D+}6EmR!UXh&R`rS|Ws-"

    "B~(tOEWS7eRI^TXJts7z{07;PP_*f0O$j~kc~C`Z9dm=p2;<00mgurn+725Tj1D$pLJXe>7J1}CYRy!!^O3rNwR1p3qw`dvlOlr3ypOq|=KC"

    ">hUumsT8_T18o8de_Hwrw&T|!-5<4FNI+yU2Ja{3HbrrMb_(=q7BH6IEXYVHB|f5#lM2Eu2jJaIOF-"

    "%$#7))4rH@EW+?p79x}8BN*0tt5ZjOma9rd>(6?FqZWGb{*jS@D?e(2V;!sn8uF>fquqf>T_<EkYHF2i+5CGOO}=|(*H-"

    "4;Es@!j(pZMkeI&A&nC;VL^L+?l5BARcONP?@L<nH>{B#KI^rOGO&i9GyA>&5rZRu1>6b*+EyvLKn-"

    "f8bhVH+Yv?;<QQ!?rHZ<~=n#aMi5>Hel}RF#Z-+iV-PM^-13X|QwpC{8E%mX0;Q=HW)8)+5AYXvDwn%xRK@$xNCl8}feNIf7<D!N6Tq+~?-"

    "GS$sO*&mvtgaH6A2#pTeQS((nVt6U;V!&3}9>u&ftftm>a@Baf#=I-("
)
REQUIRED = ["scripts/main.gd", "scripts/data.gd", "scripts/profile.gd", "scripts/keys.gd", "scripts/match.gd", "scenes/main.tscn", "data/roster.json", "addons/vrm/plugin.cfg"]
MODES = ["duel_vs_cpu", "cpu_vs_cpu"]
PLUGIN_FILES = ["addons/Godot-MToon-Shader/plugin.cfg", "addons/vrm/plugin.cfg"]
AUTOLOADS = [
    ("Data", "*res://scripts/data.gd"),
    ("Keys", "*res://scripts/keys.gd"),
    ("Profile", "*res://scripts/profile.gd"),
]


def log(msg):
    print("[FOUNDATION 01] " + str(msg), flush=True)


def load_embedded_sfx():
    return json.loads(zlib.decompress(base64.b85decode(SFX_PATHS_B85)).decode("utf-8"))


def choose_project(explicit):
    if explicit:
        return Path(explicit).expanduser().resolve()
    script_dir = Path(__file__).resolve().parent
    candidates = [DEFAULT_PROJECT, script_dir, Path.cwd()]
    for c in candidates:
        if (c / "scripts/main.gd").is_file() and (c / "scenes/main.tscn").is_file():
            return c.resolve()
    return DEFAULT_PROJECT


def check_required(root):
    missing = [rel for rel in REQUIRED if not (root / rel).is_file()]
    if missing:
        raise RuntimeError(
            "This directory doesn't contain the original Godot files: " + str(root)
            + "\nMissing: " + ", ".join(missing)
            + "\nCopy/extract your existing data.zip folders (scripts, scenes, addons, data)"
            + " into the project root, or use --project to select the right folder."
        )
    for rel in ["data/roster.json", "data/attacks.json", "data/stats.json", "data/economy.json"]:
        p = root / rel
        if p.exists():
            try:
                json.loads(p.read_text(encoding="utf-8-sig"))
            except Exception as exc:
                raise RuntimeError("Invalid project JSON: " + str(p) + " (" + str(exc) + ")")


def ini_section_limits(content, section):
    matches = list(re.finditer(r"(?m)^\[([^\]\r\n]+)\][ \t]*$", content))
    for idx, match in enumerate(matches):
        if match.group(1).strip() == section:
            return match.end(), matches[idx + 1].start() if idx + 1 < len(matches) else len(content)
    return None


def ini_value(content, section, key):
    bounds = ini_section_limits(content, section)
    if bounds is None:
        return None
    block = content[bounds[0]:bounds[1]]
    match = re.search(r"(?m)^" + re.escape(key) + r"[ \t]*=[ \t]*(.*)$", block)
    return match.group(1).strip() if match else None


def ini_set(content, section, key, value, force=False):
    bounds = ini_section_limits(content, section)
    if bounds is None:
        return content.rstrip() + "\n\n[" + section + "]\n" + key + "=" + value + "\n"
    start, end = bounds
    block = content[start:end]
    pat = re.compile(r"(?m)^" + re.escape(key) + r"[ \t]*=[^\r\n]*$")
    if pat.search(block):
        if not force:
            return content
        block = pat.sub(lambda _: key + "=" + value, block, count=1)
        return content[:start] + block + content[end:]
    block = block.rstrip() + "\n" + key + "=" + value + "\n\n"
    return content[:start] + block + content[end:]


def godot_project_file(root):
    cfg = root / "project.godot"
    if cfg.exists():
        text = cfg.read_text(encoding="utf-8-sig")
        if not re.search(r"(?m)^config_version=5\s*$", text):
            log("WARNING: pre-existing project.godot config version differs; preserving it")
    else:
        text = "config_version=5\n"
    text = ini_set(text, "application", "config/name", '"Fight Royale"')
    text = ini_set(text, "application", "run/main_scene", '"res://scenes/main.tscn"', force=True)
    text = ini_set(text, "application", "config/features", 'PackedStringArray("4.4", "GL Compatibility")')
    text = ini_set(text, "display", "window/size/viewport_width", "1280")
    text = ini_set(text, "display", "window/size/viewport_height", "720")
    text = ini_set(text, "display", "window/stretch/mode", '"canvas_items"')
    if not cfg.exists():
        text = ini_set(text, "rendering", "renderer/rendering_method", '"gl_compatibility"')
        text = ini_set(text, "rendering", "renderer/rendering_method.mobile", '"gl_compatibility"')
    # Godot instantiates autoloads in listed order; Data must precede Profile.
    for name, path in AUTOLOADS:
        text = ini_set(text, "autoload", name, '"' + path + '"', force=True)
    present_plugins = ["res://" + p for p in PLUGIN_FILES if (root / p).is_file()]
    existing_setting = ini_value(text, "editor_plugins", "enabled") or ""
    existing_paths = re.findall(r'"(res://[^"\r\n]+/plugin\.cfg)"', existing_setting)
    plugin_order = list(dict.fromkeys(present_plugins + existing_paths))
    if plugin_order:
        packed = "PackedStringArray(" + ", ".join(json.dumps(x) for x in plugin_order) + ")"
        text = ini_set(text, "editor_plugins", "enabled", packed, force=True)
    return text.rstrip() + "\n"


def sfx_scan(root, expected):
    # User's folder is <project>\\sfx; preserve directory names as provided.
    audio_root = root / "sfx"
    if not audio_root.is_dir() and (root / "audio/sfx").is_dir():
        audio_root = root / "audio/sfx"
    found = {}
    if audio_root.is_dir():
        for folder, _dirs, files in os.walk(audio_root):
            for file in files:
                item = Path(folder) / file
                if item.suffix.lower() in (".mp3", ".ogg", ".wav", ".flac"):
                    relative = item.relative_to(audio_root).as_posix()
                    found.setdefault(relative.casefold(), relative)
    matched = {}
    missing = []
    for listed in expected:
        actual = found.get(listed.casefold())
        if actual is None:
            missing.append(listed)
        else:
            matched[listed] = "res://" + audio_root.relative_to(root).as_posix() + "/" + actual
    named = set(x.casefold() for x in expected)
    extra = sorted(x for key, x in found.items() if key not in named)
    catalog = {
        "schema": 1, "sfx_root": "res://" + audio_root.relative_to(root).as_posix(),
        "note": "Only available sounds are mapped. Future audio installer will assign gameplay events.",
        "available": matched, "expected_count": len(expected), "missing_count": len(missing),
        "unlisted_count": len(extra)
    }
    report = {
        "expected_count": len(expected), "present_count": len(matched), "missing_count": len(missing),
        "unlisted_count": len(extra), "missing_examples": missing[:20],
        "unlisted_examples": extra[:20],
        "by_category_expected": dict(sorted(Counter(x.split('/')[0] for x in expected).items())),
        "by_category_present": dict(sorted(Counter(x.split('/')[0] for x in matched).items())),
    }
    return catalog, report, audio_root


def dump_json(obj):
    return json.dumps(obj, ensure_ascii=False, indent=2, sort_keys=True) + "\n"


def gitignore_patch(root):
    path = root / ".gitignore"
    orig = path.read_text(encoding="utf-8-sig") if path.exists() else ""
    desired = [".godot/", ".foundation_backups/", "__pycache__/", "*.pyc"]
    existing = {x.strip() for x in orig.splitlines()}
    additions = [v for v in desired if v not in existing]
    return orig.rstrip() + ("\n\n" if orig.strip() else "") + "\n".join(additions) + "\n" if additions else orig


def filebytes(path):
    try:
        return path.read_bytes()
    except FileNotFoundError:
        return None


def restore(root, backup_dir):
    backup = Path(backup_dir).expanduser().resolve()
    info_path = backup / "backup_manifest.json"
    if not info_path.is_file():
        raise RuntimeError("Backup manifest not found: " + str(info_path))
    info = json.loads(info_path.read_text(encoding="utf-8"))
    if Path(info["project_root"]).resolve() != root.resolve():
        raise RuntimeError("Backup belongs to a different Godot project.")
    for relative in info["changed"]:
        relative_path = Path(relative)
        if relative_path.is_absolute() or ".." in relative_path.parts:
            raise RuntimeError("Unsafe path in backup manifest: " + relative)
        current = root / relative_path
        old = backup / "originals" / relative_path
        if old.is_file():
            current.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(old, current)
            log("Restored: " + relative)
        elif relative in info["created"] and current.is_file():
            current.unlink()
            log("Removed generated file: " + relative)
    log("Restore finished. Open the project again in Godot.")


def atomic_write(path, content):
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + ".foundation_" + uuid.uuid4().hex[:8] + ".tmp")
    try:
        temporary.write_bytes(content)
        os.replace(temporary, path)
    finally:
        if temporary.exists():
            temporary.unlink()


def backup_and_apply(root, changes, dry_run):
    pending = {}
    for rel, text in changes.items():
        target = root / rel
        new_bytes = text.encode("utf-8")
        if filebytes(target) != new_bytes:
            pending[rel] = new_bytes
    if dry_run:
        for rel in pending: log("Would write: " + rel)
        return None, list(pending)
    if not pending:
        log("Already up-to-date; no files changed.")
        return None, []
    stamp = dt.datetime.now().strftime("%Y%m%d-%H%M%S")
    backup = root.parent / (root.name + "_backups") / ("foundation_01_" + stamp + "_" + uuid.uuid4().hex[:6])
    originals = backup / "originals"
    originals.mkdir(parents=True, exist_ok=True)
    created = []
    for rel in pending:
        src = root / rel
        if src.exists():
            dst = originals / rel
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src, dst)
        else:
            created.append(rel)
    (backup / "backup_manifest.json").write_text(dump_json({
        "project_root": str(root), "changed": list(pending), "created": created, "version": VERSION,
    }), encoding="utf-8")
    try:
        for rel, content in pending.items():
            atomic_write(root / rel, content)
            log("Installed: " + rel)
    except Exception:
        log("Installation failed; restoring originals...")
        restore(root, backup)
        raise
    log("Backup: " + str(backup))
    return backup, list(pending)


def godot_binary(explicit):
    if explicit:
        p = Path(explicit).expanduser()
        if p.is_file():
            return str(p.resolve())
        found = shutil.which(explicit)
        if found: return found
        raise RuntimeError("Godot executable not found: " + explicit)
    for name in ("godot", "godot4", "Godot", "godot.exe", "Godot.exe"):
        found = shutil.which(name)
        if found: return found
    return None


def test_godot(root, executable):
    if not executable:
        log("Godot executable not found in PATH. Import/parse tests skipped (run the project in Godot).")
        return {"status": "not_run", "reason": "Godot executable not found; pass --godot PATH"}
    results = []
    for name, args, timeout in [
        ("import", ["--headless", "--path", str(root), "--editor", "--import", "--quit"], 240),
        ("scripts", ["--headless", "--path", str(root), "--script", "res://tools/check_scripts.gd"], 120),
    ]:
        cmd = [executable] + args
        log("Testing with Godot (" + name + ")...")
        try:
            run = subprocess.run(cmd, cwd=str(root), text=True, capture_output=True, errors="replace", timeout=timeout)
            output = ((run.stdout or "") + "\n" + (run.stderr or ""))[-24000:]
            ok = run.returncode == 0 and not ("SCRIPT ERROR" in output or "Parse Error:" in output)
            results.append({"test": name, "ok": ok, "exit_code": run.returncode, "output_tail": output[-14000:]})
            if ok: log("Godot " + name + " check: PASS")
            else: log("Godot " + name + " check: FAILED (see foundation_report.json)")
        except subprocess.TimeoutExpired:
            results.append({"test": name, "ok": False, "error": "timed out"})
            log("Godot " + name + " check: TIMED OUT")
    return {"status": "pass" if all(x["ok"] for x in results) else "fail", "tests": results}


def main():
    p = argparse.ArgumentParser(description="Fight Royale Godot - Foundation Update 01")
    p.add_argument("--project", help="Godot project folder (defaults to your Documents/fight-royale-godot)")
    p.add_argument("--sound-list", help="Optional updated SOUND_LIST.txt on your PC")
    p.add_argument("--godot", help="Full path to Godot executable for import/script checks")
    p.add_argument("--skip-godot", action="store_true", help="Skip Godot executable checks")
    p.add_argument("--dry-run", action="store_true", help="Preview file changes without writing")
    p.add_argument("--restore", help="Restore the original files using a backup folder from this installer")
    args = p.parse_args()
    root = choose_project(args.project)
    log("Project: " + str(root))
    if args.restore:
        if not root.is_dir(): raise RuntimeError("Project folder missing: " + str(root))
        restore(root, args.restore)
        return 0
    check_required(root)
    if args.sound_list:
        sl = Path(args.sound_list).expanduser()
        if not sl.is_file(): raise RuntimeError("Sound list not found: " + str(sl))
        expected = sorted({x.strip().replace("\\", "/") for x in sl.read_text(encoding="utf-8-sig").splitlines()
                          if re.fullmatch(r"[A-Za-z0-9_./ ()-]+\.(?:mp3|wav|ogg|flac)", x.strip(), re.I)})
    else:
        expected = load_embedded_sfx()
    catalog, sfx_report, sfx_folder = sfx_scan(root, expected)
    log("Audio folder: " + str(sfx_folder))
    log("SFX list: " + str(sfx_report["expected_count"]) + "; found: " + str(sfx_report["present_count"]) + "; missing: " + str(sfx_report["missing_count"]))
    if not sfx_folder.exists():
        log("SFX folder does not exist yet; will create it without moving sounds.")
    models = sorted(p.name for p in (root / "models").glob("*.vrm")) if (root / "models").is_dir() else []
    config = {
        "schema": 1, "foundation_version": VERSION,
        "target_modes": MODES,
        "project_scope": "Offline 1v1 only; duel and two AI fighters; no shop/multiplayer/survival/team mode",
        "mode_menus_implementation": "Stage 02 (not yet installed)",
        "asset_directories": {"models": "res://models", "sfx": catalog["sfx_root"], "animations": "res://animations"},
        "character_models_found": models,
    }
    report = {
        "foundation_version": VERSION, "project": str(root),
        "project_structure": {x: (root / x).is_dir() for x in ["models", "scripts", "scenes", "addons", "data", "animations"]},
        "vrm_models": models, "vrm_count": len(models),
        "sfx": sfx_report,
        "notes": ["File list describes audio filenames, not actual audio content or verified suitability.",
                  "No shops/modes/AI behavior have been changed in Update 01.",
                  "Install 02 will replace current mode/menu flow with Duel vs CPU and CPU vs CPU."],
    }
    changes = {
        "project.godot": godot_project_file(root),
        ".gitignore": gitignore_patch(root),
        "data/foundation_config.json": dump_json(config),
        "data/sfx_catalog.json": dump_json(catalog),
        "foundation_report.json": dump_json(report),
    }
    if args.dry_run:
        _, changed = backup_and_apply(root, changes, dry_run=True)
        log("Dry run complete (" + str(len(changed)) + " candidate changes). No files modified.")
        return 0
    backup, changed = backup_and_apply(root, changes, dry_run=False)
    if not sfx_folder.exists():
        sfx_folder.mkdir(parents=True, exist_ok=True)
    log("Models found: " + str(len(models)) + " | Configured project modes: " + ", ".join(MODES))
    if not args.skip_godot:
        result = test_godot(root, godot_binary(args.godot))
        report["godot_validation"] = result
        atomic_write(root / "foundation_report.json", dump_json(report).encode("utf-8"))
        if result["status"] == "fail":
            log("Foundation files installed; existing Godot errors need attention. Validation details: foundation_report.json")
            return 2
    else:
        log("Godot checks were skipped by request.")
    log("FOUNDATION 01 COMPLETE. Next: Stage 02 (Duel vs CPU and CPU vs CPU; no shop).")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as exc:
        log("ERROR: " + str(exc))
        sys.exit(1)
