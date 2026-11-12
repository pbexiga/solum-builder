from PIL import Image
im = Image.open(".claude/skills/fit-model/worked/c2458/p-2.png"); print(im.size)
s = im.size[0] / 920
for name, (x0, y0, x1, y1) in {"hfe": (130, 535, 420, 800), "vcs": (495, 535, 800, 800), "vbe": (495, 900, 800, 1150)}.items():
    im.crop((int(x0 * s), int(y0 * s), int(x1 * s), int(y1 * s))).save(f".claude/skills/fit-model/worked/c2458/{name}.png")
