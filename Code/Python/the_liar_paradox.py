# v1:
def liar():
    print("I am lying now.")
    return not liar()   # says the opposite of what it actually returns

# Try to evaluate it
result = liar()
print("The statement is:", "true" if result else "false")

# v2:
def liar_paradox():
    # Let's pretend we can assign a truth value
    statement_is_true = True
    
    for _ in range(10):  # just to show it oscillates
        if statement_is_true:
            # If it's true → then it really is lying → so it must be false
            statement_is_true = False
            print("Assumed true → must be false")
        else:
            # If it's false → then it's not lying → so it must be true
            statement_is_true = True
            print("Assumed false → must be true")
    
    print("\nConclusion: it never stabilizes.")

liar_paradox()

# v3:
class LiarSentence:
    def __init__(self):
        self._is_true = None  # undecided at first

    @property
    def is_true(self):
        # The sentence says: "this sentence is false"
        # So its truth value = NOT its own truth value
        return not self.is_true   # ← self-reference creates the loop

    def __str__(self):
        try:
            return f"The sentence is {'true' if self.is_true else 'false'}"
        except RecursionError:
            return "The sentence causes infinite recursion — paradox!"


s = LiarSentence()
print(s)

# v4:
print("This statement is", "false" if "This statement is false" else "true")
#          ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
#                        self-reference via string content
