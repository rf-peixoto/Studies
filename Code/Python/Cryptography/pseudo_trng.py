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
    """
    if x < 0 or a <= 0:
        raise ValueError("Invalid arguments in gammaincc_custom")
    gln = math.lgamma(a)
    if x < a + 1:
        ap = a
        sum_val = 1.0 / a
        delta = sum_val
        n = 1
        while abs(delta) > abs(sum_val)*eps and n < max_iter:
            ap += 1
            delta *= x / ap
            sum_val += delta
            n += 1
        p = sum_val * math.exp(-x + a*math.log(x) - gln)
        return 1 - p  # gammaincc = 1 - P(a,x)
    else:
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
        data_hash = hashlib.sha256(data).hexdigest()
        print(f"{YELLOW}Microphone data collected: {len(data)} bytes, hash: {data_hash}{RESET}")
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
    data_hash = hashlib.sha256(data).hexdigest()
    print(f"{YELLOW}Temperature data collected: {len(data)} bytes, hash: {data_hash}{RESET}")
    return data

def get_time_data():
    data = str(time.time_ns()).encode('utf-8')
    data_hash = hashlib.sha256(data).hexdigest()
    print(f"{YELLOW}Time data collected: {len(data)} bytes, hash: {data_hash}{RESET}")
    return data

def get_os_random_bytes(n):
    data = os.urandom(n)
    data_hash = hashlib.sha256(data).hexdigest()
    print(f"{YELLOW}OS randomness data collected: {len(data)} bytes, hash: {data_hash}{RESET}")
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
        frame_hash = hashlib.sha256(frame_bytes).hexdigest()
        print(f"{YELLOW}Webcam frame {i+1} collected: {len(frame_bytes)} bytes, hash: {frame_hash}{RESET}")
        data += frame_bytes
        time.sleep(delay)
    cap.release()
    total_hash = hashlib.sha256(data).hexdigest()
    print(f"{YELLOW}Total webcam data collected: {len(data)} bytes, hash: {total_hash}{RESET}")
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

# --- SP 800-22 Tests ---

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
    p_value = gammaincc_custom(N / 2, chi2 / 2)
    return p_value, (p_value >= 0.01)

# --- SP 800-90B–Inspired Tests ---

def repetition_count_test(bit_str):
    """
    Compute the longest run of identical bits.
    For demonstration, we set a fixed threshold (e.g. 5).
    In a full SP 800-90B analysis, this threshold would be based on statistical estimation.
    """
    max_run = 0
    current_run = 1
    for i in range(1, len(bit_str)):
        if bit_str[i] == bit_str[i-1]:
            current_run += 1
        else:
            if current_run > max_run:
                max_run = current_run
            current_run = 1
    max_run = max(max_run, current_run)
    threshold = 5  # Example threshold for demonstration
    passed = max_run <= threshold
    p_value = 1.0 if passed else 0.0  # Dummy p-value for demonstration
    return p_value, passed, max_run, threshold

def markov_test(bit_str):
    """
    Perform a simple Markov test by analyzing transitions between bits.
    Expected transitions (for an unbiased source) are roughly equal.
    A chi-square statistic is computed on the 2x2 contingency table.
    """
    count_00 = count_01 = count_10 = count_11 = 0
    for i in range(1, len(bit_str)):
        if bit_str[i-1] == '0' and bit_str[i] == '0':
            count_00 += 1
        elif bit_str[i-1] == '0' and bit_str[i] == '1':
            count_01 += 1
        elif bit_str[i-1] == '1' and bit_str[i] == '0':
            count_10 += 1
        elif bit_str[i-1] == '1' and bit_str[i] == '1':
            count_11 += 1
    total_0 = count_00 + count_01
    total_1 = count_10 + count_11
    chi_sq = 0.0
    if total_0 > 0:
        expected0 = total_0 / 2
        chi_sq += ((count_00 - expected0) ** 2 + (count_01 - expected0) ** 2) / expected0
    if total_1 > 0:
        expected1 = total_1 / 2
        chi_sq += ((count_10 - expected1) ** 2 + (count_11 - expected1) ** 2) / expected1
    # For two independent groups, df = 2.
    # A rough approximation for p-value for chi-square with 2 df:
    p_value = math.exp(-chi_sq/2) * (1 + chi_sq/2)
    passed = (p_value >= 0.01)
    return p_value, passed, (count_00, count_01, count_10, count_11)

def run_all_tests(key_bytes):
    bit_str = bytes_to_bitstring(key_bytes)
    results = {}
    # SP 800-22 Tests:
    p_val, res = frequency_monobit_test(bit_str)
    results["Frequency (Monobit) Test"] = (p_val, res)
    
    p_val, res = runs_test(bit_str)
    results["Runs Test"] = (p_val, res)
    
    p_val, res = cumulative_sums_test(bit_str)
    results["Cumulative Sums Test (Forward)"] = (p_val, res)
    
    p_val, res = block_frequency_test(bit_str, block_size=20)
    results["Block Frequency Test (m=20)"] = (p_val, res)
    
    # SP 800-90B–Inspired Tests:
    p_val, res, max_run, thresh = repetition_count_test(bit_str)
    results[f"Repetition Count Test (max run vs threshold={thresh})"] = (p_val, res, max_run)
    
    p_val, res, trans_counts = markov_test(bit_str)
    results["Markov Test"] = (p_val, res, trans_counts)
    
    return results

def main():
    parser = argparse.ArgumentParser(
        description="Generate a seed/secret key from physical entropy sources and test its randomness using tests from NIST SP 800-22 and SP 800-90B."
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
    
    print(f"\n{BLUE}Running randomness tests on the generated key:{RESET}")
    test_results = run_all_tests(key)
    for test_name, result in test_results.items():
        if "Repetition Count" in test_name:
            p_value, passed, max_run = result
            status = f"{GREEN}PASS{RESET}" if passed else f"{RED}FAIL{RESET}"
            print(f"{test_name}: p-value = {p_value:.6f} --> {status} (max run = {max_run})")
        elif "Markov Test" in test_name:
            p_value, passed, trans = result
            status = f"{GREEN}PASS{RESET}" if passed else f"{RED}FAIL{RESET}"
            print(f"{test_name}: p-value = {p_value:.6f} --> {status} (transitions: 00={trans[0]}, 01={trans[1]}, 10={trans[2]}, 11={trans[3]})")
        else:
            p_value, passed = result
            status = f"{GREEN}PASS{RESET}" if passed else f"{RED}FAIL{RESET}"
            print(f"{test_name}: p-value = {p_value:.6f} --> {status}")
    
    print(f"\n{YELLOW}Note: For rigorous statistical analysis, a much longer bit sequence is recommended.{RESET}")
    
if __name__ == "__main__":
    main()
