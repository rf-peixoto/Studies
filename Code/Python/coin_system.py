class CoinSystem:
    def __init__(self, copper=0, silver=0, gold=0):
        self.copper = copper
        self.silver = silver
        self.gold = gold
        self.update_coins()

    def update_coins(self):
        # Convert copper to silver if more than 99
        self.silver += self.copper // 100
        self.copper %= 100
        
        # Convert silver to gold if more than 99
        self.gold += self.silver // 100
        self.silver %= 100

    def add_coins(self, copper=0, silver=0, gold=0):
        self.copper += copper
        self.silver += silver
        self.gold += gold
        self.update_coins()

    def remove_coins(self, copper=0, silver=0, gold=0):
        total_copper = self.copper + self.silver * 100 + self.gold * 10000
        remove_copper = copper + silver * 100 + gold * 10000

        if remove_copper > total_copper:
            raise ValueError("Not enough coins to remove.")
        
        # Update the total copper and then redistribute to silver and gold
        total_copper -= remove_copper
        self.gold = total_copper // 10000
        self.silver = (total_copper % 10000) // 100
        self.copper = total_copper % 100

    def __str__(self):
        return f"Gold: {self.gold}, Silver: {self.silver}, Copper: {self.copper}"

# Example usage
wallet = CoinSystem(1234, 98, 5)
print(wallet)
wallet.add_coins(99)
print(wallet)
wallet.remove_coins(23, 1)
print(wallet)
