import numpy
from PIL import Image # pip install Pillow

for n in range(5):
    a = numpy.random.rand(30,30,3) * 255
    im_out = Image.fromarray(a.astype('uint8')).convert('RGB')
    im_out.save('out%000d.jpg' % n)
