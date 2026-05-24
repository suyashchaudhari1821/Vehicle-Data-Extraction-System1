"""
Exporter module for writing data to Excel format.
Handles DataFrame creation and Excel export.
"""

import pandas as pd
from typing import List, Dict, Any
import os


EXPORT_COLUMNS = ["Brand", "Model", "Version", "Engine Code", "Engines"]


def export_to_excel(data: List[Dict[str, str]], output_file: str = "vehicle_data.xlsx") -> bool:
    """
    Export flattened data to Excel file.
    
    Args:
        data: List of dictionaries with Brand, Model, Version, Engine Code, Engines
        output_file: Output Excel filename (default: vehicle_data.xlsx)
        
    Returns:
        True if successful, False otherwise
    """
    if not data:
        print("No data to export")
        return False
    
    try:
        # Create DataFrame
        df = pd.DataFrame(data)
        
        # Ensure column order
        for column in EXPORT_COLUMNS:
            if column not in df.columns:
                df[column] = ""
        df = df[EXPORT_COLUMNS]
        
        # Create Excel with formatting
        output_path = os.path.abspath(output_file)
        
        with pd.ExcelWriter(output_path, engine="openpyxl") as writer:
            df.to_excel(writer, sheet_name="Vehicle Data", index=False)
            
            # Basic formatting
            worksheet = writer.sheets["Vehicle Data"]
            for idx, col in enumerate(EXPORT_COLUMNS, 1):
                worksheet.column_dimensions[chr(64 + idx)].width = 20
        
        print(f"Data exported to {output_path}")
        print(f"Total rows: {len(df)}")
        return True
    
    except Exception as e:
        print(f"Error exporting to Excel: {str(e)}")
        return False


def get_dataframe(data: List[Dict[str, str]]) -> pd.DataFrame:
    """
    Create DataFrame from data.
    
    Args:
        data: List of dictionaries with Brand, Model, Version, Engine Code, Engines
        
    Returns:
        Pandas DataFrame
    """
    if not data:
        return pd.DataFrame(columns=EXPORT_COLUMNS)
    
    df = pd.DataFrame(data)
    for column in EXPORT_COLUMNS:
        if column not in df.columns:
            df[column] = ""
    return df[EXPORT_COLUMNS]
