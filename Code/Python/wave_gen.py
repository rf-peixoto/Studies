#ref: https://www.codespeedy.com/how-to-generate-a-sine-wave-sound-in-python/

from struct import pack
from math import sin, pi
import os


output = input("Outputfile: ") + ".au"
freq = int(input("Frequency: "))
duration = int(input("Duration (milliseconds): "))
volume = int(input("Volume: "))

def gen(name, freq, dur, vol):
    fl = open(name, "wb")
    fl.write(pack('>4s5L', '.snd'.encode("utf-8"), 24, 2 * dur, 2, 9000, 1))
    sine_factor = 2 * pi * freq / 8000
    for seg in range(8 * dur):
        sine_segments = sin(seg * sine_factor)
        val = pack('b', int(vol * sine_segments))
        fl.write(val)
    fl.close()
    print("{0} created.".format(name))

gen(output, freq, duration, volume)
