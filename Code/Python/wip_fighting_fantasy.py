import tkinter as tk
from tkinter import ttk, messagebox
import random

class Enemy:
    def __init__(self, name, skill, stamina):
        self.name = name
        self.skill = skill
        self.stamina = stamina

class FightingFantasyApp(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("Fighting Fantasy – Warlock of Firetop Mountain")
        self.resizable(True, True)

        # Define map position and history to avoid attribute errors
        self.position = [0, 0]
        self.history = [(0, 0)]

        self.apply_dark_theme()

        # Player base (initial) and current attributes
        self.initial_skill = 0
        self.initial_stamina = 0
        self.initial_luck = 0
        self.skill = 0
        self.stamina = 0
        self.max_stamina = 0
        self.luck = 0
        self.gold = 0  # Gold is only adjusted manually

        # Consumables (dictionary: item -> count)
        self.consumable_types = {
            "Healing Potion": "Restores 4 stamina (capped at initial value)",
            "Elixir of Luck": "Increases luck by 2",
            "Strength Tonic": "Increases skill by 1",
            "Magic Elixir": "Restores 3 stamina (capped) and increases luck by 1",
            "Provisions": "Recovers 4 stamina per meal (capped)",
            "Key": "A key to unlock treasure chests"
        }
        self.consumables = {}

        # Treasure Inventory (dictionary: item -> count)
        self.treasure_types = {
            "Jewel": "A valuable jewel",
            "Gemstone": "A precious gemstone",
            "Gold Sentinel": "A sentinel made of gold",
            "Diamond Sentinel": "A sentinel made of diamond"
        }
        self.treasure = {}

        # Equipment items (dictionary: item -> attributes)
        self.equipment_types = {
            "Magic Sword": {"description": "Increases Skill by 2 (affects initial Skill)", "skill": 2, "stamina": 0, "luck": 0, "affects_initial": True},
            "Shield": {"description": "Increases Stamina by 3", "skill": 0, "stamina": 3, "luck": 0, "affects_initial": False},
            "Chainmail": {"description": "Increases Stamina by 4", "skill": 0, "stamina": 4, "luck": 0, "affects_initial": False},
            "Helmet": {"description": "Increases Stamina by 2", "skill": 0, "stamina": 2, "luck": 0, "affects_initial": False},
            "Magic Amulet": {"description": "Increases Luck by 2", "skill": 0, "stamina": 0, "luck": 2, "affects_initial": False},
            "Boots": {"description": "Increases Skill by 1", "skill": 1, "stamina": 0, "luck": 0, "affects_initial": False},
            "Ring of Strength": {"description": "Increases Skill by 1 and Stamina by 1", "skill": 1, "stamina": 1, "luck": 0, "affects_initial": False},
            "Magic Cloak": {"description": "Increases Luck by 1 and Stamina by 2", "skill": 0, "stamina": 2, "luck": 1, "affects_initial": False},
            "Dagger": {"description": "Increases Skill by 1", "skill": 1, "stamina": 0, "luck": 0, "affects_initial": False},
            "Potion of Skill": {"description": "Restores Skill to its initial value", "potion": True},
            "Potion of Strength": {"description": "Restores Stamina to its initial value", "potion": True},
            "Potion of Fortune": {"description": "Restores Luck to its initial value and increases initial Luck by 1", "potion": True}
        }
        self.equipped = {}

        # Enemies (from the first book)
        self.enemy_types = {
            "Orc": {"skill": 10, "stamina": 12},
            "Goblin": {"skill": 9, "stamina": 8},
            "Skeleton": {"skill": 8, "stamina": 6},
            "Giant Spider": {"skill": 11, "stamina": 10},
            "Ogre": {"skill": 12, "stamina": 14},
            "Warlock": {"skill": 15, "stamina": 20},
            "Bird Man": {"skill": 12, "stamina": 8},
            "Messenger of Death": {"skill": 7, "stamina": 6},
            "Earth Demon": {"skill": 12, "stamina": 15},
            "Barbarian": {"skill": 7, "stamina": 6},
            "Vampire": {"skill": 8, "stamina": 8},
            "Werewolf": {"skill": 8, "stamina": 8},
            "Wight": {"skill": 9, "stamina": 6}
        }
        # No gold drops on enemy defeat
        self.gold_rewards = {}

        self.enemies = []

        self.create_widgets()

    def apply_dark_theme(self):
        self.configure(bg="#2e2e2e")
        style = ttk.Style(self)
        style.theme_use("clam")
        style.configure("TFrame", background="#2e2e2e")
        style.configure("TLabel", background="#2e2e2e", foreground="white")
        style.configure("TButton", background="#3e3e3e", foreground="white")
        style.configure("TCheckbutton", background="#2e2e2e", foreground="white")
        style.configure("TLabelframe", background="#2e2e2e", foreground="white")
        style.configure("TLabelframe.Label", background="#2e2e2e", foreground="white")

    def create_widgets(self):
        # ----------- TOP FRAME: Attributes, Gold, Dice -----------
        top_frame = ttk.Frame(self)
        top_frame.pack(side="top", fill="x", padx=5, pady=5)

        attr_frame = ttk.Frame(top_frame)
        attr_frame.pack(side="left", fill="x", expand=True)
        ttk.Button(attr_frame, text="Roll Stats", command=self.roll_attributes).pack(side="left", padx=5)
        self.attr_label = ttk.Label(attr_frame, text="Skill: - | Stamina: -/- | Luck: - | Gold: -")
        self.attr_label.pack(side="left", padx=5)

        gold_control = ttk.Frame(attr_frame)
        gold_control.pack(side="left", padx=10)
        ttk.Label(gold_control, text="Gold Amount:").pack(side="left")
        self.gold_entry = ttk.Entry(gold_control, width=5)
        self.gold_entry.pack(side="left", padx=2)
        ttk.Button(gold_control, text="Add Gold", command=self.add_gold).pack(side="left", padx=2)
        ttk.Button(gold_control, text="Remove Gold", command=self.remove_gold).pack(side="left", padx=2)

        dice_frame = ttk.Frame(top_frame)
        dice_frame.pack(side="right", fill="x")
        ttk.Button(dice_frame, text="1D6", command=lambda: self.roll_dice(1)).pack(side="left", padx=5)
        ttk.Button(dice_frame, text="2D6", command=lambda: self.roll_dice(2)).pack(side="left", padx=5)
        self.dice_result_label = ttk.Label(dice_frame, text="Result: -")
        self.dice_result_label.pack(side="left", padx=5)

        # ----------- MIDDLE FRAME: Left Column (Inventories/Equipment) and Right Column (Enemy Setup/Battle) -----------
        middle_frame = ttk.Frame(self)
        middle_frame.pack(side="top", fill="both", expand=True, padx=5, pady=5)

        # LEFT COLUMN
        left_col = ttk.Frame(middle_frame)
        left_col.pack(side="left", fill="both", expand=True)

        # Consumables Inventory
        inv_frame = ttk.Labelframe(left_col, text="Consumables Inventory")
        inv_frame.pack(fill="both", expand=False, pady=5)
        self.inv_listbox = tk.Listbox(inv_frame, height=5, bg="#3e3e3e", fg="white")
        self.inv_listbox.pack(side="left", fill="both", expand=True, padx=5, pady=5)
        inv_controls = ttk.Frame(inv_frame)
        inv_controls.pack(side="right", padx=5, fill="y")
        ttk.Label(inv_controls, text="Select Consumable:").pack(pady=2)
        self.item_combobox = ttk.Combobox(inv_controls, values=list(self.consumable_types.keys()), state="readonly")
        self.item_combobox.pack(pady=2)
        ttk.Button(inv_controls, text="Add Consumable", command=self.add_consumable).pack(fill="x", pady=2)
        ttk.Button(inv_controls, text="Use Consumable", command=self.use_consumable).pack(fill="x", pady=2)
        ttk.Button(inv_controls, text="Remove Consumable", command=self.remove_consumable).pack(fill="x", pady=2)

        # Treasure Inventory
        treasure_frame = ttk.Labelframe(left_col, text="Treasure Inventory")
        treasure_frame.pack(fill="both", expand=False, pady=5)
        self.treasure_listbox = tk.Listbox(treasure_frame, height=5, bg="#3e3e3e", fg="white")
        self.treasure_listbox.pack(side="left", fill="both", expand=True, padx=5, pady=5)
        treasure_controls = ttk.Frame(treasure_frame)
        treasure_controls.pack(side="right", padx=5, fill="y")
        ttk.Label(treasure_controls, text="Select Treasure:").pack(pady=2)
        self.treasure_combobox = ttk.Combobox(treasure_controls, values=list(self.treasure_types.keys()), state="readonly")
        self.treasure_combobox.pack(pady=2)
        ttk.Button(treasure_controls, text="Add Treasure", command=self.add_treasure).pack(fill="x", pady=2)
        ttk.Button(treasure_controls, text="Remove Treasure", command=self.remove_treasure).pack(fill="x", pady=2)

        # Equipment Panel
        equip_frame = ttk.Labelframe(left_col, text="Equipment")
        equip_frame.pack(fill="both", expand=False, pady=5)
        equip_controls = ttk.Frame(equip_frame)
        equip_controls.pack(side="left", padx=5, fill="y")
        ttk.Label(equip_controls, text="Select Equipment:").pack(pady=2)
        self.equip_combobox = ttk.Combobox(equip_controls, values=list(self.equipment_types.keys()), state="readonly")
        self.equip_combobox.pack(pady=2)
        ttk.Button(equip_controls, text="Equip Item", command=self.equip_item).pack(fill="x", pady=2)
        self.equipped_listbox = tk.Listbox(equip_frame, height=5, bg="#3e3e3e", fg="white")
        self.equipped_listbox.pack(side="left", fill="both", expand=True, padx=5, pady=5)

        # RIGHT COLUMN
        right_col = ttk.Frame(middle_frame)
        right_col.pack(side="right", fill="both", expand=True)

        # Enemy Setup Panel
        enemy_setup_frame = ttk.Labelframe(right_col, text="Enemy Setup")
        enemy_setup_frame.pack(fill="both", expand=False, pady=5)
        custom_frame = ttk.Frame(enemy_setup_frame)
        custom_frame.pack(fill="x", pady=2)
        ttk.Label(custom_frame, text="Custom Enemy:").pack(side="left", padx=5)
        self.enemy_name = ttk.Entry(custom_frame, width=10)
        self.enemy_name.pack(side="left", padx=2)
        self.enemy_skill = ttk.Entry(custom_frame, width=5)
        self.enemy_skill.pack(side="left", padx=2)
        self.enemy_stamina = ttk.Entry(custom_frame, width=5)
        self.enemy_stamina.pack(side="left", padx=2)
        ttk.Button(custom_frame, text="Add Custom", command=self.add_enemy_custom).pack(side="left", padx=5)
        list_frame = ttk.Frame(enemy_setup_frame)
        list_frame.pack(fill="x", pady=2)
        ttk.Label(list_frame, text="Choose Enemy:").pack(side="left", padx=5)
        self.enemy_combobox = ttk.Combobox(list_frame, values=list(self.enemy_types.keys()), state="readonly", width=20)
        self.enemy_combobox.pack(side="left", padx=2)
        ttk.Button(list_frame, text="Add Selected", command=self.add_enemy_from_list).pack(side="left", padx=5)

        # Battle Enemies List
        battle_frame = ttk.Labelframe(right_col, text="Battle Enemies")
        battle_frame.pack(fill="both", expand=False, pady=5)
        self.enemies_listbox = tk.Listbox(battle_frame, height=5, bg="#3e3e3e", fg="white")
        self.enemies_listbox.pack(fill="both", expand=True, padx=5, pady=5)

        # Combat Controls
        combat_frame = ttk.Frame(right_col)
        combat_frame.pack(fill="x", pady=5)
        ttk.Button(combat_frame, text="Attack", command=self.attack).pack(side="left", padx=5)
        self.luck_var = tk.BooleanVar()
        ttk.Checkbutton(combat_frame, text="Use Luck", variable=self.luck_var).pack(side="left", padx=5)
        ttk.Button(combat_frame, text="Flee", command=self.flee).pack(side="left", padx=5)

        # ----------- BOTTOM FRAME: Map and Movement -----------
        bottom_frame = ttk.Frame(self)
        bottom_frame.pack(side="bottom", fill="x", padx=5, pady=5)
        self.canvas = tk.Canvas(bottom_frame, width=300, height=150, bg="#333333")
        self.canvas.pack(side="left", padx=5)
        move_frame = ttk.Frame(bottom_frame)
        move_frame.pack(side="left", padx=5)
        for d in ["North", "South", "East", "West"]:
            ttk.Button(move_frame, text=d, command=lambda dir=d: self.move(dir)).pack(side="top", pady=2)
        self.update_map()

    # ---------- Attributes/Gold ----------
    def roll_attributes(self):
        self.initial_skill = random.randint(1, 6) + 6
        self.initial_stamina = random.randint(1, 6) + random.randint(1, 6) + 12
        self.initial_luck = random.randint(1, 6) + 6
        self.skill = self.initial_skill
        self.stamina = self.initial_stamina
        self.max_stamina = self.initial_stamina
        self.luck = self.initial_luck
        self.gold = 0
        self.equipped.clear()
        self.equipped_listbox.delete(0, 'end')
        self.update_attributes()

    def update_attributes(self):
        self.attr_label.config(text=f"Skill: {self.skill} | Stamina: {self.stamina}/{self.max_stamina} | Luck: {self.luck} | Gold: {self.gold}")

    def add_gold(self):
        try:
            amount = int(self.gold_entry.get())
        except ValueError:
            messagebox.showerror("Input Error", "Enter a valid number for gold.")
            return
        self.gold += amount
        self.update_attributes()

    def remove_gold(self):
        try:
            amount = int(self.gold_entry.get())
        except ValueError:
            messagebox.showerror("Input Error", "Enter a valid number for gold.")
            return
        self.gold = max(0, self.gold - amount)
        self.update_attributes()

    # ---------- Dice ----------
    def roll_dice(self, n):
        rolls = [random.randint(1, 6) for _ in range(n)]
        self.dice_result_label.config(text=f"{rolls} (Total: {sum(rolls)})")

    # ---------- Consumables ----------
    def add_consumable(self):
        item = self.item_combobox.get()
        if item:
            self.consumables.setdefault(item, 0)
            self.consumables[item] += 1
            self.refresh_consumables()

    def refresh_consumables(self):
        self.inv_listbox.delete(0, 'end')
        for item, count in self.consumables.items():
            self.inv_listbox.insert('end', f"{item} x{count}")

    def use_consumable(self):
        selection = self.inv_listbox.curselection()
        if not selection:
            messagebox.showinfo("Use Consumable", "Select a consumable to use.")
            return
        entry = self.inv_listbox.get(selection[0])
        item = entry.split(" x")[0]
        if self.apply_consumable_effect(item):
            self.consumables[item] -= 1
            if self.consumables[item] <= 0:
                del self.consumables[item]
            self.refresh_consumables()

    def remove_consumable(self):
        selection = self.inv_listbox.curselection()
        if selection:
            entry = self.inv_listbox.get(selection[0])
            item = entry.split(" x")[0]
            del self.consumables[item]
            self.refresh_consumables()

    def apply_consumable_effect(self, item):
        if item == "Healing Potion":
            heal = 4
            old = self.stamina
            self.stamina = min(self.stamina + heal, self.initial_stamina)
            messagebox.showinfo("Consumable Used", f"Healing Potion used. Stamina: {old} -> {self.stamina}.")
        elif item == "Elixir of Luck":
            old = self.luck
            self.luck += 2
            messagebox.showinfo("Consumable Used", f"Elixir of Luck used. Luck: {old} -> {self.luck}.")
        elif item == "Strength Tonic":
            old = self.skill
            self.skill = min(self.skill + 1, self.initial_skill)
            messagebox.showinfo("Consumable Used", f"Strength Tonic used. Skill: {old} -> {self.skill}.")
        elif item == "Magic Elixir":
            heal = 3
            old_stam = self.stamina
            self.stamina = min(self.stamina + heal, self.initial_stamina)
            old_luck = self.luck
            self.luck += 1
            messagebox.showinfo("Consumable Used", f"Magic Elixir used. Stamina: {old_stam} -> {self.stamina}, Luck: {old_luck} -> {self.luck}.")
        elif item == "Provisions":
            heal = 4
            old = self.stamina
            self.stamina = min(self.stamina + heal, self.initial_stamina)
            messagebox.showinfo("Consumable Used", f"Provisions used. Stamina: {old} -> {self.stamina}.")
        elif item == "Key":
            messagebox.showinfo("Consumable Used", "Key kept for unlocking purposes.")
        else:
            messagebox.showinfo("Consumable Used", "This item has no special effect.")
        self.update_attributes()
        return True

    # ---------- Treasure ----------
    def add_treasure(self):
        item = self.treasure_combobox.get()
        if item:
            self.treasure.setdefault(item, 0)
            self.treasure[item] += 1
            self.refresh_treasure()

    def refresh_treasure(self):
        self.treasure_listbox.delete(0, 'end')
        for item, count in self.treasure.items():
            self.treasure_listbox.insert('end', f"{item} x{count}")

    def remove_treasure(self):
        selection = self.treasure_listbox.curselection()
        if selection:
            entry = self.treasure_listbox.get(selection[0])
            item = entry.split(" x")[0]
            del self.treasure[item]
            self.refresh_treasure()

    # ---------- Equipment ----------
    def equip_item(self):
        equip_name = self.equip_combobox.get()
        if not equip_name:
            messagebox.showerror("Equipment Error", "Select an equipment item to equip.")
            return
        data = self.equipment_types[equip_name]
        if data.get("affects_initial", False):
            for eqp in self.equipped.values():
                if eqp.get("affects_initial", False):
                    messagebox.showinfo("Equipment", "You already have a magic weapon equipped. Unequip it first.")
                    return
        if equip_name in self.equipped:
            messagebox.showinfo("Equipment", f"{equip_name} is already equipped.")
            return
        self.equipped[equip_name] = data
        self.equipped_listbox.insert('end', f"{equip_name}: {data['description']}")
        if data.get("potion", False):
            if equip_name == "Potion of Skill":
                self.skill = self.initial_skill
                messagebox.showinfo("Potion", "Skill restored to its initial value.")
            elif equip_name == "Potion of Strength":
                self.stamina = self.initial_stamina
                self.max_stamina = self.initial_stamina
                messagebox.showinfo("Potion", "Stamina restored to its initial value.")
            elif equip_name == "Potion of Fortune":
                self.initial_luck += 1
                self.luck = self.initial_luck
                messagebox.showinfo("Potion", "Luck restored to its initial value and increased by 1.")
        else:
            bonus_skill = data.get("skill", 0)
            bonus_stamina = data.get("stamina", 0)
            bonus_luck = data.get("luck", 0)
            if data.get("affects_initial", False):
                self.initial_skill += bonus_skill
                self.skill += bonus_skill
            else:
                self.skill = min(self.skill + bonus_skill, self.initial_skill)
            self.max_stamina += bonus_stamina
            self.stamina = min(self.stamina + bonus_stamina, self.max_stamina)
            self.luck = min(self.luck + bonus_luck, self.initial_luck)
        self.update_attributes()
        messagebox.showinfo("Equipment", f"{equip_name} equipped. Stats updated.")

    # ---------- Movement / Map ----------
    def move(self, direction):
        moves = {"North": (0, -1), "South": (0, 1), "East": (1, 0), "West": (-1, 0)}
        dx, dy = moves[direction]
        self.position[0] += dx
        self.position[1] += dy
        if tuple(self.position) not in self.history:
            self.history.append(tuple(self.position))
        self.update_map()

    def update_map(self):
        self.canvas.delete("all")
        scale = 20
        offset = [150 - self.position[0]*scale, 75 - self.position[1]*scale]
        for x, y in self.history:
            self.canvas.create_rectangle(
                offset[0]+x*scale, offset[1]+y*scale,
                offset[0]+(x+1)*scale, offset[1]+(y+1)*scale,
                fill="#555555"
            )
        px, py = self.position
        self.canvas.create_rectangle(
            offset[0]+px*scale, offset[1]+py*scale,
            offset[0]+(px+1)*scale, offset[1]+(py+1)*scale,
            fill="blue"
        )

    # ---------- Enemy/Battle ----------
    def add_enemy_custom(self):
        try:
            enemy_skill = int(self.enemy_skill.get())
            enemy_stamina = int(self.enemy_stamina.get())
        except ValueError:
            messagebox.showerror("Input Error", "Enemy Skill and Stamina must be numbers.")
            return
        enemy_name = self.enemy_name.get().strip()
        if not enemy_name:
            messagebox.showerror("Input Error", "Enemy name must be provided.")
            return
        new_enemy = Enemy(enemy_name, enemy_skill, enemy_stamina)
        self.enemies.append(new_enemy)
        self.update_battle_list()

    def add_enemy_from_list(self):
        enemy_name = self.enemy_combobox.get()
        if not enemy_name:
            messagebox.showerror("Selection Error", "Select an enemy from the list.")
            return
        data = self.enemy_types.get(enemy_name)
        if data:
            new_enemy = Enemy(enemy_name, data["skill"], data["stamina"])
            self.enemies.append(new_enemy)
            self.update_battle_list()

    def update_battle_list(self):
        self.enemies_listbox.delete(0, 'end')
        for idx, e in enumerate(self.enemies, start=1):
            self.enemies_listbox.insert('end', f"{idx}. {e.name}: {e.stamina} HP")

    def test_luck(self):
        if self.luck <= 0:
            return False
        roll = random.randint(1, 6) + random.randint(1, 6)
        result = roll <= self.luck
        self.luck = max(self.luck - 1, 0)
        self.update_attributes()
        return result

    def attack(self):
        if not self.enemies:
            messagebox.showinfo("Combat", "No enemy present.")
            return
        combat_log = ""
        for enemy in self.enemies[:]:
            player_roll = random.randint(1, 6) + random.randint(1, 6)
            enemy_roll = random.randint(1, 6) + random.randint(1, 6)
            player_total = self.skill + player_roll
            enemy_total = enemy.skill + enemy_roll
            combat_log += f"Against {enemy.name}:\n"
            combat_log += f"  You rolled {player_roll} (Total: {player_total}), {enemy.name} rolled {enemy_roll} (Total: {enemy_total}).\n"
            if player_total > enemy_total:
                base_damage = 2
                damage = base_damage
                if self.luck_var.get() and self.luck > 0:
                    if self.test_luck():
                        damage = 4
                        combat_log += "  Luck successful: enemy takes 4 damage.\n"
                    else:
                        damage = 1
                        combat_log += "  Luck failed: enemy takes 1 damage.\n"
                else:
                    combat_log += f"  No luck used: enemy takes {damage} damage.\n"
                enemy.stamina -= damage
                if enemy.stamina <= 0:
                    combat_log += f"  {enemy.name} is defeated!\n"
                    self.enemies.remove(enemy)
                else:
                    combat_log += f"  {enemy.name} now has {enemy.stamina} HP remaining.\n"
            else:
                base_damage = 2
                damage = base_damage
                if self.luck_var.get() and self.luck > 0:
                    if self.test_luck():
                        damage = 1
                        combat_log += "  Luck successful: you take 1 damage.\n"
                    else:
                        damage = 3
                        combat_log += "  Luck failed: you take 3 damage.\n"
                else:
                    combat_log += f"  No luck used: you take {damage} damage.\n"
                self.stamina -= damage
                combat_log += f"  Your stamina is now {self.stamina}.\n"
                if self.stamina <= 0:
                    messagebox.showinfo("Battle", combat_log + "\nYou have been defeated.")
                    self.destroy()
                    return
            combat_log += "\n"
        self.update_attributes()
        self.update_battle_list()
        messagebox.showinfo("Combat Round", combat_log)

    def flee(self):
        if not self.enemies:
            messagebox.showinfo("Flee", "No enemy to flee from.")
            return
        base_damage = 2
        damage = base_damage
        flee_log = "You attempt to flee.\n"
        if self.luck_var.get() and self.luck > 0:
            if self.test_luck():
                damage = 1
                flee_log += "  Luck successful: you take 1 damage while fleeing.\n"
            else:
                damage = 3
                flee_log += "  Luck failed: you take 3 damage while fleeing.\n"
        else:
            flee_log += "  No luck used: you take 2 damage while fleeing.\n"
        self.stamina -= damage
        flee_log += f"  Your stamina is now {self.stamina}.\n"
        self.enemies.clear()
        self.update_battle_list()
        self.update_attributes()
        messagebox.showinfo("Flee", flee_log)

if __name__ == "__main__":
    FightingFantasyApp().mainloop()
