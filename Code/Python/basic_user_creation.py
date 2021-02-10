# ================================================================== #
#  DEPENDENCIES
# ================================================================== #
import hashlib
import secrets
import string

# ================================================================== #
#  USER CLASS
# ================================================================== #
class User:

    def __init__(self, user: str, passwd: str, salt: str) -> str:
        """ Create an User Object """
        self.username = user
        self.passwd = passwd
        self.salt = salt

# ================================================================== #
#  MANAGER CLASS
# ================================================================== #
class Manager:

    def __init__(self):
        """ Initialize object and locals """
        self.users = []
        self.passwd_characteres_lower = string.ascii_lowercase
        self.passwd_characteres_upper = string.ascii_uppercase
        self.passwd_numbers = string.digits
        self.passwd_special = string.punctuation

    def input_username(self):
        """ Gets the Username """
        return input("Enter your user name: ")

    def input_passwd(self):
        """ Gets the Password """
        return input("Enter your user name: ")

    def check_username(self, new_username: str) -> str:
        """ Check if is a valid Username """
        for user in self.users:
            if user.username == new_username:
                print("This username already exists.")
                return False
        return True

    def check_passwd(self, passwd: str) -> str:
        """ Check if is a valid password """
        while True:
            # Check Size
            if len(passwd) < 14:
                print("This password is too short.")
                break            

            # Check Ascii Lowercase Letters
            counter = 0
            for i in passwd:
                if i in self.passwd_characteres_lower:
                    counter += 1
            if counter < 3:
                print("Your password need at last tree (3) lowercase characteres.")
                break

            # Check Ascii Uppercase Letters
            counter = 0
            for i in passwd:
                if i in self.passwd_characteres_upper:
                    counter += 1
            if counter < 3:
                print("Your password need at last tree (3) uppercase characteres.")
                break

            # Check Digits
            counter = 0
            for i in passwd:
                if i in self.passwd_numbers:
                    counter += 1
            if counter < 6:
                print("Your password need at last six (6) digits.")
                break

            # Check Special Characteres
            counter = 0
            for i in passwd:
                if i in self.passwd_special:
                    counter += 1
            if counter < 2:
                print("Your password need at last two (2) special characteres.")
                break

            # The password has passed!
            return True

    def protect_passwd(self, passwd: str) -> str:
        """ Encrypt the password before save it. """
        salt = secrets.token_urlsafe(32)
        encripted_passwd = hashlib.sha256((passwd + salt).encode()).hexdigest()
        return (encripted_passwd, salt)

    def create_new_user(self):
        """ Create a new user. """
        while True:
            user = input("Type your username: ")
            if self.check_username(user):
                break
        while True:
            passwd = input("Type your password: ")
            if self.check_passwd(passwd):
                pass_pack = self.protect_passwd(passwd)
                break

        # Well done! Let's put the values on the new User object:
        new_user = User(user, pass_pack[0], pass_pack[1])
        self.users.append(new_user)
        return True

# ================================================================== #
# We're done here. To load the user safely, simply add the 'salt'
# saved in the profile to the password entered at the time of login.
# ================================================================== #

# TESTING:
manager = Manager()
manager.create_new_user()

# Let's see:
print("\n")
print("User name: " + manager.users[0].username)
print("Saved password: " + manager.users[0].passwd)
print("This-user salt: " + manager.users[0].salt)
print("\n")
input("Press anything to quit.")
