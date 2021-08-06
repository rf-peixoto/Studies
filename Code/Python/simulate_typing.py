from time import sleep

def say(text: str, speed: float):
  for c in text:
    print(c, end="")
    sleep(speed)
