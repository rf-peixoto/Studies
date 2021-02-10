from os import system
from random import randint
# Get Percentage:
def percent(total, value):
    return round((value / total) * 100, 2)

# 7 is 16.6666% possible.

while True:
    # Number of games:
    counter = int(input("Play how much times? "))

    # Results:
    results = {'2':0, '3':0, '4':0, '5':0, '6':0,
               '7':0, '8':0, '9':0, '10':0, '11':0, '12':0}

    # Play:
    for num in range(counter):
        dice_a = randint(1, 6)
        dice_b = randint(1, 6)
        res = dice_a + dice_b
        results[str(res)] += 1

    for i in results.keys():
        print("{0}\t{1}\t{2}%".format(i,
                                       results[i],
                                       percent(counter, int(results[i]))))
    print("\n")


input()


