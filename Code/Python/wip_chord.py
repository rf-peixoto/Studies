# chord64_cli.py - Chord64 command-line encoder/decoder with user-defined tone and CRC8.
import argparse, re, sys
from datetime import datetime
import xml.etree.ElementTree as ET

# ---------------- Core tables & helpers ----------------
PC_TO_NAME = {
    0: ('C', 0), 1: ('C', 1), 2: ('D', 0), 3: ('D', 1),
    4: ('E', 0), 5: ('F', 0), 6: ('F', 1), 7: ('G', 0),
    8: ('G', 1), 9: ('A', 0), 10: ('A', 1), 11: ('B', 0),
}
NOTE_NAME_TO_PC = {v: k for k, v in PC_TO_NAME.items()}
C3_MIDI, B5_MIDI = 48, 83
QUALITY_INTERVALS = {0: [0,4,7], 1: [0,3,7], 2: [0,3,6], 3: [0,4,8], 4: [0,5,7]}
V_START, V_END, V_PAD, V_ESC = 60, 61, 62, 63
CONTROL_ROOTS = {V_START: 0, V_END: 6, V_PAD: 11, V_ESC: 3}
DOM7_INTERVALS = [0,4,7,10]
VERSION_VALUE = 0

def midi_for_pc_in_octave(pc: int, octave: int) -> int: return 12*(octave+1)+pc
def build_closed_voicing(root_midi: int, intervals): return [root_midi+i for i in sorted(intervals)]
def pick_root_midi(pc_root: int, intervals):
    for octave in range(2,7):
        root_midi = midi_for_pc_in_octave(pc_root, octave)
        notes = build_closed_voicing(root_midi, intervals)
        if notes[0] >= C3_MIDI and notes[-1] <= B5_MIDI: return root_midi
    return midi_for_pc_in_octave(pc_root, 3)

# -------- Tone parsing and key signature ----------
MAJOR_FIFTHS = {
    'C':0,'G':1,'D':2,'A':3,'E':4,'B':5,'F#':6,'C#':7,
    'F':-1,'Bb':-2,'Eb':-3,'Ab':-4,'Db':-5,'Gb':-6,'Cb':-7,
}
ALIAS = {'DO':'C','DÓ':'C','C':'C','RE':'D','RÉ':'D','R':'D','D':'D','MI':'E','E':'E',
         'FA':'F','FÁ':'F','F':'F','SOL':'G','G':'G','LA':'A','LÁ':'A','A':'A','SI':'B','B':'B'}
def normalize_note_token(tok: str) -> str:
    t = tok.strip().upper().replace('♯','#').replace('♭','b')
    m = re.match(r'^([A-GRÉDÓFAILOSMN]+)([#b]*)$', t)
    if not m: raise ValueError(f"Invalid tone root '{tok}'")
    base, acc = m.group(1), m.group(2).replace('B','b')
    if base not in ALIAS: raise ValueError(f"Unknown note name '{tok}'")
    root = ALIAS[base]
    name_to_pc = {'C':0,'D':2,'E':4,'F':5,'G':7,'A':9,'B':11}
    pc = name_to_pc[root]
    for ch in acc:
        if ch=='#': pc=(pc+1)%12
        elif ch=='b': pc=(pc-1)%12
    step, alter = PC_TO_NAME[pc]
    return step + ('#' if alter==1 else '')

def parse_tone(s: str):
    s = s.strip()
    m = re.match(r'^([A-Ga-gréRéDóÓfáFámiMiSolSOLLaLáSiSI]+(?:[#♯b♭]{0,2}))\s+(major|minor|maior|menor)$', s, re.IGNORECASE)
    if not m: raise ValueError("Tone must look like 'D minor' or 'F# major'")
    root_tok, mode_tok = m.group(1), m.group(2).lower()
    mode = 'minor' if mode_tok in ('minor','menor') else 'major'
    root_name = normalize_note_token(root_tok)
    if mode=='major':
        major_name = root_name
    else:
        pc_minor = {'C':0,'C#':1,'D':2,'D#':3,'E':4,'F':5,'F#':6,'G':7,'G#':8,'A':9,'A#':10,'B':11}[root_name]
        target_pc = (pc_minor + 3) % 12
        pc_of = {'C':0,'G':7,'D':2,'A':9,'E':4,'B':11,'F#':6,'C#':1,'F':5,'Bb':10,'Eb':3,'Ab':8,'Db':1,'Gb':6,'Cb':11}
        candidates = [k for k,v in pc_of.items() if v%12==target_pc]
        major_name = None
        for pref in ['Cb','Gb','Db','Ab','Eb','Bb','F','C','G','D','A','E','B','F#','C#']:
            if pref in candidates: major_name=pref; break
        if major_name is None: major_name = candidates[0]
    fifths = MAJOR_FIFTHS[major_name]
    ROOT_PC = {'C':0,'C#':1,'D':2,'D#':3,'E':4,'F':5,'F#':6,'G':7,'G#':8,'A':9,'A#':10,'B':11}
    offset_pc = ROOT_PC[root_name]
    return root_name, mode, offset_pc, fifths

# -------- Symbol mapping with tone offset ---------
def symbol_to_midis(v: int, offset_pc: int):
    if 0<=v<=59:
        r = (v%12 + offset_pc) % 12; q = v//12
        intervals = QUALITY_INTERVALS[q]
        return build_closed_voicing(pick_root_midi(r, intervals), intervals)
    elif v in CONTROL_ROOTS:
        r = (CONTROL_ROOTS[v] + offset_pc) % 12
        return build_closed_voicing(pick_root_midi(r, DOM7_INTERVALS), DOM7_INTERVALS)
    else:
        raise ValueError("Invalid symbol")

def midis_to_symbol(midis, offset_pc: int):
    if not midis: return None
    xs = sorted(midis); pcs = [m%12 for m in xs]
    obs_root = pcs[0]; logical_root = (obs_root - offset_pc) % 12
    rel = sorted(((p - obs_root) % 12 for p in set(pcs)))
    if rel == [0,4,7,10]:
        for k, base_root in CONTROL_ROOTS.items():
            if logical_root == base_root: return k
        return None
    for q,intervals in QUALITY_INTERVALS.items():
        if rel == sorted(intervals): return 12*q + logical_root
    return None

# -------- Base64-like chunking & CRC8 ---------
def bytes_to_6bit_values(data: bytes):
    out=[]; i=0; n=len(data)
    while i<n:
        b1=data[i]; i+=1
        b2=data[i] if i<n else None; i+=1 if i<n else 0
        b3=data[i] if i<n else None; i+=1 if i<n else 0
        if b2 is None:
            out += [(b1>>2)&0x3F, ((b1&0x03)<<4)&0x3F, 62, 62]
        elif b3 is None:
            out += [(b1>>2)&0x3F, ((b1&0x03)<<4 | (b2>>4))&0x3F, ((b2&0x0F)<<2)&0x3F, 62]
        else:
            out += [(b1>>2)&0x3F, ((b1&0x03)<<4 | (b2>>4))&0x3F, ((b2&0x0F)<<2 | (b3>>6))&0x3F, b3&0x3F]
    return out
def values_to_bytes(vals):
    out=bytearray()
    for i in range(0,len(vals),4):
        v1,v2,v3,v4 = vals[i:i+4]
        if v3==62 and v4==62:
            b1=((v1&0x3F)<<2)|((v2&0x30)>>4); out.append(b1&0xFF)
        elif v4==62:
            b1=((v1&0x3F)<<2)|((v2&0x30)>>4)
            b2=((v2&0x0F)<<4)|((v3&0x3C)>>2)
            out += bytes([b1&0xFF,b2&0xFF])
        else:
            b1=((v1&0x3F)<<2)|((v2&0x30)>>4)
            b2=((v2&0x0F)<<4)|((v3&0x3C)>>2)
            b3=((v3&0x03)<<6)|(v4&0x3F)
            out += bytes([b1&0xFF,b2&0xFF,b3&0xFF])
    return bytes(out)
def crc8(data: bytes, poly: int=0x07, init: int=0x00) -> int:
    crc=init
    for b in data:
        crc ^= b
        for _ in range(8):
            if crc & 0x80: crc=((crc<<1)^poly)&0xFF
            else: crc=(crc<<1)&0xFF
    return crc

# -------- MusicXML IO with tone metadata ---------
def midi_to_step_alter_oct(midi:int):
    pc=midi%12; step,alter = PC_TO_NAME[pc]; octave=(midi//12)-1; return step,alter,octave
def step_alter_oct_to_midi(step:str, alter:int, octave:int)->int:
    pc=NOTE_NAME_TO_PC[(step,alter)]; return 12*(octave+1)+pc

def write_musicxml(symbols, outfile, tempo_qpm, tone_root, tone_mode, offset_pc, fifths):
    score=ET.Element('score-partwise', version='3.1')
    work=ET.SubElement(score,'work'); ET.SubElement(work,'work-title').text='Chord64 Message'
    ident=ET.SubElement(score,'identification'); enc=ET.SubElement(ident,'encoding')
    ET.SubElement(enc,'software').text='Chord64 CLI Encoder'
    ET.SubElement(enc,'encoding-date').text=datetime.utcnow().isoformat()
    ET.SubElement(enc,'encoding-description').text=f'Chord64 Tone: root={tone_root}, mode={tone_mode}, offset={offset_pc}, fifths={fifths}'
    pl=ET.SubElement(score,'part-list'); sp=ET.SubElement(pl,'score-part', id='P1'); ET.SubElement(sp,'part-name').text='Piano'
    part=ET.SubElement(score,'part', id='P1')
    measure=ET.SubElement(part,'measure', number='1')
    attributes=ET.SubElement(measure,'attributes'); ET.SubElement(attributes,'divisions').text='1'
    time=ET.SubElement(attributes,'time'); ET.SubElement(time,'beats').text='4'; ET.SubElement(time,'beat-type').text='4'
    key=ET.SubElement(attributes,'key'); ET.SubElement(key,'fifths').text=str(fifths); ET.SubElement(key,'mode').text=tone_mode
    direction=ET.SubElement(measure,'direction', placement='above'); dt=ET.SubElement(direction,'direction-type')
    met=ET.SubElement(dt,'metronome'); ET.SubElement(met,'beat-unit').text='quarter'; ET.SubElement(met,'per-minute').text=str(tempo_qpm)
    beats_per_measure=4; beat_in_measure=0; current_no=1
    def new_measure(next_no): return ET.SubElement(part,'measure', number=str(next_no))
    for v in symbols:
        if beat_in_measure>=beats_per_measure:
            current_no+=1; measure=new_measure(current_no); beat_in_measure=0
        midis=symbol_to_midis(v, offset_pc)
        for idx,m in enumerate(midis):
            note=ET.SubElement(measure,'note')
            if idx>0: ET.SubElement(note,'chord')
            pitch=ET.SubElement(note,'pitch'); step,alter,octv=midi_to_step_alter_oct(m)
            ET.SubElement(pitch,'step').text=step
            if alter!=0: ET.SubElement(pitch,'alter').text=str(alter)
            ET.SubElement(pitch,'octave').text=str(octv)
            ET.SubElement(note,'duration').text='1'; ET.SubElement(note,'type').text='quarter'
        beat_in_measure+=1
    tree=ET.ElementTree(score); ET.indent(tree, space='  '); tree.write(outfile, encoding='utf-8', xml_declaration=True)

def read_musicxml_symbols_and_tone(infile: str):
    tree=ET.parse(infile); root=tree.getroot()
    tone_root,tone_mode,offset_pc,fifths='C','major',0,0
    enc_desc=root.find('./identification/encoding/encoding-description')
    if enc_desc is not None and enc_desc.text:
        m=re.search(r'root=([A-G][#b]?),\s*mode=(major|minor),\s*offset=(\d+),\s*fifths=(-?\d+)', enc_desc.text)
        if m:
            tone_root, tone_mode, offset_pc, fifths = m.group(1), m.group(2), int(m.group(3)), int(m.group(4))
    symbols=[]
    for part in root.findall('part'):
        for measure in part.findall('measure'):
            chord=[]
            for note in measure.findall('note'):
                pitch=note.find('pitch')
                if pitch is None: continue
                is_chord = note.find('chord') is not None
                step=pitch.find('step').text
                alter_elem=pitch.find('alter'); alter=int(alter_elem.text) if alter_elem is not None else 0
                octv=int(pitch.find('octave').text)
                midi=12*(octv+1)+NOTE_NAME_TO_PC[(step,alter)]
                if not is_chord and chord:
                    v=midis_to_symbol(chord, offset_pc)
                    if v is None: raise ValueError(f'Unrecognized chord: {chord}')
                    symbols.append(v); chord=[midi]
                else:
                    chord.append(midi)
            if chord:
                v=midis_to_symbol(chord, offset_pc)
                if v is None: raise ValueError(f'Unrecognized chord: {chord}')
                symbols.append(v)
    return symbols, (tone_root, tone_mode, offset_pc, fifths)

# -------- High-level encode/decode ---------
def encode_to_symbols(data: bytes, include_version: bool=True):
    vals=bytes_to_6bit_values(data); syms=[60]
    if include_version: syms.append(0)
    syms += vals; syms.append(61)
    c=crc8(data); hi,lo=divmod(c,60); syms += [hi,lo]; return syms
def decode_from_symbols(symbols):
    if 60 not in symbols or 61 not in symbols: raise ValueError('Missing START/END')
    si=symbols.index(60); ei=symbols.index(61)
    if ei<=si: raise ValueError('END before START')
    if len(symbols)<ei+3: raise ValueError('Missing CRC symbols')
    hi,lo=symbols[ei+1],symbols[ei+2]; expected=hi*60+lo
    payload=symbols[si+1:ei]
    if payload and payload[0]==0: payload=payload[1:]
    if len(payload)%4!=0: raise ValueError('Payload symbol count not multiple of 4')
    data=values_to_bytes(payload); return data, (crc8(data)==expected)

# -------- CLI ---------
def cmd_encode(args):
    with open(args.input,'rb') as f: data=f.read()
    if args.tone:
        root_name, mode, offset_pc, fifths = parse_tone(args.tone)
    else:
        root_name, mode, offset_pc, fifths = 'C','major',0,0
    symbols=encode_to_symbols(data, include_version=True)
    write_musicxml(symbols, args.output, args.tempo, root_name, mode, offset_pc, fifths)
    print(f'Encoded {len(data)} bytes -> {args.output} (tone={root_name} {mode}, offset={offset_pc}, fifths={fifths})')

def cmd_decode(args):
    symbols, tone = read_musicxml_symbols_and_tone(args.input)
    data, ok = decode_from_symbols(symbols)
    if not ok: print('WARNING: CRC mismatch (tamper suspected)', file=sys.stderr)
    with open(args.output,'wb') as f: f.write(data)
    print(f'Decoded -> {args.output}. CRC_OK={ok}. Tone={tone[0]} {tone[1]} (offset={tone[2]}, fifths={tone[3]})')

def build_parser():
    p=argparse.ArgumentParser(prog='chord64', description='Chord64 CLI: encode/decode with tone control and CRC8.')
    sub=p.add_subparsers(dest='cmd', required=True)
    pe=sub.add_parser('encode', help='Encode a file to MusicXML')
    pe.add_argument('-i','--input', required=True); pe.add_argument('-o','--output', required=True)
    pe.add_argument('--tone', help="Key center like 'D minor' or 'F# major'")
    pe.add_argument('--tempo', type=int, default=120, help='Tempo in QPM (default 120)')
    pe.set_defaults(func=cmd_encode)
    pd=sub.add_parser('decode', help='Decode a MusicXML file to binary')
    pd.add_argument('-i','--input', required=True); pd.add_argument('-o','--output', required=True)
    pd.set_defaults(func=cmd_decode); return p

def main(argv=None):
    p=build_parser(); args=p.parse_args(argv); args.func(args)

if __name__=='__main__':
    main()
