# ref: https://stackoverflow.com/questions/11329917/restart-python-script-from-within-itself
os.execv(sys.argv[0], sys.argv)
