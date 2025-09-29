import os
import pandas as pd


# file_name = f"s{i:02d}.csv"

file_path = os.path.join('ser', 's00.csv')

if os.path.exists(file_path):
    print(f"Processing {file_path}")
    
    # Read the CSV file without headers
    df = pd.read_csv(file_path, header=None)
    
    # Keep only O1 and O2 columns by index (O1=index 14, O2=index 15)
    # Channel order: Fp1, Fp2, F3, F4, F7, F8, T3, T4, C3, C4, T5, T6, P3, P4, O1, O2, Fz, Cz, Pz
    columns_to_keep = [0, 1]  # O1 and O2 indices
    
    # Filter dataframe to keep only O1 and O2 columns
    df_filtered = df.iloc[:, columns_to_keep]
    
    # Add column names for clarity
    df_filtered.columns = ['FP1', 'FP2']
    
    # Save preprocessed data
    output_path = os.path.join('preprocessed', 's00_preprocessed.csv')
    os.makedirs('preprocessed', exist_ok=True)
    df_filtered.to_csv(output_path, index=False)
    
    print(f"Saved preprocessed data to {output_path}")
    print(f"Original shape: {df.shape}, Filtered shape: {df_filtered.shape}")
else:
    print(f"File {file_path} not found")

print("Preprocessing complete!")