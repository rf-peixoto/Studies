def ripstr(string, part_size) -> list:
    return [string[i:i + part_size] for i in range(0, len(string), part_size)]
