#!/usr/bin/env python3
import random
import copy
from collections import deque
import tkinter as tk
from tkinter import filedialog, messagebox

# ---------- Map generation logic ----------

class Rect:
    """Axis-aligned rectangle on the grid."""
    def __init__(self, x, y, w, h):
        self.x, self.y, self.w, self.h = x, y, w, h

    def intersects(self, other):
        return (self.x < other.x + other.w and
                self.x + self.w > other.x and
                self.y < other.y + other.h and
                self.y + self.h > other.y)

class Room(Rect):
    """A room with an ID and type."""
    def __init__(self, id, x, y, w, h, rtype):
        super().__init__(x, y, w, h)
        self.id = id
        self.type = rtype  # 'normal', 'entrance', 'objective', 'special'
    @property
    def center(self):
        return (self.x + self.w // 2, self.y + self.h // 2)

def manhattan(a, b):
    return abs(a[0] - b[0]) + abs(a[1] - b[1])

class MapGenerator:
    def __init__(self, **cfg):
        self.map_width  = cfg.get('map_width', 32)
        self.map_height = cfg.get('map_height', 32)
        self.room_min_size = cfg.get('room_min_size', 3)
        self.room_max_size = cfg.get('room_max_size', 7)
        self.corridor_min_length = cfg.get('corridor_min_length', 3)
        self.corridor_max_length = cfg.get('corridor_max_length', 15)
        self.normal_room_count_min = cfg.get('normal_room_count_min', 5)
        self.normal_room_count_max = cfg.get('normal_room_count_max', 10)
        self.special_room_count   = cfg.get('special_room_count', 2)
        self.special_room_chance  = cfg.get('special_room_chance', 0.5)
        self.seed = cfg.get('seed') or random.randrange(1 << 30)

    def _add_room(self, room):
        self.rooms.append(room)
        self.rooms_by_id[room.id] = room
        self.adj[room.id] = set()

    def _carve_room(self, room):
        for y in range(room.y, room.y + room.h):
            for x in range(room.x, room.x + room.w):
                self.grid[y][x] = '.'

    def _carve_corridor(self, a, b):
        x1, y1 = a; x2, y2 = b
        if random.choice([True, False]):
            for x in range(min(x1, x2), max(x1, x2) + 1):
                self.grid[y1][x] = '.'
            for y in range(min(y1, y2), max(y1, y2) + 1):
                self.grid[y][x2] = '.'
        else:
            for y in range(min(y1, y2), max(y1, y2) + 1):
                self.grid[y][x1] = '.'
            for x in range(min(x1, x2), max(x1, x2) + 1):
                self.grid[y2][x] = '.'

    def _connect_outside(self, roomA, roomB):
        """Connect two rooms via exactly one corridor tile on each room's perimeter."""
        outsA, outsB = [], []
        for x in range(roomA.x, roomA.x+roomA.w):
            if roomA.y>0:               outsA.append((x,roomA.y-1))
            if roomA.y+roomA.h<self.map_height: outsA.append((x,roomA.y+roomA.h))
        for y in range(roomA.y, roomA.y+roomA.h):
            if roomA.x>0:               outsA.append((roomA.x-1,y))
            if roomA.x+roomA.w<self.map_width:  outsA.append((roomA.x+roomA.w,y))
        for x in range(roomB.x, roomB.x+roomB.w):
            if roomB.y>0:               outsB.append((x,roomB.y-1))
            if roomB.y+roomB.h<self.map_height: outsB.append((x,roomB.y+roomB.h))
        for y in range(roomB.y, roomB.y+roomB.h):
            if roomB.x>0:               outsB.append((roomB.x-1,y))
            if roomB.x+roomB.w<self.map_width:  outsB.append((roomB.x+roomB.w,y))

        start = min(outsA, key=lambda p:manhattan(p,roomB.center))
        end   = min(outsB, key=lambda p:manhattan(p,roomA.center))
        # carve single-touch corridor
        self.grid[start[1]][start[0]] = '.'
        self.grid[end[1]][end[0]] = '.'
        # then main corridor one tile away
        def step(room, px,py):
            cx = min(max(px,room.x),room.x+room.w-1)
            cy = min(max(py,room.y),room.y+room.h-1)
            dx,dy = px-cx, py-cy
            return px+dx, py+dy
        ns = step(roomA, *start)
        ne = step(roomB, *end)
        self.grid[ns[1]][ns[0]] = '.'
        self.grid[ne[1]][ne[0]] = '.'
        self._carve_corridor(ns, ne)
        self.adj[roomA.id].add(roomB.id)
        self.adj[roomB.id].add(roomA.id)

    def _place_normal_rooms(self):
        cnt = random.randint(self.normal_room_count_min, self.normal_room_count_max)
        tries = 0
        while len([r for r in self.rooms if r.type=='normal'])<cnt and tries<cnt*50:
            w,h = random.randint(self.room_min_size,self.room_max_size), random.randint(self.room_min_size,self.room_max_size)
            x,y = random.randint(1,self.map_width-w-1), random.randint(1,self.map_height-h-1)
            r=Rect(x,y,w,h)
            if any(r.intersects(o) for o in self.rooms): tries+=1; continue
            rm=Room(self.next_id,x,y,w,h,'normal'); self.next_id+=1
            self._add_room(rm); self._carve_room(rm)
        if len([r for r in self.rooms if r.type=='normal'])<self.normal_room_count_min:
            raise RuntimeError("Insufficient normal rooms")

    def _connect_normal_rooms(self):
        normals=[r for r in self.rooms if r.type=='normal']
        if not normals:return
        edges=[]
        for i,a in enumerate(normals):
            for b in normals[i+1:]:
                edges.append((manhattan(a.center,b.center),a,b))
        edges.sort(key=lambda e:e[0])
        visited={normals[0].id}; mst=[]
        for d,a,b in edges:
            if len(visited)==len(normals):break
            if ((a.id in visited)^(b.id in visited)) and self.corridor_min_length<=d<=self.corridor_max_length:
                mst.append((a,b)); visited.add(a.id if b.id in visited else b.id)
        if len(visited)<len(normals):
            visited={normals[0].id}; mst=[]
            for d,a,b in edges:
                if len(visited)==len(normals):break
                if (a.id in visited)^(b.id in visited):
                    mst.append((a,b)); visited.add(a.id if b.id in visited else b.id)
        for a,b in mst:
            self._carve_corridor(a.center,b.center)
            self.adj[a.id].add(b.id); self.adj[b.id].add(a.id)

    def _add_loops(self):
        normals=[r for r in self.rooms if r.type=='normal']
        pairs=[]
        for i,a in enumerate(normals):
            for b in normals[i+1:]:
                if b.id in self.adj[a.id]: continue
                d=manhattan(a.center,b.center)
                if self.corridor_min_length<=d<=self.corridor_max_length:
                    pairs.append((a,b))
        random.shuffle(pairs)
        for a,b in pairs[:random.randint(0,len(normals)//2)]:
            self._carve_corridor(a.center,b.center)
            self.adj[a.id].add(b.id); self.adj[b.id].add(a.id)

    def _bfs(self,s,t,adj):
        q=deque([s]); parent={s:None}
        while q:
            c=q.popleft()
            if c==t:break
            for n in adj.get(c,[]):
                if n not in parent:
                    parent[n]=c; q.append(n)
        if t not in parent:return[]
        path=[]; u=t
        while u is not None: path.append(u); u=parent[u]
        return list(reversed(path))

    def _count_normals(self,path):
        return sum(1 for i in path if i in self.rooms_by_id and self.rooms_by_id[i].type=='normal')

    def _place_mandatory(self):
        normals=[r for r in self.rooms if r.type=='normal']
        need=len(normals)//2
        for _ in range(500):
            ent=None
            for _ in range(200):
                w,h=random.randint(self.room_min_size,self.room_max_size),random.randint(self.room_min_size,self.room_max_size)
                side=random.choice(['top','bot','left','right'])
                if side=='top':    x,y=random.randint(1,self.map_width-w-1),1
                elif side=='bot':  x,y=random.randint(1,self.map_width-w-1),self.map_height-h-1
                elif side=='left': x,y=1,random.randint(1,self.map_height-h-1)
                else:              x,y=self.map_width-w-1,random.randint(1,self.map_height-h-1)
                exp=Rect(x-1,y-1,w+2,h+2)
                if any(exp.intersects(o) for o in self.rooms): continue
                dists=sorted([(manhattan((x+w//2,y+h//2),R.center),R) for R in normals],key=lambda t:t[0])
                if not dists: continue
                d,tgt=dists[0]
                if not(self.corridor_min_length<=d<=self.corridor_max_length): continue
                ent=(Room(self.next_id,x,y,w,h,'entrance'),tgt.id)
                break
            if not ent:continue

            obj=None
            for _ in range(200):
                w,h=random.randint(self.room_min_size,self.room_max_size),random.randint(self.room_min_size,self.room_max_size)
                side=random.choice(['top','bot','left','right'])
                if side=='top':    x,y=random.randint(1,self.map_width-w-1),1
                elif side=='bot':  x,y=random.randint(1,self.map_width-w-1),self.map_height-h-1
                elif side=='left': x,y=1,random.randint(1,self.map_height-h-1)
                else:              x,y=self.map_width-w-1,random.randint(1,self.map_height-h-1)
                exp=Rect(x-1,y-1,w+2,h+2)
                if any(exp.intersects(o) for o in self.rooms) or exp.intersects(ent[0]): continue
                dists=sorted([(manhattan((x+w//2,y+h//2),R.center),R) for R in normals],key=lambda t:t[0])
                if not dists: continue
                d,tgt=dists[0]
                if not(self.corridor_min_length<=d<=self.corridor_max_length): continue
                obj=(Room(self.next_id+1,x,y,w,h,'objective'),tgt.id)
                adj2=copy.deepcopy(self.adj)
                adj2[ent[0].id]={ent[1]}; adj2[ent[1]].add(ent[0].id)
                adj2[obj[0].id]={obj[1]}; adj2[obj[1]].add(obj[0].id)
                path=self._bfs(ent[0].id,obj[0].id,adj2)
                if self._count_normals(path)<need: continue
                for rm,tg in (ent,obj):
                    self._add_room(rm); self._carve_room(rm)
                    self._connect_outside(rm,self.rooms_by_id[tg])
                    self.next_id+=1
                return
        raise RuntimeError("Could not place mandatory rooms")

    def _place_special(self):
        normals=[r for r in self.rooms if r.type=='normal']
        for _ in range(self.special_room_count):
            if random.random()>self.special_room_chance: continue
            for _ in range(200):
                w,h=random.randint(self.room_min_size,self.room_max_size),random.randint(self.room_min_size,self.room_max_size)
                x,y=random.randint(1,self.map_width-w-1),random.randint(1,self.map_height-h-1)
                r=Rect(x,y,w,h)
                if any(r.intersects(o) for o in self.rooms): continue
                dists=sorted([(manhattan((x+w//2,y+h//2),R.center),R) for R in normals],key=lambda t:t[0])
                if not dists: continue
                d,tgt=dists[0]
                if not(self.corridor_min_length<=d<=self.corridor_max_length): continue
                rm=Room(self.next_id,x,y,w,h,'special'); self.next_id+=1
                self._add_room(rm); self._carve_room(rm)
                self._connect_outside(rm,tgt)
                break

    def generate(self):
        random.seed(self.seed)
        self.grid=[['#']*self.map_width for _ in range(self.map_height)]
        self.rooms=[]; self.rooms_by_id={}; self.adj={}; self.next_id=0
        self._place_normal_rooms()
        self._connect_normal_rooms()
        self._add_loops()
        self._place_mandatory()
        self._place_special()
        # mark mandatory rooms
        for r in self.rooms:
            if r.type in ('entrance','objective'):
                mark='1' if r.type=='entrance' else '2'
                for yy in range(r.y,r.y+r.h):
                    for xx in range(r.x,r.x+r.w):
                        self.grid[yy][xx]=mark
        return self.grid

# ---------- Dark-theme GUI with Layer Toggles ----------

def draw_blank(canvas):
    canvas.delete("all")

class App(tk.Tk):
    def __init__(self):
        super().__init__()
        # theme
        self.bg='#2e2e2e'; self.fg='#ffffff'
        self.ent_bg='#3c3f41'; self.btn_bg='#5c5f61'; self.hl='#4a4a4a'
        self.canvas_bg='#212121'
        self.title("Procedural Dungeon Generator")
        # defaults & entries
        self.defaults={
            'map_width':32,'map_height':32,
            'room_min_size':3,'room_max_size':7,
            'corridor_min_length':3,'corridor_max_length':15,
            'normal_room_count_min':5,'normal_room_count_max':10,
            'special_room_count':2,'special_room_chance':0.5,
            'tile_size':20,'seed':''
        }
        self.entries={}
        # layer toggles
        self.show_normals=tk.BooleanVar(value=True)
        self.show_corridors=tk.BooleanVar(value=True)
        self.show_mandatory=tk.BooleanVar(value=True)
        self.show_specials=tk.BooleanVar(value=True)
        self.grid_data=None
        self.layers={}
        self._build_ui()

    def _build_ui(self):
        self.config(bg=self.bg)
        # menu
        menubar=tk.Menu(self,bg=self.bg,fg=self.fg)
        filem=tk.Menu(menubar,tearoff=0,bg=self.bg,fg=self.fg)
        filem.add_command(label="Import Map...",command=self.on_import)
        filem.add_command(label="Export Map...",command=self.on_export)
        filem.add_command(label="Save Image...",command=self.on_save_image)
        filem.add_separator(); filem.add_command(label="Exit",command=self.quit)
        menubar.add_cascade(label="File",menu=filem)
        helpm=tk.Menu(menubar,tearoff=0,bg=self.bg,fg=self.fg)
        helpm.add_command(label="About",command=lambda:messagebox.showinfo("About",
            "Procedural Dungeon Generator\nDark Theme\nLayer Toggle")) 
        menubar.add_cascade(label="Help",menu=helpm)
        self.config(menu=menubar)

        ctrl=tk.Frame(self,bg=self.bg); ctrl.pack(side='left',fill='y',padx=5,pady=5)
        row=0
        # parameter fields
        for k,v in self.defaults.items():
            tk.Label(ctrl,text=k.replace('_',' ').title(),bg=self.bg,fg=self.fg).grid(row=row,column=0,sticky='w')
            var=tk.StringVar(value=str(v))
            ent=tk.Entry(ctrl,textvariable=var,bg=self.ent_bg,fg=self.fg,insertbackground=self.fg,
                         relief='flat',width=8)
            ent.grid(row=row,column=1,padx=2,pady=2)
            self.entries[k]=var
            if k=='seed':
                tk.Button(ctrl,text="🎲",command=self.on_random_seed,
                          bg=self.btn_bg,fg=self.fg,bd=0,activebackground=self.hl).grid(row=row,column=2,padx=2)
            row+=1
        # action buttons
        tk.Button(ctrl,text="Generate",command=self.on_generate,
                  bg=self.btn_bg,fg=self.fg,activebackground=self.hl)\
            .grid(row=row,column=0,columnspan=3,pady=5,sticky='we')
        row+=1
        tk.Button(ctrl,text="Reset Defaults",command=self.on_reset,
                  bg=self.btn_bg,fg=self.fg,activebackground=self.hl)\
            .grid(row=row,column=0,columnspan=3,pady=5,sticky='we')
        row+=1
        # layer toggles
        tk.Label(ctrl,text="Layers:",bg=self.bg,fg=self.fg).grid(row=row,column=0,sticky='w')
        row+=1
        tk.Checkbutton(ctrl,text="Normal Rooms",variable=self.show_normals,
                       bg=self.bg,fg=self.fg,selectcolor=self.bg,
                       command=self._redraw).grid(row=row,column=0,columnspan=3,sticky='w')
        row+=1
        tk.Checkbutton(ctrl,text="Corridors",variable=self.show_corridors,
                       bg=self.bg,fg=self.fg,selectcolor=self.bg,
                       command=self._redraw).grid(row=row,column=0,columnspan=3,sticky='w')
        row+=1
        tk.Checkbutton(ctrl,text="Mandatory Rooms",variable=self.show_mandatory,
                       bg=self.bg,fg=self.fg,selectcolor=self.bg,
                       command=self._redraw).grid(row=row,column=0,columnspan=3,sticky='w')
        row+=1
        tk.Checkbutton(ctrl,text="Special Rooms",variable=self.show_specials,
                       bg=self.bg,fg=self.fg,selectcolor=self.bg,
                       command=self._redraw).grid(row=row,column=0,columnspan=3,sticky='w')
        # status bar
        self.status=tk.Label(self,text="Ready",anchor='w',bg=self.bg,fg=self.fg)
        self.status.pack(side='bottom',fill='x')

        # canvas
        ts=int(self.defaults['tile_size'])
        w=int(self.defaults['map_width'])*ts
        h=int(self.defaults['map_height'])*ts
        self.canvas=tk.Canvas(self,width=w,height=h,bg=self.canvas_bg,highlightthickness=0)
        self.canvas.pack(side='right',padx=5,pady=5)

    def _compute_layers(self):
        normals=set(); corridors=set()
        entrance=set(); objective=set(); specials=set()
        # room-based layers
        for r in self.mapgen.rooms:
            coords=[(x,y) for y in range(r.y,r.y+r.h) for x in range(r.x,r.x+r.w)]
            if r.type=='normal': normals.update(coords)
            elif r.type=='entrance': entrance.update(coords)
            elif r.type=='objective': objective.update(coords)
            elif r.type=='special': specials.update(coords)
        # corridor layer = dots not in any room
        for y,row in enumerate(self.mapgen.grid):
            for x,t in enumerate(row):
                if t=='.' and (x,y) not in normals|entrance|objective|specials:
                    corridors.add((x,y))
        self.layers={'normal':normals,'corridor':corridors,
                     'entrance':entrance,'objective':objective,'special':specials}

    def _redraw(self):
        if not self.grid_data: return
        self.canvas.delete("all")
        ts=int(self.entries['tile_size'].get())
        # draw in order
        if self.show_normals.get():
            for x,y in self.layers['normal']:
                self.canvas.create_rectangle(x*ts,y*ts,(x+1)*ts,(y+1)*ts,
                                             fill='#666666',outline='')
        if self.show_corridors.get():
            for x,y in self.layers['corridor']:
                self.canvas.create_rectangle(x*ts,y*ts,(x+1)*ts,(y+1)*ts,
                                             fill='#444444',outline='')
        if self.show_specials.get():
            for x,y in self.layers['special']:
                self.canvas.create_rectangle(x*ts,y*ts,(x+1)*ts,(y+1)*ts,
                                             fill='#3366cc',outline='')
        if self.show_mandatory.get():
            for x,y in self.layers['entrance']:
                self.canvas.create_rectangle(x*ts,y*ts,(x+1)*ts,(y+1)*ts,
                                             fill='#33aa33',outline='')
            for x,y in self.layers['objective']:
                self.canvas.create_rectangle(x*ts,y*ts,(x+1)*ts,(y+1)*ts,
                                             fill='#aa3333',outline='')

    def on_generate(self):
        try:
            params={k:int(self.entries[k].get()) for k in (
                'map_width','map_height','room_min_size','room_max_size',
                'corridor_min_length','corridor_max_length',
                'normal_room_count_min','normal_room_count_max','special_room_count')}
            params['special_room_chance']=float(self.entries['special_room_chance'].get())
            s=self.entries['seed'].get().strip()
            params['seed']=int(s) if s else None
            ts=int(self.entries['tile_size'].get())
            self.mapgen=MapGenerator(**params)
            grid=self.mapgen.generate()
            self.grid_data=grid
            self.entries['seed'].set(str(self.mapgen.seed))
            self.status.config(text="Map generated")
            # compute layers and redraw
            self._compute_layers()
            self._redraw()
            self.title(f"Dungeon Generator – Seed: {self.mapgen.seed}")
            # resize canvas
            self.canvas.config(width=params['map_width']*ts,
                               height=params['map_height']*ts)
        except Exception as e:
            messagebox.showerror("Error",str(e))

    def on_reset(self):
        for k,v in self.defaults.items():
            self.entries[k].set(str(v))
        self.status.config(text="Defaults restored")

    def on_random_seed(self):
        s=random.randrange(1<<30)
        self.entries['seed'].set(str(s))
        self.status.config(text="Seed randomized")

    def on_export(self):
        if not self.grid_data:
            messagebox.showwarning("No map","Generate a map first")
            return
        f=filedialog.asksaveasfilename(defaultextension=".txt",filetypes=[("Text","*.txt")])
        if not f: return
        with open(f,'w') as out:
            for row in self.grid_data: out.write(''.join(row)+'\n')
        messagebox.showinfo("Export",f"Map exported to {f}")

    def on_import(self):
        f=filedialog.askopenfilename(filetypes=[("Text","*.txt")])
        if not f: return
        with open(f) as inp: lines=[l.rstrip('\n') for l in inp]
        self.grid_data=[list(r) for r in lines]
        # fake-up a minimal mapgen for layers
        self.mapgen.grid=self.grid_data
        self.mapgen.rooms=[ ]  # skip detailed rooms on import
        self._compute_layers()
        self._redraw()
        self.status.config(text="Map imported")

    def on_save_image(self):
        if not self.grid_data:
            messagebox.showwarning("No map","Generate a map first")
            return
        f=filedialog.asksaveasfilename(defaultextension=".ps",filetypes=[("PostScript","*.ps")])
        if not f: return
        self.canvas.postscript(file=f)
        messagebox.showinfo("Save Image",f"PostScript saved to {f}")

def main():
    app=App()
    app.mainloop()

if __name__=="__main__":
    main()
