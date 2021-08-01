function example {
  echo "This is a funcion in bash."
}

example

# With args:
function exampleb () {
  echo "This is the example $1"
}

exampleb $RANDOM
