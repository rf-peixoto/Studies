#pip install python-vagrant

import vagrant

# Create a Vagrant instance
v = vagrant.Vagrant()

# Initialize a virtual machine
v.init('ubuntu/bionic64')

# Start the virtual machine
v.up()

# Run a command inside the virtual machine
result = v.ssh(command='python mycode.py')
print(result)

# Stop and destroy the virtual machine
v.destroy()
