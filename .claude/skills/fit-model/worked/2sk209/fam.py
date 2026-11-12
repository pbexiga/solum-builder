"""Read the 2SK209 ID-VGS family (Toshiba sheet page 2) at fixed VGS steps."""
from PIL import Image; import numpy as np
a=np.array(Image.open('.claude/skills/fit-model/worked/2sk209/idvgs.png').convert('L'))<110
X0,DX=790,726.0   # VGS 0 at px 790, 1 V per 726 px
Y0,DY=624,42.57   # ID 0 at px 624, px per mA
grid_rows={27,28,29,70,113,156,198,199,283,369,454,455,539,623,624,625}
for v in [-0.02,-0.05,-0.1,-0.15,-0.2,-0.25,-0.3,-0.35,-0.4,-0.45,-0.5,-0.55,-0.6,-0.7,-0.8]:
    x=int(round(X0+v*DX))
    ys=[y for y in np.where(a[30:622,x])[0]+30]
    runs=np.split(np.array(ys),np.where(np.diff(ys)>1)[0]+1) if ys else []
    c=[r.mean() for r in runs if len(r)>=4]
    print(f"{v:+.2f}", [round((Y0-y)/DY,2) for y in c])
