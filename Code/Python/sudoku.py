import random
import os
from colorama import Fore, Style, init

# Initialize colorama
init(autoreset=True)

# Clear the terminal screen
def clear_screen():
    os.system('cls' if os.name == 'nt' else 'clear')

# Sudoku puzzle generator
def generate_sudoku(board):
    base  = 3
    side  = base*base

    # Pattern for a baseline valid solution
    def pattern(r, c): return (base*(r%base)+r//base+c)%side

    # Randomize rows, columns, and numbers (but keep them within valid constraints)
    def shuffle(s): return random.sample(s, len(s)) 

    r_base = range(base) 
    rows  = [g*base + r for g in shuffle(r_base) for r in shuffle(r_base)] 
    cols  = [g*base + c for g in shuffle(r_base) for c in shuffle(r_base)]
    nums  = shuffle(range(1, base*base+1))

    # Create the board
    board = [[nums[pattern(r, c)] for c in cols] for r in rows]

    # Remove some numbers to create the puzzle (difficulty can be adjusted by changing n)
    squares = side*side
    n = random.randint(40, 55)  # Number of empty spaces
    for p in random.sample(range(squares), n):
        board[p//side][p%side] = 0

    return board

# Display the Sudoku board with color, rows, and column letters
def display_board(board, original_board):
    # Column indicators (A-I)
    print("    " + " ".join([Fore.CYAN + chr(65 + i) + Style.RESET_ALL for i in range(9)]))
    
    for i in range(9):
        if i % 3 == 0 and i != 0:
            print(Fore.CYAN + "   " + "- " * 11 + Style.RESET_ALL)
        
        # Row indicator (1-9)
        row_str = Fore.CYAN + f"{i + 1}  " + Style.RESET_ALL
        for j in range(9):
            if j % 3 == 0 and j != 0:
                row_str += Fore.CYAN + "| " + Style.RESET_ALL
            if board[i][j] == 0:
                row_str += Fore.YELLOW + ". " + Style.RESET_ALL
            elif original_board[i][j] != 0:
                row_str += Fore.GREEN + f"{board[i][j]} " + Style.RESET_ALL
            else:
                row_str += f"{board[i][j]} "
        print(row_str)

# Check if a move is valid
def valid_move(board, row, col, num):
    # Check row
    if num in board[row]:
        return False
    # Check column
    for i in range(9):
        if board[i][col] == num:
            return False
    # Check 3x3 box
    box_x = col // 3
    box_y = row // 3
    for i in range(box_y * 3, box_y * 3 + 3):
        for j in range(box_x * 3, box_x * 3 + 3):
            if board[i][j] == num:
                return False
    return True

# Check if the board is completely filled
def is_complete(board):
    for row in board:
        if 0 in row:
            return False
    return True

# Sudoku game logic with continuous board updates
def play_sudoku():
    # Generate a new board
    original_board = generate_sudoku([[0]*9 for _ in range(9)])
    board = [row[:] for row in original_board]  # Copy of the board to track user input
    
    print(Fore.MAGENTA + "Welcome to Sudoku!" + Style.RESET_ALL)
    print(Fore.MAGENTA + "Enter moves as 'row_letter,number' (e.g., A5,7)." + Style.RESET_ALL)
    print(Fore.MAGENTA + "Type 'q' to quit." + Style.RESET_ALL)

    while not is_complete(board):
        clear_screen()
        display_board(board, original_board)

        user_input = input(Fore.CYAN + "Enter your move (e.g., A5,7) or 'q' to quit: " + Style.RESET_ALL).strip().lower()
        if user_input == 'q':
            print(Fore.RED + "Exiting the game. Thanks for playing!" + Style.RESET_ALL)
            break

        try:
            pos, num = user_input.split(",")
            col = ord(pos[0]) - ord('a')  # Convert column letter to index
            row = int(pos[1]) - 1  # Adjust for zero-based index
            num = int(num)
        except (ValueError, IndexError):
            print(Fore.RED + "Invalid input. Please use the format 'A5,7'." + Style.RESET_ALL)
            continue

        if row not in range(9) or col not in range(9) or num not in range(1, 10):
            print(Fore.RED + "Row, column, and number must be within valid range." + Style.RESET_ALL)
            continue

        if original_board[row][col] != 0:
            print(Fore.RED + "Cannot change an original number." + Style.RESET_ALL)
            continue

        if valid_move(board, row, col, num):
            board[row][col] = num
        else:
            print(Fore.RED + "Invalid move. Try again." + Style.RESET_ALL)

    if is_complete(board):
        clear_screen()
        display_board(board, original_board)
        print(Fore.GREEN + "Congratulations! You've completed the Sudoku puzzle!" + Style.RESET_ALL)

if __name__ == "__main__":
    play_sudoku()
