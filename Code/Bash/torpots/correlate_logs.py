#!/usr/bin/env python3
import os
import re
from datetime import datetime, timedelta
import pandas as pd

# Configuration
LOG_DIRECTORY = "./logs/"  # Path to the centralized logs directory
OUTPUT_FILE = "correlated_connections.csv"
TIME_WINDOW = timedelta(seconds=30)  # Maximum allowed time difference for correlation

# Regular Expressions
# Example log entries with debug level:
# 2024-04-25 10:25:50.456 [debug] Stream 5678: Incoming connection from 203.0.113.5:54321 on circuit ABCD
# 2024-04-25 10:25:50.600 [debug] Stream 5678: Outgoing connection to 198.51.100.23:80 on circuit ABCD

stream_incoming_regex = re.compile(
    r'(?P<timestamp>\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}\.\d{3}) \[debug\] Stream (?P<stream_id>\d+): Incoming connection from (?P<src_ip>\d+\.\d+\.\d+\.\d+):(?P<src_port>\d+) on circuit (?P<circuit_id>\w+)'
)

stream_outgoing_regex = re.compile(
    r'(?P<timestamp>\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}\.\d{3}) \[debug\] Stream (?P<stream_id>\d+): Outgoing connection to (?P<dest_ip>\d+\.\d+\.\d+\.\d+):(?P<dest_port>\d+) on circuit (?P<circuit_id>\w+)'
)

circuit_build_regex = re.compile(
    r'(?P<timestamp>\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}\.\d{3}) \[debug\] New Circuit built: (?P<circuit_id>\w+)'
)

def parse_logs():
    """
    Parses all notices.log files and extracts incoming and outgoing connections.
    
    Returns:
        incoming_df (DataFrame): DataFrame containing incoming connections.
        outgoing_df (DataFrame): DataFrame containing outgoing connections.
    """
    incoming_connections = []
    outgoing_connections = []
    circuit_creations = []

    for root, dirs, files in os.walk(LOG_DIRECTORY):
        for file in files:
            if file.endswith("notices.log"):
                log_path = os.path.join(root, file)
                print(f"Parsing log file: {log_path}")
                with open(log_path, 'r') as f:
                    for line in f:
                        # Parse incoming connections
                        incoming_match = stream_incoming_regex.search(line)
                        if incoming_match:
                            incoming = incoming_match.groupdict()
                            incoming_connections.append({
                                'timestamp': datetime.strptime(incoming['timestamp'], "%Y-%m-%d %H:%M:%S.%f"),
                                'stream_id': incoming['stream_id'],
                                'src_ip': incoming['src_ip'],
                                'src_port': int(incoming['src_port']),
                                'circuit_id': incoming['circuit_id'],
                                'node': os.path.basename(root)  # e.g., node1
                            })
                            continue

                        # Parse outgoing connections
                        outgoing_match = stream_outgoing_regex.search(line)
                        if outgoing_match:
                            outgoing = outgoing_match.groupdict()
                            outgoing_connections.append({
                                'timestamp': datetime.strptime(outgoing['timestamp'], "%Y-%m-%d %H:%M:%S.%f"),
                                'stream_id': outgoing['stream_id'],
                                'dest_ip': outgoing['dest_ip'],
                                'dest_port': int(outgoing['dest_port']),
                                'circuit_id': outgoing['circuit_id'],
                                'node': os.path.basename(root)  # e.g., node1
                            })
                            continue

                        # Parse circuit creations (optional, for reference)
                        circuit_match = circuit_build_regex.search(line)
                        if circuit_match:
                            circuit = circuit_match.groupdict()
                            circuit_creations.append({
                                'timestamp': datetime.strptime(circuit['timestamp'], "%Y-%m-%d %H:%M:%S.%f"),
                                'circuit_id': circuit['circuit_id'],
                                'node': os.path.basename(root)  # e.g., node1
                            })
                            continue

    incoming_df = pd.DataFrame(incoming_connections)
    outgoing_df = pd.DataFrame(outgoing_connections)
    circuit_df = pd.DataFrame(circuit_creations)

    return incoming_df, outgoing_df, circuit_df

def correlate_connections(incoming_df, outgoing_df):
    """
    Correlates incoming and outgoing connections based on stream IDs and circuit IDs.
    
    Args:
        incoming_df (DataFrame): DataFrame containing incoming connections.
        outgoing_df (DataFrame): DataFrame containing outgoing connections.
    
    Returns:
        correlated_df (DataFrame): DataFrame containing correlated connections.
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
    print(f"Correlated connections saved to {OUTPUT_FILE}")

def main():
    print("Starting Tor Log Correlation...")
    incoming_df, outgoing_df, circuit_df = parse_logs()

    if incoming_df.empty:
        print("No incoming connections found in the logs.")
    if outgoing_df.empty:
        print("No outgoing connections found in the logs.")
    if incoming_df.empty or outgoing_df.empty:
        print("Insufficient data for correlation. Exiting.")
        return

    print("Correlating incoming and outgoing connections...")
    correlated_df = correlate_connections(incoming_df, outgoing_df)

    if correlated_df.empty:
        print("No correlated connections found within the specified time window.")
    else:
        print(f"Found {len(correlated_df)} correlated connections.")
        save_correlated_connections(correlated_df)

        # Optional: Display the first few correlated connections
        print("\nSample Correlated Connections:")
        print(correlated_df.head())

if __name__ == "__main__":
    main()
