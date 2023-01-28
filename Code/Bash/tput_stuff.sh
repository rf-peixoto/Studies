#!/bin/bash

# Check terminal window size:
tput lines
tput cols

# Move cursor to position:
tput cup [x] [y]
tput reset

# Underline
tput smul
echo Test
tput rmul

# Save cursor position:
tput sc
# Restore to saved position:
tput rc

# Sample:
tput reset

ctrl_c(){
  tput reset
  exit 130
}

trap ctrl_c SIGINT SIGTERM

# Vars:
set_vars(){
  RESETCOLOR=$(tput sgr0)
  GREEN=$(tput bold;tput setaf 6)
  RED=$(tput bold;tput setaf 1)
  BLUE=$(tput bold;tput setaf 4)
  COLS=20
}
set_vars

set_info(){
  tput cup 2 $COLS
  cat <<- Menu
      [*] INSERT DATA
Menu

tput cup 6 $COLS
echo -e "NAME: \c"

tput cup 7 $COLS
echo -e "LOGIN: \c"

tput cup 8 $COLS
echo -e "PASS: \c"
}
set_info

get_info(){
tput cup 6 $COLS
echo -e "$GREEN NAME: $RESETCOLOR\c"
read NAME

tput cup 7 $COLS
echo -e "$BLUE LOGIN: $RESETCOLOR\c"
read LOGIN

tput cup 8 $COLS
echo -e "$RED PASS: $RESETCOLOR\c"
read PASS
}

get_info
exit 0
