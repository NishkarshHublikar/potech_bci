import os
import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
from sklearn.cluster import KMeans
from sklearn.preprocessing import StandardScaler

# Load preprocessed data
file_path = os.path.join('preprocessed', "s00_preprocessed.csv")

if os.path.exists(file_path):
    print(f"Loading {file_path}")
    
    # Read the preprocessed CSV file
    df = pd.read_csv(file_path)
    
    # Prepare data for clustering
    X = df[['FP1', 'FP2']].values
    
    # Standardize the data
    scaler = StandardScaler()
    X_scaled = scaler.fit_transform(X)
    
    # Apply K-means clustering
    n_clusters = 2  # You can adjust this number
    kmeans = KMeans(n_clusters=n_clusters, random_state=42)
    clusters = kmeans.fit_predict(X_scaled)
    
    # Add cluster labels to dataframe
    df['Cluster'] = clusters
    
    # Create visualizations
    plt.figure(figsize=(15, 10))
    
    # Plot 1: Scatter plot of FP1 vs FP2 with clusters
    plt.subplot(2, 3, 1)
    scatter = plt.scatter(df['FP1'], df['FP2'], c=df['Cluster'], cmap='viridis', alpha=0.6)
    plt.xlabel('FP1 Channel')
    plt.ylabel('FP2 Channel')
    plt.title('EEG Clusters (FP1 vs FP2)')
    plt.colorbar(scatter)
    
    # Plot 2: Time series of FP1 with cluster colors
    plt.subplot(2, 3, 2)
    for cluster in range(n_clusters):
        mask = df['Cluster'] == cluster
        plt.plot(df[mask].index, df[mask]['FP1'], alpha=0.7, label=f'Cluster {cluster}')
    plt.xlabel('Time Points')
    plt.ylabel('FP1 Amplitude')
    plt.title('FP1 Channel Time Series by Cluster')
    plt.legend()
    
    # Pl1t 3: Time series of FP2 with cluster colors
    plt.subplot(2, 3, 3)
    for cluster in range(n_clusters):
        mask = df['Cluster'] == cluster
        plt.plot(df[mask].index, df[mask]['FP2'], alpha=0.7, label=f'Cluster {cluster}')
    plt.xlabel('Time Points')
    plt.ylabel('FP2 Amplitude')
    plt.title('FP2 Channel Time Series by Cluster')
    plt.legend()
    
    # Plot 4: Cluster distribution
    plt.subplot(2, 3, 4)
    cluster_counts = df['Cluster'].value_counts().sort_index()
    plt.bar(cluster_counts.index, cluster_counts.values)
    plt.xlabel('Cluster')
    plt.ylabel('Number of Data Points')
    plt.title('Cluster Distribution')
    
    # Plot 5: Box plot of FP1 by cluster
    plt.subplot(2, 3, 5)
    df.boxplot(column='FP1', by='Cluster', ax=plt.gca())
    plt.title('FP1 Distribution by Cluster')
    plt.suptitle('')
    
    # Plot 6: Box plot of FP2 by cluster
    plt.subplot(2, 3, 6)
    df.boxplot(column='FP2', by='Cluster', ax=plt.gca())
    plt.title('FP2 Distribution by Cluster')
    plt.suptitle('')
    
    plt.tight_layout()
    plt.show()
    
    # Print cluster statistics
    print("\nCluster Statistics:")
    for cluster in range(n_clusters):
        cluster_data = df[df['Cluster'] == cluster]
        print(f"\nCluster {cluster}:")
        print(f"  Size: {len(cluster_data)} points")
        print(f"  FP1 - Mean: {cluster_data['FP1'].mean():.4f}, Std: {cluster_data['FP1'].std():.4f}")
        print(f"  FP2 - Mean: {cluster_data['FP2'].mean():.4f}, Std: {cluster_data['FP2'].std():.4f}")
    
    # Save clustered data
    output_path = os.path.join('preprocessed', 's00_clustered.csv')
    df.to_csv(output_path, index=False)
    print(f"\nClustered data saved to {output_path}")
    
else:
    print(f"File {file_path} not found. Please run preprocessing first.")
