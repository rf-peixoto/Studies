# Ref: https://www.youtube.com/watch?v=geCx-psFOcs

import time
import logging
import multiprocessing
from watchdog.observers import Observer
from watchdog.events import LoggingEventHandler

event_handler = LoggingEventHandler()
observer = Observer()

target_folder = "/home/$USER/Downloads"

def monitor_folder(path: str):
    logging.basicConfig(level=logging.INFO,
                        format='%(asctime)s - %(message)s',
                        datefmt='%y-%m-%d %H:%M:%S')
    observer.schedule(event_handler, path, recursive=True)
    observer.start()

    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        observer.stop()
    observer.join()

if __name__ == '__main__':
    m = multiprocessing.Process(target=monitor_folder, args=(target_folder,))
    m.start()
