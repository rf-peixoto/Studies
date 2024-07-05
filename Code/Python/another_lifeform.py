import random
import numpy as np
import os
import time
import sys

# Configuration options
env_size = 32
initial_entities = 10
initial_resource_amount = 100  # Total number of initial resources to place
steps = 1000  # Total number of steps to run the simulation
base_entity_energy_gain = 2
resource_spawn_interval = 50  # Interval to spawn natural resources
random_death_chance = 0.01  # Chance for an entity to die randomly
carrying_capacity_factor = 1.5  # Max entities based on available resources
move_attempts_before_death = 2  # Number of failed move attempts before entity dies
mutation_chance = 0.05  # Chance for offspring to mutate
entity_char = 'E'
resource_char = 'R'
empty_char = '.'

# Customization options
min_age = 5
max_age = 30
min_energy_consumption = 1
max_energy_consumption = 5
max_reproductions = 3
reproduction_energy_cost = 5

# Define the Entity class
class Entity:
    def __init__(self, x, y, energy, age, reproduction_rate, max_age, energy_consumption_rate):
        self.x = x
        self.y = y
        self.energy = energy
        self.age = age
        self.reproduction_rate = reproduction_rate
        self.max_age = max_age
        self.energy_consumption_rate = energy_consumption_rate
        self.failed_move_attempts = 0
        self.reproduction_count = 0
        self.last_position = None
    
    def move(self, env_size, environment):
        directions = [(-1, 0), (1, 0), (0, -1), (0, 1)]
        random.shuffle(directions)
        move_success = False
        possible_moves = []

        for direction in directions:
            new_x = self.x + direction[0]
            new_y = self.y + direction[1]
            if 0 <= new_x < env_size and 0 <= new_y < env_size:
                if environment[new_x][new_y] > 0:  # Move towards resource
                    self.last_position = (self.x, self.y)
                    self.x = new_x
                    self.y = new_y
                    move_success = True
                    break
                elif environment[new_x][new_y] != -1 and (new_x, new_y) != self.last_position:
                    possible_moves.append((new_x, new_y))
        
        if not move_success and possible_moves:
            new_position = random.choice(possible_moves)
            self.last_position = (self.x, self.y)
            self.x = new_position[0]
            self.y = new_position[1]
            move_success = True
        
        if not move_success:
            for direction in directions:
                new_x = self.x + direction[0]
                new_y = self.y + direction[1]
                if 0 <= new_x < env_size and 0 <= new_y < env_size:
                    if environment[new_x][new_y] != -1:  # Move to an empty space
                        self.last_position = (self.x, self.y)
                        self.x = new_x
                        self.y = new_y
                        move_success = True
                        break
        
        if not move_success and self.last_position:
            new_x, new_y = self.last_position
            if environment[new_x][new_y] != -1:  # Move back to the last position if it's the only possible move
                self.x = new_x
                self.y = new_y
                move_success = True

        if not move_success:
            self.failed_move_attempts += 1
        else:
            self.failed_move_attempts = 0
    
    def consume_resource(self, environment):
        if environment[self.x][self.y] > 0:
            self.energy += self.energy_consumption_rate
            environment[self.x][self.y] -= 1
    
    def reproduce(self):
        if random.random() < self.reproduction_rate and self.reproduction_count < max_reproductions and self.energy >= reproduction_energy_cost:
            self.reproduction_count += 1
            self.energy -= reproduction_energy_cost
            energy_consumption_rate = self.energy_consumption_rate
            if random.random() < mutation_chance:
                energy_consumption_rate += random.choice([-1, 1])
            return Entity(self.x, self.y, 10, 0, self.reproduction_rate, random.randint(min_age, max_age), energy_consumption_rate)
    
    def age_increment(self):
        self.age += 1
        # Energy consumption increases with age
        if self.age % 5 == 0:
            self.energy_consumption_rate += 1
    
    def die(self):
        return (self.energy <= 0 or self.age > self.max_age or 
                random.random() < random_death_chance or self.failed_move_attempts >= move_attempts_before_death)

# Define the Environment class
class Environment:
    def __init__(self, size, initial_resource_amount):
        self.size = size
        self.resource_distribution = np.full((size, size), -1)
        self.entities = []
        self.place_initial_resources(initial_resource_amount)
    
    def place_initial_resources(self, amount):
        for _ in range(amount):
            x, y = random.randint(0, self.size - 1), random.randint(0, self.size - 1)
            self.resource_distribution[x][y] = 1
    
    def update_environment(self, step):
        new_entities = []
        carrying_capacity = np.sum(self.resource_distribution == 1) * carrying_capacity_factor
        
        for entity in self.entities:
            entity.move(self.size, self.resource_distribution)
            entity.consume_resource(self.resource_distribution)
            if len(new_entities) < carrying_capacity:
                offspring = entity.reproduce()
                if offspring:
                    new_entities.append(offspring)
            entity.age_increment()
            if not entity.die():
                new_entities.append(entity)
        
        self.entities = new_entities
        
        # Natural resource spawning
        if step % resource_spawn_interval == 0:
            self.resource_regeneration()

    def add_entity(self, entity):
        self.entities.append(entity)
    
    def resource_regeneration(self):
        for _ in range(int(self.size * self.size * 0.1)):  # Regenerate resources on 10% of the map
            x, y = random.randint(0, self.size - 1), random.randint(0, self.size - 1)
            self.resource_distribution[x][y] = 1

def clear_screen():
    os.system('cls' if os.name == 'nt' else 'clear')

# Simulation loop
def run_simulation():
    environment = Environment(env_size, initial_resource_amount)
    for _ in range(initial_entities):
        environment.add_entity(Entity(
            random.randint(0, env_size-1), random.randint(0, env_size-1), 
            10, 0, 0.1, random.randint(min_age, max_age), random.randint(min_energy_consumption, max_energy_consumption)
        ))

    for step in range(steps):  # 'step' is the current iteration of the simulation
        environment.update_environment(step)
        
        if not environment.entities:
            print(f"No more entities at step {step}. Simulation stopped.")
            break
        
        clear_screen()
        display = np.full((env_size, env_size), empty_char)
        for x in range(env_size):
            for y in range(env_size):
                if environment.resource_distribution[x][y] > 0:
                    display[x][y] = resource_char
        
        for entity in environment.entities:
            display[entity.x][entity.y] = entity_char
        
        print(f"Step: {step}, Entities: {len(environment.entities)}")
        for row in display:
            print(' '.join(row))
        
        time.sleep(0.1)

# Run the simulation
run_simulation()
