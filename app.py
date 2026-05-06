
import streamlit as st
import pandas as pd
from api_client import APIClient
import config
import exporter
import re
from collections import defaultdict
import io
import database


# Page configuration
st.set_page_config(
    page_title="Vehicle Data Extractor",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Initialize database
database.init_database()

# Check if cookies are valid on page load
def check_cookies_valid():
    """Check if current cookies are valid."""
    try:
        with APIClient(config.get_cookies()) as client:
            response = client.get(
                config.MODELS_ENDPOINT,
                params={"brandCode": "JEEP"}
            )
            return response.get('categories') is not None
    except:
        return False

# Add settings in sidebar
with st.sidebar:
    st.markdown("### Settings")
    
    # Check cookie status
    cookies_valid = check_cookies_valid()
    if cookies_valid:
        st.success("Cookies are valid")
    else:
        st.error("Cookies may be expired! Click below to update.")
    
    with st.expander("Update Authentication", expanded=not cookies_valid):
        st.markdown("""
        **Update your API credentials here!**
        
        **How to get new credentials:**
        1. Go to https://library.fcaservices.com/web/secure/dashboard/user and log in
        2. Open DevTools (Press F12)
        3. Go to **Network** tab → reload → click any request
        4. Find **X-Auth-Token** in Request Headers → copy value
        5. Go to **Application** tab → **Cookies** → copy all cookies
        """)
        
        st.markdown("**Step 1: X-Auth-Token**")
        token_input = st.text_input(
            "Paste X-Auth-Token:",
            value="",
            type="password",
            placeholder="Paste the token from Network tab headers...",
            label_visibility="collapsed"
        )
        
        st.markdown("**Step 2: Cookies**")
        cookie_input = st.text_area(
            "Paste your cookies here:",
            value="",
            height=80,
            placeholder="Paste the entire cookie string from DevTools...",
            label_visibility="collapsed"
        )
        
        col1, col2 = st.columns(2)
        with col1:
            if st.button("Save Credentials", use_container_width=True):
                saved = False
                if token_input.strip():
                    config.set_auth_token(token_input.strip())
                    saved = True
                if cookie_input.strip():
                    config.set_cookies(cookie_input.strip())
                    saved = True
                
                if saved:
                    st.success("Credentials updated successfully!")
                    st.session_state.credentials_updated = True
                    st.cache_data.clear()
                else:
                    st.error("Please paste at least one credential")
        
        with col2:
            if st.button("Test Connection", use_container_width=True):
                with st.spinner("Testing..."):
                    try:
                        with APIClient(config.get_cookies()) as client:
                            response = client.get(
                                config.MODELS_ENDPOINT,
                                params={"brandCode": "JEEP"}
                            )
                            if response.get('categories'):
                                st.success("Connection successful! ✅")
                            else:
                                st.error("No data - credentials may be invalid")
                    except Exception as e:
                        st.error(f"Connection failed: {str(e)}")
    
    st.divider()
    
    # Database management
    st.markdown("### Model Database")
    
    db_exists = database.is_database_exists()
    if db_exists:
        last_refresh = database.get_last_refresh_time()
        st.info(f"Last updated: {last_refresh}")
    else:
        st.warning("Database is empty. Build it first!")
    
    if st.button("Build/Refresh Database", use_container_width=True, type="primary"):
        if not cookies_valid:
            st.error("Please update cookies first!")
        else:
            with st.spinner("Building database from API..."):
                success, message = database.regenerate_database()
                if success:
                    st.success(message)
                    st.rerun()
                else:
                    st.error(f"Failed: {message}")
    
    st.divider()

# Custom CSS
st.markdown("""
<style>
    .main {
        padding: 2rem;
    }
    .stButton>button {
        width: 100%;
        padding: 0.75rem;
        font-size: 1rem;
        font-weight: bold;
        border-radius: 0.5rem;
    }
    .brand-card {
        padding: 1.5rem;
        border-radius: 0.75rem;
        border: 2px solid #E0E0E0;
        cursor: pointer;
        transition: all 0.3s;
    }
    .brand-card:hover {
        border-color: #FF6B6B;
        box-shadow: 0 4px 8px rgba(0,0,0,0.1);
    }
    h1, h2, h3 {
        color: #1F77B4;
    }
</style>
""", unsafe_allow_html=True)

# Title and header
st.markdown("# Vehicle Data Extraction System")
st.markdown("Extract vehicle models, versions, and engines by brand")
st.divider()

# Initialize session state
if 'extraction_complete' not in st.session_state:
    st.session_state.extraction_complete = False
if 'extracted_data' not in st.session_state:
    st.session_state.extracted_data = None
if 'selected_brand' not in st.session_state:
    st.session_state.selected_brand = None
if 'cookies_updated' not in st.session_state:
    st.session_state.cookies_updated = False
if 'search_results' not in st.session_state:
    st.session_state.search_results = None


def render_tree(tree_data, max_depth=0, current_depth=0):
    """Render tree structure with indentation: Brand → Model → Version → Engine."""
    if current_depth == 0:
        st.markdown("### Model Tree Structure (Brand → Model → Year/Version → Engine)")
    
    for key, value in tree_data.items():
        if isinstance(value, dict):
            # Determine the label based on depth level
            if current_depth == 0:
                label = f"**{key}**"  # Brand level - bold
            elif current_depth == 1:
                label = f"**Model:** {key}"  # Model level
            elif current_depth == 2:
                label = f"**Year/Version:** {key}"  # Version/Year level
            else:
                label = key
            
            # Expandable section for dictionaries
            # Always expand the first 2 levels (brand and model), expand year level by default
            with st.expander(label, expanded=(current_depth < 3)):
                render_tree(value, max_depth, current_depth + 1)
        elif isinstance(value, list):
            # At depth 2, we have Version → Engines mapping
            if current_depth == 2:
                # Show version with engines inside expander
                version_label = f"**Year/Version:** {key}"
                with st.expander(version_label, expanded=True):
                    st.markdown("**Engines:**")
                    for engine in value:
                        st.markdown(f"  • {engine}")
            else:
                # Engine list - shown at depth 3 or beyond
                st.markdown("**Engines:**")
                for engine in value:
                    st.markdown(f"  • {engine}")
        else:
            st.markdown(f"  • {value}")


@st.cache_data(ttl=3600)
def get_all_brands():
    """Fetch all unique BRANDS from API using brandCode parameter.
    Results are cached for 1 hour."""
    try:
        with APIClient(config.get_cookies()) as client:
            brands_dict = {}
            
            progress = st.progress(0)
            status = st.empty()
            
            brand_items = list(config.BRAND_CODES.items())
            
            # Try each brand code
            for idx, (brand_name, brand_code) in enumerate(brand_items):
                try:
                    # Show progress
                    progress.progress((idx + 1) / len(brand_items))
                    status.text(f"Loading brands... {idx + 1}/{len(brand_items)}")
                    
                    # Fetch models for this specific brand using brandCode parameter
                    response = client.get(
                        config.MODELS_ENDPOINT,
                        params={"brandCode": brand_code}
                    )
                    
                    categories = response.get('categories', [])
                    models_count = sum(len(cat.get('models', [])) for cat in categories)
                    
                    if models_count > 0:
                        brands_dict[brand_name] = models_count
                
                except Exception as e:
                    # Brand not found - skip
                    if '401' in str(e):
                        progress.empty()
                        status.empty()
                        st.error("Cookies expired! Please update them in Settings → Update Cookies")
                        return []
                    pass
            
            progress.empty()
            status.empty()
            
            # Sort by count
            sorted_brands = sorted(brands_dict.items(), key=lambda x: x[1], reverse=True)
            return sorted_brands
    except Exception as e:
        if '401' in str(e):
            st.error("Cookies expired! Please update them in Settings - Update Cookies")
        else:
            st.error(f"Error fetching brands: {str(e)}")
        return []



def extract_brand_data(brand_name):
    """Extract data for specific brand using brandCode parameter."""
    try:
        with APIClient(config.get_cookies()) as client:
            # Get brand code for API call
            brand_code = config.BRAND_CODES.get(brand_name, brand_name)
            
            # Fetch models for this brand
            print(f"Fetching {brand_name} (code: {brand_code})...")
            response = client.get(
                config.MODELS_ENDPOINT,
                params={"brandCode": brand_code}
            )
            
            # Get all models from response
            categories = response.get('categories', [])
            models = []
            for category in categories:
                models.extend(category.get('models', []))
            
            if not models:
                return None, f"No models found for {brand_name}"
            
            # Extract data with engines
            flattened_data = []
            progress_bar = st.progress(0)
            status_text = st.empty()
            
            for idx, model in enumerate(models):
                progress = (idx + 1) / len(models)
                progress_bar.progress(progress)
                status_text.text(f"Processing: {idx + 1}/{len(models)} models...")
                
                model_name = model.get('modelName', '')
                versions = model.get('modelVersions', [])
                
                # Process each version
                for version in versions:
                    version_id = version.get('modelVersionId', '')
                    version_name = version.get('versionName', 'Unknown')
                    
                    # Get engines for this version
                    try:
                        engine_response = client.get(
                            config.ENGINES_ENDPOINT,
                            params={"modelVersionId": version_id}
                        )
                        engines = engine_response.get('engines', [])
                        engine_list = [e.get('engine', '') for e in engines if e.get('engine')]
                    except:
                        engine_list = []
                    
                    if not engine_list:
                        engine_list = ['N/A']
                    
                    # Create a separate row for each engine (vertical stacking)
                    for engine in engine_list:
                        flattened_data.append({
                            'Brand': brand_name,
                            'Model': model_name,
                            'Version': version_name,
                            'Engines': engine
                        })
            
            progress_bar.empty()
            status_text.empty()
            
            return pd.DataFrame(flattened_data), None
    
    except Exception as e:
        return None, str(e)


# Main UI - Search Vehicle
st.markdown("### Search Vehicle")

if not database.is_database_exists():
    st.warning("Database not built yet. Click 'Build/Refresh Database' in Settings (left sidebar)")
else:
    # Search input - auto-detects model or engine
    search_query = st.text_input(
        "Search for a model or engine:",
        placeholder="e.g., Cherokee, V6, Diesel...",
        key="search_input"
    )
    
    if search_query:
        # Get suggestions for both models and engines
        results = database.search_models_and_engines(search_query)
        
        # Determine which type has more results and prioritize display
        model_count = len(results['models'])
        engine_count = len(results['engines'])
        
        # Display results in order of relevance
        if model_count > 0 or engine_count > 0:
            # Show models first if they match better, engines otherwise
            if model_count >= engine_count:
                # Display model results first
                if results['models']:
                    st.markdown(f"**Models ({model_count}):**")
                    for model in results['models']:
                        if st.button(f"{model}", key=f"model_{model}", use_container_width=True):
                            tree_data = database.get_tree_structure(model_name=model)
                            if tree_data:
                                st.divider()
                                render_tree(tree_data)
                                st.session_state.search_results = tree_data
                            else:
                                st.info("No data found for this model")
                
                # Then display engine results
                if results['engines']:
                    st.markdown(f"**Engines ({engine_count}):**")
                    for eng_result in results['engines']:
                        engine = eng_result['engine']
                        model = eng_result['model']
                        brand = eng_result['brand']
                        if st.button(f"{engine} ({brand} {model})", key=f"engine_{engine}_{model}_{brand}", use_container_width=True):
                            tree_data = database.get_tree_structure(model_name=model)
                            if tree_data:
                                st.divider()
                                render_tree(tree_data)
                                st.session_state.search_results = tree_data
                            else:
                                st.info("No data found for this engine")
            else:
                # Display engine results first (more relevant)
                if results['engines']:
                    st.markdown(f"**Engines ({engine_count}):**")
                    for eng_result in results['engines']:
                        engine = eng_result['engine']
                        model = eng_result['model']
                        brand = eng_result['brand']
                        if st.button(f"{engine} ({brand} {model})", key=f"engine_{engine}_{model}_{brand}", use_container_width=True):
                            tree_data = database.get_tree_structure(model_name=model)
                            if tree_data:
                                st.divider()
                                render_tree(tree_data)
                                st.session_state.search_results = tree_data
                            else:
                                st.info("No data found for this engine")
                
                # Then display model results
                if results['models']:
                    st.markdown(f"**Models ({model_count}):**")
                    for model in results['models']:
                        if st.button(f"{model}", key=f"model_{model}", use_container_width=True):
                            tree_data = database.get_tree_structure(model_name=model)
                            if tree_data:
                                st.divider()
                                render_tree(tree_data)
                                st.session_state.search_results = tree_data
                            else:
                                st.info("No data found for this model")
        else:
            st.info(f"No models or engines found matching '{search_query}'")

st.divider()

# Main UI - Browse & Extract
# Browse Section
col1, col2 = st.columns([2, 1])

with col1:
    st.markdown("### Available Brands")

with col2:
    if st.button("Refresh Brands", use_container_width=True):
        st.rerun()

# Fetch and display brands
brands = get_all_brands()

if not brands:
    st.error("Unable to fetch brands. Check your cookies and API configuration.")
else:
    # Display brands in grid
    cols = st.columns(3)
    for idx, (brand, count) in enumerate(brands[:15]):
        col = cols[idx % 3]
        with col:
            if st.button(f"**{brand}**\n({count} models)", use_container_width=True):
                st.session_state.selected_brand = brand
                st.rerun()

st.divider()

# Extraction section for selected brand
if st.session_state.selected_brand:
    st.markdown(f"### Extracting: **{st.session_state.selected_brand}**")
    
    col1, col2 = st.columns(2)
    
    with col1:
        if st.button("Extract Data", use_container_width=True, type="primary"):
            with st.spinner(f"Extracting {st.session_state.selected_brand} data..."):
                df, error = extract_brand_data(st.session_state.selected_brand)
                
                if error:
                    st.error(f"{error}")
                else:
                    st.session_state.extracted_data = df
                    st.session_state.extraction_complete = True
                    st.success(f"Successfully extracted {len(df)} rows!")

    with col2:
        if st.button("Clear Selection", use_container_width=True):
            st.session_state.selected_brand = None
            st.session_state.extracted_data = None
            st.session_state.extraction_complete = False
            st.rerun()

# Extract & Download Section
st.divider()
st.markdown("### Extract & Download Data")

if st.session_state.extraction_complete and st.session_state.extracted_data is not None:
    df = st.session_state.extracted_data
    
    col1, col2, col3, col4 = st.columns(4)
    with col1:
        st.metric("Total Rows", len(df))
    with col2:
        st.metric("Unique Models", df['Model'].nunique())
    with col3:
        st.metric("Unique Versions", df['Version'].nunique())
    with col4:
        st.metric("Unique Engines", df['Engines'].nunique())
    
    st.divider()
    
    # Data table
    st.markdown("### Data Preview")
    st.dataframe(df, use_container_width=True, height=400)
   
    # Download section
    st.markdown("#### Download Options")
    col1, col2 = st.columns(2)
    
    with col1:
        # Excel download
        output = io.BytesIO()
        with pd.ExcelWriter(output, engine='openpyxl') as writer:
            df.to_excel(writer, sheet_name='Vehicle Data', index=False)
        excel_data = output.getvalue()
        
        st.download_button(
            label="Download Excel",
            data=excel_data,
            file_name=f"vehicle_data_{st.session_state.selected_brand.lower()}.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            use_container_width=True
        )
    
    with col2:
        # CSV download
        csv_data = df.to_csv(index=False)
        st.download_button(
            label="Download CSV",
            data=csv_data,
            file_name=f"vehicle_data_{st.session_state.selected_brand.lower()}.csv",
            mime="text/csv",
            use_container_width=True
        )
    
    # Statistics
    st.markdown("#### Statistics")
    
    col1, col2 = st.columns(2)
    
    with col1:
        st.markdown("#### Versions per Model")
        version_stats = df.groupby('Model')['Version'].nunique().sort_values(ascending=False).head(10)
        st.bar_chart(version_stats)
    
    with col2:
        st.markdown("#### Engines Distribution")
        engine_counts = df['Engines'].value_counts().head(10)
        st.bar_chart(engine_counts)
else:
    st.info("Extract data from a brand above to see results here.")

st.divider()

st.markdown("""
---
Vehicle Data Extraction System | FCA Services Library API
Built with Streamlit
""")
