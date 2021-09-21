#!/bin/bash
lynx --dump $1 | grep "http" | sed 's/......//' | egrep -v "bio.link"
