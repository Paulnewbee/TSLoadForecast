
import pandas as pd
from everything_data.config import ERCOT_LOAD_DATA_ADDRESS_LIST, ERCOT_PRICE_DATA_ADDRESS_LIST
import requests
import zipfile
import io
from typing import List
import re
from datetime import datetime, timedelta

def fix_ercot_time_format(df: pd.DataFrame, time_columns: list = None) -> pd.DataFrame:
    """Fix ERCOT time format where 24:00 should be 00:00 of next day."""
    df = df.copy()
    
    # If no time columns specified, try to find common time column names
    if time_columns is None:
        time_columns = []
        for col in df.columns:
            if any(keyword in col.lower() for keyword in ['time', 'date', 'datetime', 'hour', 'timestamp']):
                time_columns.append(col)
    
    for col in time_columns:
        if col in df.columns:
            # Convert to string first to handle any data type
            df[col] = df[col].astype(str)
            
            # Replace 24:00 with 00:00 of next day
            def fix_time_string(time_str):
                if pd.isna(time_str) or time_str == 'nan':
                    return time_str
                
                # Check if it contains 24:00
                if '24:00' in time_str:
                    # Replace 24:00 with 00:00
                    fixed_time = time_str.replace('24:00', '00:00')
                    
                    # Try to parse and add one day
                    try:
                        # Handle different date formats
                        for fmt in ['%m/%d/%Y %H:%M', '%Y-%m-%d %H:%M', '%m-%d-%Y %H:%M']:
                            try:
                                dt = datetime.strptime(fixed_time, fmt)
                                # Add one day
                                dt = dt + timedelta(days=1)
                                return dt.strftime(fmt)
                            except ValueError:
                                continue
                        
                        # If no format matches, just return the fixed time
                        return fixed_time
                    except:
                        return fixed_time
                
                return time_str
            
            df[col] = df[col].apply(fix_time_string)
            
            # Try to convert to datetime
            try:
                df[col] = pd.to_datetime(df[col], errors='coerce')
            except:
                pass
    
    return df

def download_and_extract_zip(url: str) -> pd.DataFrame:
    """Download a ZIP file and extract Excel data from it."""
    try:
        response = requests.get(url, timeout=30)
        response.raise_for_status()
        
        with zipfile.ZipFile(io.BytesIO(response.content)) as zip_file:
            # Find Excel files in the ZIP
            excel_files = [f for f in zip_file.namelist() if f.endswith(('.xlsx', '.xls'))]
            
            if not excel_files:
                print(f"No Excel files found in {url}")
                return pd.DataFrame()
            
            # Read the first Excel file found
            with zip_file.open(excel_files[0]) as excel_file:
                df = pd.read_excel(excel_file)
                # Fix ERCOT time format issues
                df = fix_ercot_time_format(df)
                return df
                
    except Exception as e:
        print(f"Error processing {url}: {str(e)}")
        return pd.DataFrame()

def download_and_extract_price_zip(url: str) -> pd.DataFrame:
    """Download a ZIP file and extract Excel data from all sheets, concatenating horizontally."""
    try:
        # Add headers to mimic a browser request
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
        }
        
        response = requests.get(url, headers=headers, timeout=60, allow_redirects=True)
        response.raise_for_status()
        
        with zipfile.ZipFile(io.BytesIO(response.content)) as zip_file:
            # Find Excel files in the ZIP
            excel_files = [f for f in zip_file.namelist() if f.endswith(('.xlsx', '.xls'))]
            
            if not excel_files:
                print(f"No Excel files found in {url}")
                return pd.DataFrame()
            
            # Process each Excel file and concatenate all sheets horizontally
            all_sheets_data = []
            
            for excel_file in excel_files:
                print(f"Processing Excel file: {excel_file}")
                with zip_file.open(excel_file) as file:
                    # Read all sheets from the Excel file
                    excel_data = pd.read_excel(file, sheet_name=None)  # None reads all sheets
                    
                    if isinstance(excel_data, dict):  # Multiple sheets
                        for sheet_name, sheet_df in excel_data.items():
                            if not sheet_df.empty:
                                all_sheets_data.append(sheet_df)
                                print(f"  - Sheet '{sheet_name}': {sheet_df.shape}")
                    else:  # Single sheet
                        if not excel_data.empty:
                            all_sheets_data.append(excel_data)
                            print(f"  - Single sheet: {excel_data.shape}")
            
            # Concatenate all sheets vertically (axis=0)
            if all_sheets_data:
                # Concatenate all dataframes vertically
                result_df = pd.concat(all_sheets_data, axis=0, ignore_index=True, sort=False)
                # Fix ERCOT time format issues
                result_df = fix_ercot_time_format(result_df)
                return result_df
            else:
                return pd.DataFrame()
                
    except Exception as e:
        print(f"Error processing {url}: {str(e)}")
        return pd.DataFrame()

def main():
    # Download and process load data (ZIP files)
    print("Downloading ERCOT load data...")
    load_dataframes = []
    for address in ERCOT_LOAD_DATA_ADDRESS_LIST:
        print(f"Processing: {address}")
        df = download_and_extract_zip(address)
        if not df.empty:
            load_dataframes.append(df)

    # Download and process price data (ZIP files with Excel sheets)
    print("Downloading ERCOT price data...")
    price_dataframes = []
    for address in ERCOT_PRICE_DATA_ADDRESS_LIST:
        print(f"Processing: {address}")
        df = download_and_extract_price_zip(address)
        if not df.empty:
            price_dataframes.append(df)

    # Combine all dataframes
    if load_dataframes:
        ercot_load_df = pd.concat(load_dataframes, ignore_index=True)
        print(f"Combined load data shape: {ercot_load_df.shape}")
    else:
        ercot_load_df = pd.DataFrame()
        print("No load data was successfully downloaded")

    if price_dataframes:
        ercot_price_df = pd.concat(price_dataframes, ignore_index=True)
        print(f"Combined price data shape: {ercot_price_df.shape}")
    else:
        ercot_price_df = pd.DataFrame()
        print("No price data was successfully downloaded")
        
    return ercot_load_df, ercot_price_df