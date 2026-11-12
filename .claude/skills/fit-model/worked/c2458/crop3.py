from PIL import Image
im = Image.open(".claude/skills/fit-model/worked/c2458/p-3.png"); s = im.size[0] / 920
im.crop((int(130 * s), int(180 * s), int(420 * s), int(430 * s))).save(".claude/skills/fit-model/worked/c2458/ft.png")
