# Manager's Setup Guide

Quick setup instructions to run the Vehicle Data Extraction System locally.

## Single Command Setup (Easiest)

On Windows (PowerShell):
```powershell
# Activate virtual environment
.\.venv\Scripts\Activate.ps1

# Install dependencies
pip install -r requirements.txt

# Run the app
streamlit run app.py
```

On Mac/Linux:
```bash
# Activate virtual environment
source .venv/bin/activate

# Install dependencies
pip install -r requirements.txt

# Run the app
streamlit run app.py
```

## Step-by-Step Instructions

### 1. Clone the Repository
```bash
git clone https://github.com/suyashchaudhari1821/Vehicle-Data-Extraction-System.git
cd Vehicle\ Data\ Ex
```

### 2. Create Virtual Environment
**Windows:**
```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
```

**Mac/Linux:**
```bash
python3 -m venv .venv
source .venv/bin/activate
```

### 3. Install Requirements
```bash
pip install -r requirements.txt
```

### 4. Run the Application

**Streamlit App (Recommended):**
```bash
streamlit run app.py
```
→ Opens at `http://localhost:8501`

**Or run batch scripts:**
```bash
python run_all_brands.py      # Extract all brands
python run_quick.py           # Quick demo
python extract_by_brand.py    # Specific brand
```

## After First Run

The app will:
- ✅ Connect to the FCA Services API
- ✅ Extract vehicle data
- ✅ Display results in browser
- ✅ Allow data export to Excel

## System Requirements

- Python 3.10+
- 2GB RAM (minimum)
- Internet connection
- Latest pip

## Common Commands

```bash
# Deactivate virtual environment
deactivate

# Update dependencies
pip install -r requirements.txt --upgrade

# View installed packages
pip list

# Check Python version
python --version
```

## Need Help?

1. Check README.md for full documentation
2. Verify Python is installed: `python --version`
3. Ensure internet connection is active
4. Try deleting `.venv` and recreating it
5. Check the GitHub repository for issues

---

**Contact**: suyashchaudhari1821 (GitHub)
