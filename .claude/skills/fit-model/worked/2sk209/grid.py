import sys
from PIL import Image; import numpy as np
a=np.array(Image.open(sys.argv[1]).convert('L'))<110
h,w=a.shape; print(h,w)
print('vcols',[x for x in range(w) if a[int(h*0.75):int(h*0.93),x].mean()>0.9])
print('hrows',[y for y in range(h) if a[y,int(w*0.6):int(w*0.9)].mean()>0.9])
