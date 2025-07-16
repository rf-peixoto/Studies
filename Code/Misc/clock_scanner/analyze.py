#!/usr/bin/env python3
"""
analyze.py <outfile>    # produced by collect.c
Prints a coarse activity timeline and keystroke-like spike list.
"""
import sys, struct, pandas as pd, numpy as np, matplotlib.pyplot as plt

rec = struct.Struct('<QQQQ')
rows = []
with open(sys.argv[1], 'rb') as f:
    while (chunk := f.read(rec.size)):
        rows.append(rec.unpack(chunk))

df = pd.DataFrame(rows, columns=['ns','tsc','aperf','mperf'])
df['dt']        = df['ns'].diff().fillna(0) / 1e9                # seconds per sample
df['freq_mhz']  = (df['aperf'].diff() / df['mperf'].diff()) * 100
base            = df['freq_mhz'].median()
thr_active      = base * 1.20                                     # heuristic
thr_keystroke   = base * 1.50

# Boolean masks
df['active']    = df['freq_mhz'] > thr_active
df['spike']     = (df['freq_mhz'] > thr_keystroke) & (df['dt'] < 0.001)

# Aggregate statistics
active_segments = (df['active'].diff() == 1).sum()
spikes          = df['spike'].sum()

print(f"Baseline freq         : {base:.1f} MHz")
print(f"Detected active phases: {active_segments}")
print(f"Keystroke-like spikes : {spikes}")

# Optional quick-look plot
plt.plot(df['ns']/1e9, df['freq_mhz'])
plt.xlabel('time (s)'); plt.ylabel('effective core freq (MHz)')
plt.title('Core-0 APERF/MPERF frequency trace'); plt.show()
