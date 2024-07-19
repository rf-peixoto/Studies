import pandas as pd
import matplotlib.pyplot as plt
import seaborn as sns

# Load the CSV file
csv_file_path = 'simulation_stats.csv'
df = pd.read_csv(csv_file_path)

# Data preparation
df['Likes'] = pd.to_numeric(df['Likes'], errors='coerce')
df['Shares'] = pd.to_numeric(df['Shares'], errors='coerce')
df['TTL'] = pd.to_numeric(df['TTL'], errors='coerce')

# Aggregating data by themes
theme_likes = df.groupby('Content')['Likes'].sum().reset_index()
theme_shares = df.groupby('Content')['Shares'].sum().reset_index()

# Function to plot top themes by likes
def plot_top_themes_by_likes(theme_likes, top_n=10):
    top_themes_likes = theme_likes.nlargest(top_n, 'Likes')
    plt.figure(figsize=(12, 8))
    sns.barplot(x='Likes', y='Content', data=top_themes_likes, palette='coolwarm')
    plt.title(f'Top {top_n} Themes by Likes')
    plt.xlabel('Total Likes')
    plt.ylabel('Theme')
    plt.show()

# Function to plot top themes by shares
def plot_top_themes_by_shares(theme_shares, top_n=10):
    top_themes_shares = theme_shares.nlargest(top_n, 'Shares')
    plt.figure(figsize=(12, 8))
    sns.barplot(x='Shares', y='Content', data=top_themes_shares, palette='viridis')
    plt.title(f'Top {top_n} Themes by Shares')
    plt.xlabel('Total Shares')
    plt.ylabel('Theme')
    plt.show()

# Function to plot least liked themes
def plot_least_liked_themes(theme_likes, bottom_n=10):
    least_liked_themes = theme_likes.nsmallest(bottom_n, 'Likes')
    plt.figure(figsize=(12, 8))
    sns.barplot(x='Likes', y='Content', data=least_liked_themes, palette='coolwarm')
    plt.title(f'Bottom {bottom_n} Themes by Likes')
    plt.xlabel('Total Likes')
    plt.ylabel('Theme')
    plt.show()

# Function to plot least shared themes
def plot_least_shared_themes(theme_shares, bottom_n=10):
    least_shared_themes = theme_shares.nsmallest(bottom_n, 'Shares')
    plt.figure(figsize=(12, 8))
    sns.barplot(x='Shares', y='Content', data=least_shared_themes, palette='viridis')
    plt.title(f'Bottom {bottom_n} Themes by Shares')
    plt.xlabel('Total Shares')
    plt.ylabel('Theme')
    plt.show()

# Plot the visualizations
plot_top_themes_by_likes(theme_likes)
#plot_top_themes_by_shares(theme_shares)
#plot_least_liked_themes(theme_likes)
#plot_least_shared_themes(theme_shares)
