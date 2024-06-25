def convert_to_seconds(time_str):
    h, m, s = map(int, time_str.split(':'))
    return h * 3600 + m * 60 + s

def convert_to_hms(seconds):
    h = seconds // 3600
    m = (seconds % 3600) // 60
    s = seconds % 60
    return f"{h:02}:{m:02}:{s:02}"

def calculate_time(video_length):
    speeds = [1, 1.25, 1.5, 0.5, 0.75]
    results = {}

    video_length_seconds = convert_to_seconds(video_length)
    
    for speed in speeds:
        adjusted_time = video_length_seconds / speed
        results[f"x{speed}"] = convert_to_hms(int(adjusted_time))
    
    return results

if __name__ == "__main__":
    video_length = input("Enter the video length (HH:MM:SS): ")
    results = calculate_time(video_length)
    
    for speed, time in results.items():
        print(f"At speed {speed}, the video will take: {time}")
