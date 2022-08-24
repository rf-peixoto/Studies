from PIL import Image
import sys

def include(img, content, out_file):
    print("[*] Opening source: {0}".format(img))
    source = Image.open(img)
    print("[*] Opening message: {0}".format(content))
    data = Image.open(content)
    data = data.resize(source.size)
    data = data.convert('1')
    print("[*] Prepare output: {0}".format(out_file))
    output = Image.new('RGB', source.size)
    print("[*] Hiding message.")
    width, height = source.size
    bmp = []
    for h in range(height):
        for w in range(width):
            ip = source.getpixel((w,h))
            hp = data.getpixel((w,h))
            if hp == 0:
                newred = ip[0] & 254
            else:
                newred = ip[0] | 1
            bmp.append((newred, ip[1], ip[2]))
    print("[*] Exporting output.")
    output.putdata(bmp)
    output.save(out_file)


def extract(img, output):
    print("[*] Opening source: {0}".format(img))
    source = Image.open(img)
    print("[*] Preparing output.")
    out = Image.new('L', source.size)
    width, height = source.size
    bmp = []
    print("[*] Extracting message.")
    for h in range(height):
        for w in range(width):
            ip = source.getpixel((w, h))
            if ip[0] & 1 == 0:
                bmp.append(0)
            else:
                bmp.append(255)

    print("[*] Exporting output.")
    out.putdata(bmp)
    out.save(output)

# Select Mode:
if sys.argv[1].lower() == "i":
    include(sys.argv[2], sys.argv[3], sys.argv[4])
elif sys.argv[1].lower() == "e":
    extract(sys.argv[2], sys.argv[3])
