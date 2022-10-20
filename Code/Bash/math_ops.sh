#!/bin/sh
a=100
b=50

val='expr $a + $b' #Line 1
echo "a + b : $val" #Line 2

val='expr $a - $b' #Line 4
echo "a - b : $val" #Line 5

val='expr $a \* $b' #Line 7
echo "a * b : $val" #Line 8

val='expr $a / $b' #Line 10
echo "b / a : $val" #Line 11
