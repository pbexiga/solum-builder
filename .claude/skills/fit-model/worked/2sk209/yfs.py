"""Digitise the 2SK209 |Yfs|-IDSS line (Toshiba sheet page 2)."""
from PIL import Image; import numpy as np
a=np.array(Image.open('.claude/skills/fit-model/worked/2sk209/yfs.png').convert('L'))<110
X0,DX=277.5,446.0; Y10,DY=360.5,454.0
pts=[]
for x in range(185,790,3):
    ys=np.where(a[50:495,x])[0]+50
    runs=[r for r in (np.split(ys,np.where(np.diff(ys)>1)[0]+1) if len(ys) else []) if 5<=len(r)<=14]
    if len(runs)==1: pts.append((10**((x-X0)/DX), 10*10**((Y10-runs[0].mean())/DY)))
p=np.array(pts); lx,ly=np.log10(p[:,0]),np.log10(p[:,1])
for _ in range(2):
    k,b=np.polyfit(lx,ly,1); keep=np.abs(ly-(k*lx+b))<0.03; lx,ly=lx[keep],ly[keep]
print(len(lx),'pts; |Yfs| = %.3f mS * Idss_mA^%.4f'%(10**b,k))
for i in (1,4.11,10): print(i,'mA ->', round(10**b*i**k,2),'mS')
