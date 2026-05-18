# Vehicle Data Extraction System

A Streamlit-based web application for extracting and analyzing vehicle data from the FCA Services API. This tool allows users to extract brand-wise vehicle data, export to Excel, and perform comparative analysis.

## Features

- **Brand-wise Data Extraction**: Extract vehicle models and engine specifications for all vehicle brands
- **Multiple Export Formats**: Export data to Excel and CSV formats
- **Comparative Analysis**: Compare vehicle specifications across different brands
- **Beautiful Web UI**: User-friendly Streamlit interface for easy interaction
- **API Integration**: Seamless integration with FCA Services API

## Project Structure

```
vehicle-data-ex/
├── app.py                      # Main Streamlit application
├── api_client.py              # API client for FCA Services
├── config.py                  # Configuration and credentials
├── parser.py                  # Data parsing utilities
├── exporter.py                # Excel/CSV export functionality
├── compare_brands.py          # Brand comparison logic
├── extract_by_brand.py        # Brand-specific extraction
├── run_all_brands.py          # Batch extraction script
├── deep_inspect.py            # Deep inspection utilities
├── requirements.txt           # Python dependencies
└── vehicle_data*.xlsx         # Sample output files
```

## Prerequisites

- **Python 3.10 or higher**
- **pip** (Python package manager)
- **Git** (for cloning the repository)

## Installation & Setup

### Step 1: Clone the Repository

```bash
git clone https://github.com/suyashchaudhari1821/Vehicle-Data-Extraction-System.git
cd "vehicle-data-ex"
```

### Step 2: Create a Virtual Environment

#### On Windows (PowerShell):
```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
```

#### On Mac/Linux:
```bash
python3 -m venv .venv
source .venv/bin/activate
```

### Step 3: Install Dependencies

```bash
pip install -r requirements.txt
```

This will install all required packages including:
- **streamlit**: Web framework
- **pandas**: Data manipulation
- **requests**: HTTP client
- **openpyxl**: Excel file handling
- And all other dependencies

### Step 4: Configure API Credentials

The application uses API credentials stored in `config.py`. The credentials are already configured, but you can update them if needed by editing the file.

## Running the Application

### Option 1: Run Streamlit Web App (Recommended)

```bash
streamlit run app.py
```

This will:
- Launch a local web server on `http://localhost:8501`
- Open the application in your default browser
- Display a beautified UI for data extraction

## Persistent Database on Streamlit Cloud

Streamlit Cloud resets files written at runtime when the app restarts. To keep
the refreshed `vehicle_data.db` after restart, configure GitHub DB sync in
Streamlit Secrets:

```toml
GITHUB_DB_SYNC_ENABLED = "true"
GITHUB_TOKEN = "github_pat_your_token_here"
GITHUB_REPO = "suyashchaudhari1821/Vehicle-Data-Extraction-System1"
GITHUB_BRANCH = "main"
GITHUB_DB_PATH = "vehicle_data.db"
```

Use a GitHub fine-grained personal access token with **Contents: Read and
write** access to this repository. After this is configured, the app downloads
the latest database from GitHub on startup and uploads the database back to
GitHub after every successful **Build/Refresh Database**.

### Option 2: Run Batch Scripts

Extract data for all brands:
```bash
python run_all_brands.py
```

Extract quick sample:
```bash
python run_quick.py
```

Extract specific brand:
```bash
python extract_by_brand.py
```

## Usage Guide

### In the Web Application:

1. **Select a Brand**: Choose from the dropdown list of available vehicle brands
2. **Extract Data**: Click the "Extract" button to fetch vehicle data
3. **View Results**: Browse extracted models and specifications in the table
4. **Download Data**: Export results to Excel or CSV format
5. **Compare Brands**: Use the comparison tool to analyze data across brands

## API Integration Details

- **Base URL**: `https://library.fcaservices.com`
- **Authentication**: X-Auth-Token (already configured)
- **Endpoints**:
  - Models: `/connect/api/vehicle/models/categorized`
  - Engines: `/connect/api/vehicle/engines`

## Troubleshooting

### Issue: `ModuleNotFoundError: No module named 'streamlit'`
**Solution**: Ensure virtual environment is activated and dependencies are installed:
```bash
pip install -r requirements.txt
```

### Issue: API Connection Errors
**Solution**: 
- Check your internet connection
- Verify the API token in `config.py` is valid and not expired
- Check if the FCA Services API is accessible

### Issue: Excel Export Fails
**Solution**: 
- Ensure `openpyxl` is installed: `pip install openpyxl`
- Check if the output directory has write permissions

## Development

### Adding New Features:
1. Create feature branches for new functionality
2. Test thoroughly before committing
3. Update documentation as needed

### Code Structure:
- **api_client.py**: Handles all API communication
- **parser.py**: Processes raw API responses
- **exporter.py**: Handles file export operations
- **config.py**: Centralized configuration

## Contributing

1. Fork the repository
2. Create a feature branch (`git checkout -b feature/YourFeature`)
3. Make your changes
4. Commit your changes (`git commit -m 'Add YourFeature'`)
5. Push to the branch (`git push origin feature/YourFeature`)
6. Open a Pull Request

## Support

For issues or questions:
- Check existing issues on GitHub
- Create a new issue with detailed description
- Include error messages and steps to reproduce

## License

This project is proprietary and confidential.

## Author

Originally created for FCA vehicle data extraction and analysis.

---

**Last Updated**: May 5, 2026
