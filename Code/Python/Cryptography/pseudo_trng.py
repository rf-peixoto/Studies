#!/usr/bin/env python3
import argparse
import hashlib
import time
import os
import psutil
import math

try:
    import sounddevice as sd
except ImportError:
    print("sounddevice module not found. Install it using: pip install sounddevice")
    exit(1)

try:
    import cv2
except ImportError:
    print("opencv-python module not found. Install it using: pip install opencv-python")
    exit(1)

# ANSI color codes for output.
GREEN = "\033[92m"
RED = "\033[91m"
BLUE = "\033[94m"
YELLOW = "\033[93m"
RESET = "\033[0m"

def gammaincc_custom(a, x, eps=1e-14, max_iter=1000):
    """
    Compute the complementary incomplete gamma function, gammaincc(a, x),
    using a series expansion (if x < a+1) or continued fraction (if x >= a+1).
    
    Returns:
      float: Approximate value of gammaincc(a, x)
    """
    if x < 0 or a <= 0:
        raise ValueError("Invalid arguments in gammaincc_custom")
    gln = math.lgamma(a)
    if x < a + 1:
        # Series representation for the lower incomplete gamma function P(a,x)
        ap = a
        sum_val = 1.0 / a
        delta = sum_val
        n = 1
        while abs(delta) > abs(sum_val)*eps and n < max_iter:
            ap += 1
            delta *= x / ap
            sum_val += delta
            n += 1
        # P(a,x) computed by the series
        p = sum_val * math.exp(-x + a*math.log(x) - gln)
        return 1 - p  # gammaincc = 1 - P(a,x)
    else:
        # Continued fraction representation for Q(a,x) = gammaincc(a,x)
        b = x + 1 - a
        c = 1e30
        d = 1.0 / b
        h = d
        for i in range(1, max_iter+1):
            an = -i * (i - a)
            b += 2
            d = an * d + b
            if abs(d) < 1e-30:
                d = 1e-30
            c = b + an / c
            if abs(c) < 1e-30:
                c = 1e-30
            d = 1.0 / d
            delta = d * c
            h *= delta
            if abs(delta - 1.0) < eps:
                break
        return math.exp(-x + a*math.log(x) - gln) * h

def capture_microphone(duration=3, sample_rate=44100):
    print(f"{BLUE}Recording microphone for {duration} seconds...{RESET}")
    try:
        recording = sd.rec(int(duration * sample_rate), samplerate=sample_rate, channels=1, dtype='int16')
        sd.wait()
        data = recording.tobytes()
        print(f"{YELLOW}Microphone data collected: {len(data)} bytes{RESET}")
        return data
    except Exception as e:
        print(f"{RED}Microphone capture failed: {e}{RESET}")
        return b""

def get_temperature_data():
    temp_data = ""
    if hasattr(psutil, "sensors_temperatures"):
        sensors = psutil.sensors_temperatures()
        for sensor_name, entries in sensors.items():
            for entry in entries:
                temp_data += f"{sensor_name}:{entry.current};"
    else:
        temp_data = "no_temp_sensor"
    data = temp_data.encode('utf-8')
    print(f"{YELLOW}Temperature data collected: {len(data)} bytes{RESET}")
    return data

def get_time_data():
    data = str(time.time_ns()).encode('utf-8')
    print(f"{YELLOW}Time data collected: {len(data)} bytes{RESET}")
    return data

def get_os_random_bytes(n):
    data = os.urandom(n)
    print(f"{YELLOW}OS randomness data collected: {len(data)} bytes{RESET}")
    return data

def capture_webcam(frames=1, delay=0.1):
    data = b""
    cap = cv2.VideoCapture(0)
    if not cap.isOpened():
        print(f"{RED}Webcam capture failed: Unable to open webcam{RESET}")
        return b""
    for i in range(frames):
        ret, frame = cap.read()
        if not ret:
            print(f"{RED}Webcam capture failed at frame {i}{RESET}")
            break
        frame_bytes = frame.tobytes()
        data += frame_bytes
        print(f"{YELLOW}Webcam frame {i+1} collected: {len(frame_bytes)} bytes{RESET}")
        time.sleep(delay)
    cap.release()
    print(f"{YELLOW}Total webcam data collected: {len(data)} bytes{RESET}")
    return data

def generate_entropy_key(size_bytes, mic_duration=3, sample_rate=44100, webcam_frames=1, webcam_delay=0.1):
    print(f"{BLUE}Collecting entropy from various sources...{RESET}")
    entropy_parts = {}
    
    mic_data = capture_microphone(mic_duration, sample_rate)
    entropy_parts["microphone"] = mic_data
    
    temp_data = get_temperature_data()
    entropy_parts["temperature"] = temp_data
    
    time_data = get_time_data()
    entropy_parts["time"] = time_data
    
    webcam_data = capture_webcam(webcam_frames, webcam_delay)
    entropy_parts["webcam"] = webcam_data
    
    os_random = get_os_random_bytes(32)
    entropy_parts["os_random"] = os_random
    
    # Combine all entropy sources.
    combined_entropy = b"".join(entropy_parts.values())
    print(f"{BLUE}Total combined entropy: {len(combined_entropy)} bytes{RESET}")
    
    # Process the collected entropy using SHA-512 in counter mode.
    hash_func = hashlib.sha512
    output = b""
    counter = 0
    current_data = combined_entropy
    while len(output) < size_bytes:
        counter_bytes = counter.to_bytes(4, 'big')
        current_data = hash_func(current_data + counter_bytes).digest()
        output += current_data
        counter += 1
    
    return output[:size_bytes], entropy_parts

def bytes_to_bitstring(data):
    return ''.join(f"{byte:08b}" for byte in data)

def frequency_monobit_test(bit_str):
    n = len(bit_str)
    s_n = sum(1 if bit == '1' else -1 for bit in bit_str)
    s_obs = abs(s_n) / math.sqrt(n)
    p_value = math.erfc(s_obs / math.sqrt(2))
    return p_value, (p_value >= 0.01)

def runs_test(bit_str):
    n = len(bit_str)
    ones = bit_str.count('1')
    pi = ones / n
    if abs(pi - 0.5) >= (2 / math.sqrt(n)):
        return 0.0, False
    v_n = 1 + sum(1 for i in range(1, n) if bit_str[i] != bit_str[i-1])
    numerator = abs(v_n - (2 * n * pi * (1 - pi)))
    denominator = 2 * math.sqrt(2 * n) * pi * (1 - pi)
    p_value = math.erfc(numerator / denominator)
    return p_value, (p_value >= 0.01)

def cumulative_sums_test(bit_str):
    n = len(bit_str)
    s = [1 if bit == '1' else -1 for bit in bit_str]
    cumulative = []
    cum = 0
    for bit in s:
        cum += bit
        cumulative.append(cum)
    z = max(abs(x) for x in cumulative)
    if z == 0:
        return 1.0, True
    sum_val = 0.0
    k_min = int(math.floor((-n / z + 1) / 4))
    k_max = int(math.floor((n / z - 1) / 4))
    for k in range(k_min, k_max + 1):
        term1 = math.erfc(((4 * k + 1) * z) / math.sqrt(2 * n))
        term2 = math.erfc(((4 * k - 1) * z) / math.sqrt(2 * n))
        sum_val += term1 - term2
    p_value = 1 - sum_val
    return p_value, (p_value >= 0.01)

def block_frequency_test(bit_str, block_size=20):
    n = len(bit_str)
    N = n // block_size
    if N == 0:
        return 0.0, False
    sum_chi = 0.0
    for i in range(N):
        block = bit_str[i*block_size:(i+1)*block_size]
        ones = block.count('1')
        pi = ones / block_size
        sum_chi += (pi - 0.5) ** 2
    chi2 = 4 * block_size * sum_chi
    # Use the custom gammaincc function to compute the p-value.
    p_value = gammaincc_custom(N / 2, chi2 / 2)
    return p_value, (p_value >= 0.01)

def run_nist_tests(key_bytes):
    bit_str = bytes_to_bitstring(key_bytes)
    results = {}
    
    p_val, res = frequency_monobit_test(bit_str)
    results["Frequency (Monobit) Test"] = (p_val, res)
    
    p_val, res = runs_test(bit_str)
    results["Runs Test"] = (p_val, res)
    
    p_val, res = cumulative_sums_test(bit_str)
    results["Cumulative Sums Test (Forward)"] = (p_val, res)
    
    p_val, res = block_frequency_test(bit_str, block_size=20)
    results["Block Frequency Test (m=20)"] = (p_val, res)
    
    return results

def main():
    parser = argparse.ArgumentParser(
        description="Generate a seed/secret key from physical entropy sources and test its randomness using NIST SP 800-22 tests."
    )
    parser.add_argument("--size", type=int, default=32,
                        help="Output key size in bytes (default: 32 bytes).")
    parser.add_argument("--mic_duration", type=float, default=3,
                        help="Duration for microphone recording in seconds (default: 3).")
    parser.add_argument("--sample_rate", type=int, default=44100,
                        help="Microphone sample rate in Hz (default: 44100).")
    parser.add_argument("--webcam_frames", type=int, default=1,
                        help="Number of webcam frames to capture (default: 1).")
    parser.add_argument("--webcam_delay", type=float, default=0.1,
                        help="Delay between webcam frames in seconds (default: 0.1).")
    args = parser.parse_args()

    key, entropy_parts = generate_entropy_key(args.size, args.mic_duration, args.sample_rate, args.webcam_frames, args.webcam_delay)
    print(f"\n{YELLOW}Generated key (hex): {key.hex()}{RESET}\n")
    
    print(f"{BLUE}Entropy sources details:{RESET}")
    for source, data in entropy_parts.items():
        print(f"  {source}: {len(data)} bytes")
    
    print(f"\n{BLUE}Running NIST SP 800-22 tests on the generated key:{RESET}")
    test_results = run_nist_tests(key)
    for test_name, (p_value, passed) in test_results.items():
        status = f"{GREEN}PASS{RESET}" if passed else f"{RED}FAIL{RESET}"
        print(f"{test_name}: p-value = {p_value:.6f} --> {status}")

    print(f"\n{YELLOW}Note: For rigorous statistical analysis, a much longer bit sequence is recommended.{RESET}")
    
if __name__ == "__main__":
    main()
