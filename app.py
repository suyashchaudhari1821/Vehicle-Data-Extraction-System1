
import streamlit as st
import pandas as pd
from api_client import APIClient
import config
import exporter
import re
import hmac
from collections import defaultdict
import io
import os
from pathlib import Path
import database
import db_sync
import parser
import torque_verifier


EXPORT_COLUMNS = ['Brand', 'Model', 'Version', 'Engine Code', 'Engines']
EXTRACTION_STATE_VERSION = "engine-code-column-v1"


# Page configuration
st.set_page_config(
    page_title="Vehicle Data Extractor",
    layout="wide",
    initial_sidebar_state="expanded"
)

def get_login_secret(name):
    """Read login credentials from Streamlit secrets or environment variables."""
    try:
        return st.secrets[name]
    except Exception:
        return os.environ.get(name, "")


def require_login():
    """Stop the app until the user has signed in."""
    if st.session_state.get("authenticated"):
        with st.sidebar:
            st.caption(f"Signed in as {st.session_state.get('username', '')}")
            if st.button("Logout", use_container_width=True):
                st.session_state.authenticated = False
                st.session_state.username = ""
                st.rerun()
        return

    expected_username = get_login_secret("APP_USERNAME")
    expected_password = get_login_secret("APP_PASSWORD")

    st.title("Vehicle Data Extractor")
    st.subheader("Login")

    if not expected_username or not expected_password:
        st.error("Login credentials are not configured.")
        st.info("Add APP_USERNAME and APP_PASSWORD in Streamlit Secrets.")
        st.stop()

    with st.form("login_form"):
        username = st.text_input("Email")
        password = st.text_input("Password", type="password")
        submitted = st.form_submit_button("Login", use_container_width=True)

    if submitted:
        username_ok = hmac.compare_digest(username.strip(), expected_username)
        password_ok = hmac.compare_digest(password, expected_password)
        if username_ok and password_ok:
            st.session_state.authenticated = True
            st.session_state.username = username.strip()
            st.rerun()
        else:
            st.error("Invalid email or password.")

    st.stop()


require_login()

# Pull the latest persisted DB before initializing the schema. This keeps
# Streamlit restarts from falling back to the old bundled SQLite file.
if not st.session_state.get("db_sync_startup_checked"):
    sync_result = db_sync.download_database_if_newer(database.DB_PATH)
    st.session_state.db_sync_startup_checked = True
    st.session_state.db_sync_status = sync_result.message
    if sync_result.changed:
        st.cache_data.clear()

# Initialize database
database.init_database()

# Check if cookies are valid on page load
def check_cookies_valid():
    """Check if current cookies are valid."""
    try:
        with APIClient(config.get_cookies()) as client:
            response = client.get(
                config.MODELS_ENDPOINT,
                params=config.get_model_request_params("JEEP")
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
                                params=config.get_model_request_params("JEEP")
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
        db_summary = database.get_database_summary()
        st.info(f"Last updated: {db_summary['last_refresh']}")
        st.caption(
            f"Loaded {db_summary['models']} models, "
            f"{db_summary['versions']} versions, "
            f"{db_summary['engines']} engines"
        )
        if db_sync.is_configured():
            st.caption(f"GitHub DB sync: {st.session_state.get('db_sync_status', 'enabled')}")
        else:
            st.caption("GitHub DB sync is not configured; restart will use the deployed DB file.")
        db_file = Path(db_summary["path"])
        if db_file.exists():
            st.download_button(
                "Download Current Database",
                data=db_file.read_bytes(),
                file_name="vehicle_data.db",
                mime="application/vnd.sqlite3",
                use_container_width=True,
                help="Optional backup copy of the SQLite database currently loaded by the app.",
            )
            if db_sync.is_configured():
                if st.button(
                    "Save Current Database to GitHub",
                    use_container_width=True,
                    help="Replace the GitHub-stored SQLite database with the current loaded database.",
                ):
                    sync_result = db_sync.upload_database(database.DB_PATH)
                    st.session_state.db_sync_status = sync_result.message
                    if sync_result.ok:
                        st.success(sync_result.message)
                    else:
                        st.warning(sync_result.message)
    else:
        st.warning("Database is empty. Build it first!")
    
    if st.button("Build/Refresh Database", use_container_width=True, type="primary"):
        if not cookies_valid:
            st.error("Please update cookies first!")
        else:
            with st.spinner("Building database from API..."):
                success, message = database.regenerate_database()
                if success:
                    sync_result = db_sync.upload_database(database.DB_PATH)
                    st.session_state.db_sync_status = sync_result.message
                    st.success(message)
                    if sync_result.ok:
                        st.success(sync_result.message)
                    else:
                        st.warning(sync_result.message)
                    st.cache_data.clear()
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
if st.session_state.get('extraction_state_version') != EXTRACTION_STATE_VERSION:
    st.session_state.extracted_data = None
    st.session_state.extraction_complete = False
    st.session_state.extraction_state_version = EXTRACTION_STATE_VERSION
if (
    st.session_state.extracted_data is not None
    and list(st.session_state.extracted_data.columns) != EXPORT_COLUMNS
):
    st.session_state.extracted_data = None
    st.session_state.extraction_complete = False
    st.session_state.extraction_state_version = EXTRACTION_STATE_VERSION


def get_model_result_parts(model_result):
    """Support both legacy string results and richer search result dictionaries."""
    if isinstance(model_result, dict):
        return (
            model_result.get('label') or model_result.get('model') or '',
            model_result.get('model') or model_result.get('label') or '',
            model_result.get('version')
        )
    return model_result, model_result, None


def format_engine_result(engine_result):
    """Return a readable engine label with the sales code when available."""
    engine = engine_result['engine']
    engine_code = engine_result.get('engine_code')
    if engine_code:
        return f"{engine_code} - {engine}"
    return engine


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
                        params=config.get_model_request_params(brand_code)
                    )
                    
                    models_count = len(parser.extract_models(response))
                    
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
                params=config.get_model_request_params(brand_code)
            )
            
            # Get all models from response. Some brands use a different nesting shape.
            models = parser.extract_models(response)
            
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
                
                api_model_name = parser.get_model_name(model)
                model_name = config.get_model_display_name(brand_code, api_model_name)
                versions = parser.extract_versions(model)
                
                # Process each version
                for version in versions:
                    version_id = parser.get_version_id(version)
                    api_version_name = parser.get_version_name(version)
                    version_name = config.get_version_display_name(
                        brand_code,
                        api_model_name,
                        api_version_name
                    )
                    
                    # Get engines for this version
                    try:
                        engine_response = client.get(
                            config.ENGINES_ENDPOINT,
                            params={"modelVersionId": version_id}
                        )
                        engine_list = parser.extract_engines(engine_response)
                    except Exception:
                        engine_list = []
                    
                    if not engine_list:
                        engine_list = [{'name': 'N/A', 'code': ''}]
                    
                    # Create a separate row for each engine (vertical stacking)
                    for engine in engine_list:
                        flattened_data.append({
                            'Brand': brand_name,
                            'Model': model_name,
                            'Version': version_name,
                            'Engine Code': engine.get('code', ''),
                            'Engines': engine.get('name', 'N/A')
                        })
            
            progress_bar.empty()
            status_text.empty()
            
            return pd.DataFrame(flattened_data, columns=EXPORT_COLUMNS), None
    
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
                    for model_result in results['models']:
                        model_label, model_name, version_name = get_model_result_parts(model_result)
                        if st.button(f"{model_label}", key=f"model_{model_label}_{model_name}_{version_name}", use_container_width=True):
                            tree_data = database.get_tree_structure(model_name=model_name, version_name=version_name)
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
                        engine = format_engine_result(eng_result)
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
                        engine = format_engine_result(eng_result)
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
                    for model_result in results['models']:
                        model_label, model_name, version_name = get_model_result_parts(model_result)
                        if st.button(f"{model_label}", key=f"model_{model_label}_{model_name}_{version_name}", use_container_width=True):
                            tree_data = database.get_tree_structure(model_name=model_name, version_name=version_name)
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
        st.cache_data.clear()
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

st.markdown("### Torque Verification Search")

with st.form("torque_verification_form"):
    col1, col2, col3 = st.columns(3)
    with col1:
        torque_year = st.number_input(
            "Model year",
            min_value=1900,
            max_value=2100,
            value=2026,
            step=1,
            key="torque_verify_year"
        )
    with col2:
        torque_vehicle_family = st.text_input(
            "VEH FAM",
            placeholder="e.g., JL, WL, DJ, LB, DT",
            key="torque_verify_vehicle_family"
        )
    with col3:
        torque_engine_code = st.text_input(
            "Engine code",
            placeholder="e.g., ERC, EJN, EZH",
            key="torque_verify_engine_code"
        )

    torque_vsc_name = st.text_input(
        "VSC name",
        placeholder="e.g., Brakes, Suspension / Control Arms & Track Bar",
        key="torque_verify_vsc_name"
    )
    torque_description = st.text_input(
        "Description",
        placeholder="e.g., Master Cylinder Nuts",
        key="torque_verify_description"
    )
    torque_target = st.text_input(
        "Target torque specification",
        placeholder="e.g., 18 N·m, 0030, 25 N·m",
        key="torque_verify_target"
    )

    torque_submitted = st.form_submit_button("Verify torque", use_container_width=True)

if torque_submitted:
    missing_fields = []
    if not torque_vehicle_family.strip():
        missing_fields.append("VEH FAM")
    if not torque_target.strip():
        missing_fields.append("Target torque specification")

    if missing_fields:
        st.error(f"Enter: {', '.join(missing_fields)}")
    else:
        with st.spinner("Checking Service Library torque specifications..."):
            try:
                verification = torque_verifier.verify_torque(
                    int(torque_year),
                    torque_vehicle_family,
                    torque_engine_code,
                    torque_vsc_name,
                    torque_description,
                    torque_target,
                )
            except Exception as exc:
                st.error(f"Torque verification failed: {exc}")
                verification = None

        if verification:
            st.markdown("#### Verification Result")
            st.metric("Status", verification.get("status", "Unknown"), f"{verification.get('confidence', 0)}% confidence")
            result_rows = [
                {"Field": "Vehicle", "Match": "Yes" if verification["vehicle_match"] else "No"},
                {
                    "Field": "Engine code",
                    "Match": (
                        "Yes"
                        if verification["engine_match"]
                        else "Searched all engines"
                        if not verification.get("engine_code_provided")
                        else "No"
                    ),
                },
                {
                    "Field": "VSC name",
                    "Match": "Yes" if verification["vsc_match"] else "Not provided/weak match",
                },
                {
                    "Field": "Description",
                    "Match": (
                        "Yes"
                        if verification["description_match"]
                        else "Not provided/weak match"
                        if not torque_description.strip()
                        else "No"
                    ),
                },
                {"Field": "Torque", "Match": "Yes" if verification["torque_match"] else "No"},
            ]
            st.dataframe(pd.DataFrame(result_rows), use_container_width=True, hide_index=True)

            if verification.get("vehicle"):
                vehicle = verification["vehicle"]
                st.markdown(
                    f"**Vehicle:** {vehicle['brand']} {vehicle['model']} "
                    f"({vehicle['version']} {vehicle['model_code']})"
                )
            if verification.get("engine"):
                engine = verification["engine"]
                st.markdown(f"**Engine:** {engine['engine_code']} - {engine['engine']}")
            if verification.get("engines_checked"):
                st.caption(f"Engines checked: {verification['engines_checked']}")

            best = verification.get("best")
            if best:
                st.markdown("#### Best Match")
                st.markdown(f"**Page:** {best['page']}")
                st.markdown(f"**Found description:** {best['description']}")
                st.markdown(f"**Found specification:** {best['specification']}")
                st.markdown(f"**Similarity:** {best['confidence']}%")
                if best.get("comment"):
                    st.markdown(f"**Comment:** {best['comment']}")

                candidates = verification.get("candidates", [])
                if candidates:
                    st.markdown("#### Best Matches")
                    candidate_rows = []
                    for candidate in candidates:
                        candidate_engine = candidate.get("engine", {})
                        candidate_vehicle = candidate.get("vehicle", {})
                        candidate_rows.append(
                            {
                                "Similarity": f"{candidate['confidence']}%",
                                "Description Similarity": f"{round(candidate['description_score'] * 100, 1)}%",
                                "Torque Similarity": f"{round(candidate['torque_score'] * 100, 1)}%",
                                "Torque Match": "Yes" if candidate["torque_match"] else "No",
                                "Actual Description": candidate["description"],
                                "Actual Torque": candidate["specification"],
                                "Comment": candidate.get("comment", ""),
                                "Engine Code": candidate_engine.get("engine_code", ""),
                                "Engine": candidate_engine.get("engine", ""),
                                "Vehicle": (
                                    f"{candidate_vehicle.get('brand', '')} "
                                    f"{candidate_vehicle.get('model', '')} "
                                    f"{candidate_vehicle.get('version', '')}"
                                ).strip(),
                                "Page": candidate["page"],
                            }
                        )
                    st.dataframe(pd.DataFrame(candidate_rows), use_container_width=True, hide_index=True)
            else:
                st.info(verification.get("message", "No matching torque rows found."))

            if verification.get("torque_pages_found") is not None:
                st.caption(
                    f"Checked {verification['torque_pages_checked']} of "
                    f"{verification['torque_pages_found']} torque pages."
                )
            if verification.get("skipped_content_pages"):
                st.warning(
                    f"Skipped {verification['skipped_content_pages']} torque page(s) because "
                    "Service Library rejected their raw content request."
                )
                content_errors = verification.get("content_errors", [])
                if content_errors:
                    with st.expander("Skipped torque page details"):
                        st.dataframe(pd.DataFrame(content_errors), use_container_width=True, hide_index=True)

st.divider()

st.markdown("""
---
Vehicle Data Extraction System | FCA Services Library API
Built with Streamlit
""")
