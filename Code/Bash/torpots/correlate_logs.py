#!/usr/bin/env python3
import os
import re
from datetime import datetime, timedelta
import pandas as pd
from multiprocessing import Pool, cpu_count
from functools import partial
from tqdm import tqdm

# Configuration
LOG_DIRECTORY = "../logs/"  # Path to the centralized logs directory (relative to scripts/)
OUTPUT_FILE = "../correlated_connections.csv"
TIME_WINDOW = timedelta(seconds=30)  # Maximum allowed time difference for correlation
NUM_WORKERS = cpu_count()  # Number of parallel workers

# Regular Expressions
stream_incoming_regex = re.compile(
    r'(?P<timestamp>\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}\.\d{3}) \[debug\] Stream (?P<stream_id>\d+): Incoming connection from (?P<src_ip>\d+\.\d+\.\d+\.\d+):(?P<src_port>\d+) on circuit (?P<circuit_id>\w+)'
)

stream_outgoing_regex = re.compile(
    r'(?P<timestamp>\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}\.\d{3}) \[debug\] Stream (?P<stream_id>\d+): Outgoing connection to (?P<dest_ip>\d+\.\d+\.\d+\.\d+):(?P<dest_port>\d+) on circuit (?P<circuit_id>\w+)'
)

circuit_build_regex = re.compile(
    r'(?P<timestamp>\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}\.\d{3}) \[debug\] New Circuit built: (?P<circuit_id>\w+)'
)

def parse_log_file(log_path):
    """
    Parses a single log file and extracts incoming and outgoing connections.
    
    Args:
        log_path (str): Path to the log file.
    
    Returns:
        tuple: (incoming_connections, outgoing_connections)
               Each is a list of dictionaries with parsed connection data.
    """
    incoming_connections = []
    outgoing_connections = []
    
    try:
        with open(log_path, 'r') as f:
            for line in f:
                # Parse incoming connections
                incoming_match = stream_incoming_regex.search(line)
                if incoming_match:
                    incoming = incoming_match.groupdict()
                    incoming_connections.append({
                        'timestamp_incoming': datetime.strptime(incoming['timestamp'], "%Y-%m-%d %H:%M:%S.%f"),
                        'stream_id': incoming['stream_id'],
                        'circuit_id': incoming['circuit_id'],
                        'src_ip': incoming['src_ip'],
                        'src_port': int(incoming['src_port']),
                        'node': os.path.basename(os.path.dirname(log_path))  # e.g., node1
                    })
                    continue

                # Parse outgoing connections
                outgoing_match = stream_outgoing_regex.search(line)
                if outgoing_match:
                    outgoing = outgoing_match.groupdict()
                    outgoing_connections.append({
                        'timestamp_outgoing': datetime.strptime(outgoing['timestamp'], "%Y-%m-%d %H:%M:%S.%f"),
                        'stream_id': outgoing['stream_id'],
                        'circuit_id': outgoing['circuit_id'],
                        'dest_ip': outgoing['dest_ip'],
                        'dest_port': int(outgoing['dest_port']),
                        'node': os.path.basename(os.path.dirname(log_path))  # e.g., node1
                    })
                    continue
    except Exception as e:
        print(f"Error parsing {log_path}: {e}")
    
    return incoming_connections, outgoing_connections

def aggregate_logs(log_files):
    """
    Aggregates incoming and outgoing connections from all log files using multiprocessing.
    
    Args:
        log_files (list): List of paths to log files.
    
    Returns:
        tuple: (all_incoming, all_outgoing)
               Each is a list of dictionaries with parsed connection data.
    """
    all_incoming = []
    all_outgoing = []
    
    with Pool(processes=NUM_WORKERS) as pool:
        results = list(tqdm(pool.imap(parse_log_file, log_files), total=len(log_files), desc="Parsing log files"))
    
    for incoming, outgoing in results:
        all_incoming.extend(incoming)
        all_outgoing.extend(outgoing)
    
    return all_incoming, all_outgoing

def correlate_connections(incoming_df, outgoing_df):
    """
    Correlates incoming and outgoing connections based on stream IDs and circuit IDs.
    
    Args:
        incoming_df (DataFrame): DataFrame containing incoming connections.
        outgoing_df (DataFrame): DataFrame containing outgoing connections.
    
    Returns:
        DataFrame: DataFrame containing correlated connections.
    """
    # Merge incoming and outgoing connections on stream_id and circuit_id
    merged_df = pd.merge(
        incoming_df,
        outgoing_df,
        on=['stream_id', 'circuit_id'],
        suffixes=('_incoming', '_outgoing'),
        how='inner',
        validate='one_to_one'  # Assuming one incoming per outgoing per stream
    )

    # Calculate time difference between incoming and outgoing connections
    merged_df['time_diff'] = merged_df['timestamp_outgoing'] - merged_df['timestamp_incoming']

    # Filter correlations within the specified time window
    merged_df = merged_df[
        (merged_df['time_diff'] >= timedelta(0)) &
        (merged_df['time_diff'] <= TIME_WINDOW)
    ]

    # Select and reorder relevant columns
    correlated_df = merged_df[[
        'stream_id',
        'circuit_id',
        'timestamp_incoming',
        'node_incoming',
        'src_ip',
        'src_port',
        'timestamp_outgoing',
        'node_outgoing',
        'dest_ip',
        'dest_port',
        'time_diff'
    ]]

    return correlated_df

def save_correlated_connections(correlated_df):
    """
    Saves the correlated connections to a CSV file.
    
    Args:
        correlated_df (DataFrame): DataFrame containing correlated connections.
    """
    correlated_df.to_csv(OUTPUT_FILE, index=False)
    print(f"\nCorrelated connections saved to {OUTPUT_FILE}")

def main():
    print("Starting Tor Log Correlation...")
    
    # Collect all notices.log files
    log_files = []
    for root, dirs, files in os.walk(LOG_DIRECTORY):
        for file in files:
            if file.endswith("notices.log"):
                log_path = os.path.join(root, file)
                log_files.append(log_path)
    
    if not log_files:
        print("No log files found. Please ensure that the log directory is correct.")
        return
    
    print(f"Found {len(log_files)} log files. Beginning parsing...")
    
    # Aggregate logs using multiprocessing
    all_incoming, all_outgoing = aggregate_logs(log_files)
    
    print(f"Parsed {len(all_incoming)} incoming connections and {len(all_outgoing)} outgoing connections.")
    
    if not all_incoming:
        print("No incoming connections found in the logs.")
    if not all_outgoing:
        print("No outgoing connections found in the logs.")
    if not all_incoming or not all_outgoing:
        print("Insufficient data for correlation. Exiting.")
        return
    
    # Convert lists to DataFrames
    incoming_df = pd.DataFrame(all_incoming)
    outgoing_df = pd.DataFrame(all_outgoing)
    
    # Correlate connections
    print("Correlating incoming and outgoing connections...")
    correlated_df = correlate_connections(incoming_df, outgoing_df)
    
    if correlated_df.empty:
        print("No correlated connections found within the specified time window.")
    else:
        print(f"Found {len(correlated_df)} correlated connections.")
        # Save to CSV
        save_correlated_connections(correlated_df)
        # Optionally, display a sample
        print("\nSample Correlated Connections:")
        print(correlated_df.head())

if __name__ == "__main__":
    main()
