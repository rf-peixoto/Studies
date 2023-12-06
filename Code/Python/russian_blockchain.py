import hashlib
import time

def create_hash(index, timestamp, code, previous_hash):
    return hashlib.sha256(f'{index}{timestamp}{code}{previous_hash}'.encode()).hexdigest()

class Block:
    def __init__(self, index, code, previous_hash):
        self.index = index
        self.timestamp = time.time()
        self.code = code
        self.previous_hash = previous_hash
        self.hash = create_hash(index, self.timestamp, code, previous_hash)

    def run_code(self):
        exec(self.code)

class Blockchain:
    def __init__(self):
        self.chain = [self.create_genesis_block()]

    def create_genesis_block(self):
        return Block(0, "print('Hello, Blockchain!')", "0")

    def add_block(self, code):
        previous_block = self.chain[-1]
        new_block = Block(len(self.chain), code, previous_block.hash)
        new_block.run_code()
        self.chain.append(new_block)

# Example Usage
blockchain = Blockchain()
blockchain.add_block("print('Block 1 code')")
blockchain.add_block("print('Block 2 code')")
