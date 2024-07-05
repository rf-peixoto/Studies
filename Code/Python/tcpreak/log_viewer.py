import json
import pandas as pd
import matplotlib.pyplot as plt
import seaborn as sns

def read_logs(filename):
    logs = []
    with open(filename, 'r') as log_file:
        for line in log_file:
            logs.append(json.loads(line))
    return logs

def generate_dataframe(logs):
    df = pd.DataFrame(logs)
    return df

def plot_status_distribution(ax, df, title):
    sns.countplot(x='status', data=df, ax=ax)
    ax.set_title(title)
    ax.set_xlabel('Status')
    ax.set_ylabel('Count')

def plot_errors(ax, df, title):
    error_df = df[df['status'] == 'error']
    if not error_df.empty:
        error_counts = error_df['error'].value_counts()
        sns.barplot(x=error_counts.index, y=error_counts.values, ax=ax)
        ax.set_title(title)
        ax.set_xlabel('Error')
        ax.set_ylabel('Count')
        ax.set_xticklabels(ax.get_xticklabels(), rotation=90)
    else:
        ax.set_title(title)
        ax.set_xlabel('Error')
        ax.set_ylabel('Count')
        ax.bar([], [])  # Display an empty plot

def plot_sent_data_size_distribution(ax, df, title):
    df['sent_data_size'] = df['sent_data'].apply(lambda x: len(x) // 2)  # Convert hex length to byte length
    sns.histplot(df['sent_data_size'], bins=30, kde=True, ax=ax)
    ax.set_title(title)
    ax.set_xlabel('Data Size (bytes)')
    ax.set_ylabel('Count')

def plot_combined_status_distribution(ax, client_df, server_df):
    combined_df = pd.concat([client_df.assign(source='Client'), server_df.assign(source='Server')])
    sns.countplot(x='status', hue='source', data=combined_df, ax=ax)
    ax.set_title('Combined Status Distribution')
    ax.set_xlabel('Status')
    ax.set_ylabel('Count')

def main():
    client_logs = read_logs('client_log.json')
    server_logs = read_logs('server_log.json')

    client_df = generate_dataframe(client_logs)
    server_df = generate_dataframe(server_logs)

    fig, axs = plt.subplots(3, 2, figsize=(18, 18))
    fig.suptitle('TCP Fuzzer Logs Analysis', fontsize=16)

    plot_status_distribution(axs[0, 0], client_df, 'Client Status Distribution')
    plot_status_distribution(axs[0, 1], server_df, 'Server Status Distribution')

    plot_errors(axs[1, 0], client_df, 'Client Error Types Distribution')
    plot_errors(axs[1, 1], server_df, 'Server Error Types Distribution')

    plot_sent_data_size_distribution(axs[2, 0], client_df, 'Client Sent Data Size Distribution')
    plot_combined_status_distribution(axs[2, 1], client_df, server_df)

    plt.tight_layout(rect=[0, 0.03, 1, 0.95])
    plt.show()

if __name__ == "__main__":
    main()
