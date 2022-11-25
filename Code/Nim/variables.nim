# Ref: https://learnxinyminutes.com/docs/nim/

var number: int = 10
var txt: string = "Text"
var letter: char = 'y'
var switch: bool = false
var decimal: float = 1.0

# Use let to declare and bind variables *ONCE*:
let size: int = 320

# Constants are computed at compile time. This provides performance and is useful in compile time expressions.
const  debug: bool = true 

echo "X equals to: ", x
echo "This is a ", y

# Tuples:
var node: tuple[id: int, signature: string]
node = (id: 1, signature: "abc123")
node.id = 2

# Sequences: (lists?)
var stuff: seq[string]
stuff = @["1", "2", "3"]
stuff.add("4")

if "0" in stuff:
    switch = true
