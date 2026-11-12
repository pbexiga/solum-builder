"""Digitise the 2SK209 VGS(OFF)-IDSS line (Toshiba sheet page 2)."""
from PIL import Image; import numpy as np
a=np.array(Image.open('.claude/skills/fit-model/worked/2sk209/voff.png').convert('L'))<110
X0,X1,DX=278,729.5,451.5   # IDSS 1 mA, 10 mA; px per decade
Y1,DY=265,503.6            # |VGS(OFF)| 1 V; px per decade (up = larger)
pts=[]
for x in range(185,780,3):
    col=a[30:612,x]; ys=np.where(col)[0]+30
    runs=np.split(ys,np.where(np.diff(ys)>1)[0]+1) if len(ys) else []
    runs=[r for r in runs if 5<=len(r)<=14]
    if len(runs)==1:
        y=runs[0].mean(); pts.append((10**((x-X0)/DX), 10**((Y1-y)/DY)))
pts=np.array(pts); lx,ly=np.log10(pts[:,0]),np.log10(pts[:,1])
k,b=np.polyfit(lx,ly,1)
print(len(pts),'points; |Voff| = %.4f * Idss_mA^%.4f'%(10**b,k))
print('resid max %.3f dec'%np.abs(ly-(k*lx+b)).max())
for i in (0.7,1,2.6,4.11,4.55,6.5,14): print(i,'mA ->', round(10**b*i**k,3),'V')
keep=np.abs(ly-(k*lx+b))<0.03
k,b=np.polyfit(lx[keep],ly[keep],1)
print(keep.sum(),'kept; |Voff| = %.4f * Idss_mA^%.4f'%(10**b,k), 'resid max %.4f'%np.abs(ly[keep]-(k*lx[keep]+b)).max())
for i in (1,4.11,10): print(i,'mA ->', round(10**b*i**k,3),'V')
