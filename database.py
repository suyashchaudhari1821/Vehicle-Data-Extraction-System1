"""
Database management for caching vehicle model data
Provides fast searching and tree structure generation
"""

import os
import re
import sqlite3
import tempfile
from datetime import datetime
from pathlib import Path
import streamlit as st
from api_client import APIClient
import config
import parser

# Database file path
DB_PATH = Path(os.environ.get("VEHICLE_DB_PATH", Path(__file__).parent / "vehicle_data.db"))


def _connect(db_path=DB_PATH):
    db_path.parent.mkdir(parents=True, exist_ok=True)
    return sqlite3.connect(db_path)


def _version_sort_key(version_name):
    """Sort year/version labels newest first when a year is present."""
    text = str(version_name or "")
    year_match = re.search(r"\b(?:19|20)\d{2}\b", text)
    if year_match:
        return (0, -int(year_match.group(0)), text.lower())
    return (1, text.lower())


def _create_schema(conn):
    """Create or migrate the database schema on an open connection."""
    c = conn.cursor()

    # Create tables
    c.execute('''
        CREATE TABLE IF NOT EXISTS metadata (
            key TEXT PRIMARY KEY,
            value TEXT
        )
    ''')
    
    c.execute('''
        CREATE TABLE IF NOT EXISTS brands (
            brand_id INTEGER PRIMARY KEY,
            brand_name TEXT UNIQUE NOT NULL,
            brand_code TEXT
        )
    ''')
    
    c.execute('''
        CREATE TABLE IF NOT EXISTS models (
            model_id INTEGER PRIMARY KEY,
            brand_id INTEGER NOT NULL,
            model_name TEXT NOT NULL,
            api_model_name TEXT,
            FOREIGN KEY(brand_id) REFERENCES brands(brand_id)
        )
    ''')
    
    c.execute('''
        CREATE TABLE IF NOT EXISTS versions (
            version_id INTEGER PRIMARY KEY,
            model_id INTEGER NOT NULL,
            version_name TEXT NOT NULL,
            version_id_api TEXT,
            FOREIGN KEY(model_id) REFERENCES models(model_id)
        )
    ''')
    
    c.execute('''
        CREATE TABLE IF NOT EXISTS engines (
            engine_id INTEGER PRIMARY KEY,
            version_id INTEGER NOT NULL,
            engine_name TEXT NOT NULL,
            engine_code TEXT,
            engine_status TEXT DEFAULT 'OK',
            FOREIGN KEY(version_id) REFERENCES versions(version_id)
        )
    ''')

    c.execute("PRAGMA table_info(models)")
    model_columns = {row[1] for row in c.fetchall()}
    if "api_model_name" not in model_columns:
        c.execute("ALTER TABLE models ADD COLUMN api_model_name TEXT")

    c.execute("PRAGMA table_info(engines)")
    engine_columns = {row[1] for row in c.fetchall()}
    if "engine_code" not in engine_columns:
        c.execute("ALTER TABLE engines ADD COLUMN engine_code TEXT")
    if "engine_status" not in engine_columns:
        c.execute("ALTER TABLE engines ADD COLUMN engine_status TEXT DEFAULT 'OK'")
    
    conn.commit()


def init_database(db_path=DB_PATH):
    """Initialize the database schema."""
    conn = _connect(db_path)
    _create_schema(conn)
    conn.close()


def get_last_refresh_time():
    """Get the last time the database was refreshed."""
    conn = _connect()
    c = conn.cursor()
    c.execute("SELECT value FROM metadata WHERE key='last_refresh'")
    result = c.fetchone()
    conn.close()
    return result[0] if result else "Never"


def get_database_summary():
    """Return basic database details for diagnostics in the UI."""
    summary = {
        "path": str(DB_PATH),
        "exists": DB_PATH.exists(),
        "size_bytes": DB_PATH.stat().st_size if DB_PATH.exists() else 0,
        "last_refresh": "Never",
        "brands": 0,
        "models": 0,
        "versions": 0,
        "engines": 0,
    }

    if not DB_PATH.exists():
        return summary

    try:
        conn = _connect()
        _create_schema(conn)
        c = conn.cursor()
        c.execute("SELECT value FROM metadata WHERE key='last_refresh'")
        result = c.fetchone()
        summary["last_refresh"] = result[0] if result else "Never"

        for table in ("brands", "models", "versions", "engines"):
            c.execute(f"SELECT COUNT(*) FROM {table}")
            summary[table] = c.fetchone()[0]

        conn.close()
    except Exception:
        return summary

    return summary


def regenerate_database():
    """Regenerate the entire database from the API and atomically replace it."""
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    temp_file = tempfile.NamedTemporaryFile(
        prefix=f"{DB_PATH.stem}_",
        suffix=".tmp",
        dir=DB_PATH.parent,
        delete=False,
    )
    temp_path = Path(temp_file.name)
    temp_file.close()

    conn = _connect(temp_path)
    _create_schema(conn)
    c = conn.cursor()

    progress_bar = st.progress(0)
    status_text = st.empty()

    try:
        with APIClient(config.get_cookies()) as client:
            brand_items = list(config.BRAND_CODES.items())
            engine_issue_count = 0
            skipped_brands = []
            model_count = 0
            version_count = 0
            engine_count = 0

            for idx, (brand_name, brand_code) in enumerate(brand_items):
                try:
                    progress = (idx + 1) / len(brand_items)
                    progress_bar.progress(progress)
                    status_text.text(f"Processing: {idx + 1}/{len(brand_items)} brands...")
                    
                    # Insert brand
                    c.execute(
                        "INSERT OR IGNORE INTO brands (brand_name, brand_code) VALUES (?, ?)",
                        (brand_name, brand_code)
                    )
                    conn.commit()
                    
                    # Get brand_id
                    c.execute("SELECT brand_id FROM brands WHERE brand_name=?", (brand_name,))
                    brand_id = c.fetchone()[0]
                    
                    # Fetch models
                    response = client.get(
                        config.MODELS_ENDPOINT,
                        params=config.get_model_request_params(brand_code)
                    )
                    
                    models = parser.extract_models(response)
                    if not models:
                        skipped_brands.append(f"{brand_name}: no models returned")
                        continue
                    
                    # Insert models and their versions/engines
                    for model in models:
                        api_model_name = parser.get_model_name(model)
                        model_name = config.get_model_display_name(brand_code, api_model_name)
                        
                        c.execute(
                            "INSERT INTO models (brand_id, model_name, api_model_name) VALUES (?, ?, ?)",
                            (brand_id, model_name, api_model_name)
                        )
                        conn.commit()
                        model_count += 1
                        
                        c.execute("SELECT last_insert_rowid()")
                        model_id = c.fetchone()[0]
                        
                        versions = parser.extract_versions(model)
                        for version in versions:
                            version_id_api = parser.get_version_id(version)
                            api_version_name = parser.get_version_name(version)
                            version_name = config.get_version_display_name(
                                brand_code,
                                api_model_name,
                                api_version_name
                            )
                            
                            c.execute(
                                "INSERT INTO versions (model_id, version_name, version_id_api) VALUES (?, ?, ?)",
                                (model_id, version_name, version_id_api)
                            )
                            conn.commit()
                            version_count += 1
                            
                            c.execute("SELECT last_insert_rowid()")
                            version_id = c.fetchone()[0]
                            
                            # Get engines
                            try:
                                engine_response = client.get(
                                    config.ENGINES_ENDPOINT,
                                    params={"modelVersionId": version_id_api}
                                )
                                engine_items = parser.extract_engines(engine_response)
                                engine_status = 'OK' if engine_items else 'EMPTY_RESPONSE'
                                if not engine_items:
                                    engine_issue_count += 1
                                    engine_items = [{'name': 'N/A', 'code': ''}]

                                for engine_item in engine_items:
                                    c.execute(
                                        "INSERT INTO engines (version_id, engine_name, engine_code, engine_status) VALUES (?, ?, ?, ?)",
                                        (
                                            version_id,
                                            engine_item['name'],
                                            engine_item.get('code', ''),
                                            engine_status
                                        )
                                    )
                                    engine_count += 1
                                conn.commit()
                            except Exception as e:
                                engine_issue_count += 1
                                c.execute(
                                    "INSERT INTO engines (version_id, engine_name, engine_code, engine_status) VALUES (?, ?, ?, ?)",
                                    (version_id, 'N/A', '', f'FETCH_FAILED: {e}')
                                )
                                engine_count += 1
                                conn.commit()
                
                except Exception as e:
                    if '401' in str(e):
                        progress_bar.empty()
                        status_text.empty()
                        conn.close()
                        temp_path.unlink(missing_ok=True)
                        return False, "Cookies expired! Please update them in Settings."
                    skipped_brands.append(f"{brand_name}: {e}")

            if model_count == 0 or version_count == 0:
                progress_bar.empty()
                status_text.empty()
                conn.close()
                temp_path.unlink(missing_ok=True)
                reason = "; ".join(skipped_brands[:3]) if skipped_brands else "No data returned from API"
                return False, f"Database was not replaced because the API returned no usable model data. {reason}"

        # Update refresh time
        c.execute(
            "INSERT OR REPLACE INTO metadata (key, value) VALUES (?, ?)",
            ('last_refresh', str(datetime.now()))
        )
        c.execute(
            "INSERT OR REPLACE INTO metadata (key, value) VALUES (?, ?)",
            ('last_refresh_summary', f"{model_count} models, {version_count} versions, {engine_count} engines")
        )
        conn.commit()

        progress_bar.empty()
        status_text.empty()
        conn.close()

        os.replace(temp_path, DB_PATH)

        message = f"Database regenerated successfully: {model_count} models, {version_count} versions, {engine_count} engines."
        if engine_issue_count:
            message += f" {engine_issue_count} versions did not return a real engine; check the model tree/export status."
        if skipped_brands:
            message += f" Skipped {len(skipped_brands)} brand(s): {'; '.join(skipped_brands[:3])}"
        return True, message
    
    except Exception as e:
        progress_bar.empty()
        status_text.empty()
        try:
            conn.close()
        finally:
            temp_path.unlink(missing_ok=True)
        return False, str(e)


def search_models(query):
    """Search for models by display, source, or version name."""
    if not DB_PATH.exists():
        return []
    
    conn = _connect()
    c = conn.cursor()
    
    query_pattern = f"%{query}%"
    
    c.execute("""
        SELECT DISTINCT m.model_name
        FROM models m
        LEFT JOIN versions v ON v.model_id = m.model_id
        WHERE m.model_name LIKE ?
           OR COALESCE(m.api_model_name, '') LIKE ?
           OR COALESCE(v.version_name, '') LIKE ?
        ORDER BY m.model_name
        LIMIT 50
    """, (query_pattern, query_pattern, query_pattern))
    
    results = [row[0] for row in c.fetchall()]
    conn.close()
    return results


def search_models_and_engines(query):
    """Search for models and engines by name, returns dict with results."""
    if not DB_PATH.exists():
        return {'models': [], 'engines': []}
    
    conn = _connect()
    c = conn.cursor()
    
    query_pattern = f"%{query}%"
    
    # Search models and version-level names. A website "model" may be stored as
    # a version under a broader API model, e.g. C3 PICASSO under C3.
    c.execute("""
        SELECT DISTINCT
            CASE
                WHEN v.version_name LIKE ? AND v.version_name <> m.model_name THEN v.version_name
                ELSE m.model_name
            END AS label,
            m.model_name,
            CASE
                WHEN v.version_name LIKE ? AND v.version_name <> m.model_name THEN v.version_name
                ELSE NULL
            END AS version_name
        FROM models m
        LEFT JOIN versions v ON v.model_id = m.model_id
        WHERE m.model_name LIKE ?
           OR COALESCE(m.api_model_name, '') LIKE ?
           OR COALESCE(v.version_name, '') LIKE ?
        ORDER BY label
        LIMIT 50
    """, (query_pattern, query_pattern, query_pattern, query_pattern, query_pattern))
    
    models = [
        {'label': row[0], 'model': row[1], 'version': row[2]}
        for row in c.fetchall()
    ]
    
    # Search engines
    c.execute("""
        SELECT DISTINCT e.engine_name, COALESCE(e.engine_code, ''), m.model_name, b.brand_name
        FROM engines e
        JOIN versions v ON e.version_id = v.version_id
        JOIN models m ON v.model_id = m.model_id
        JOIN brands b ON m.brand_id = b.brand_id
        WHERE (e.engine_name LIKE ? OR COALESCE(e.engine_code, '') LIKE ?)
          AND COALESCE(e.engine_status, 'OK') = 'OK'
        ORDER BY COALESCE(e.engine_code, ''), e.engine_name
        LIMIT 50
    """, (query_pattern, query_pattern))
    
    engines = [
        {'engine': row[0], 'engine_code': row[1], 'model': row[2], 'brand': row[3]}
        for row in c.fetchall()
    ]
    
    conn.close()
    return {'models': models, 'engines': engines}


def get_tree_structure(brand_name=None, model_name=None, version_name=None):
    """Get tree structure of Brand → Model → Version → Engine."""
    if not DB_PATH.exists():
        return {}
    
    conn = _connect()
    c = conn.cursor()
    
    tree = {}
    
    # Build query
    query = """
        SELECT b.brand_name, m.model_name, COALESCE(v.version_name, 'Unknown'),
               COALESCE(e.engine_name, 'N/A'), COALESCE(e.engine_code, '')
        FROM brands b
        JOIN models m ON m.brand_id = b.brand_id
        LEFT JOIN versions v ON v.model_id = m.model_id
        LEFT JOIN engines e ON e.version_id = v.version_id
        WHERE 1=1
    """
    params = []
    
    if brand_name:
        query += " AND b.brand_name = ?"
        params.append(brand_name)
    
    if model_name:
        query += " AND m.model_name = ?"
        params.append(model_name)

    if version_name:
        query += " AND v.version_name = ?"
        params.append(version_name)
    
    query += " ORDER BY b.brand_name, m.model_name, e.engine_name"
    
    c.execute(query, params)
    rows = sorted(
        c.fetchall(),
        key=lambda row: (
            str(row[0]).lower(),
            str(row[1]).lower(),
            _version_sort_key(row[2]),
            str(row[3]).lower(),
        ),
    )
    
    # Build tree structure
    for brand, model, version, engine, engine_code in rows:
        engine_label = f"{engine_code} - {engine}" if engine_code else engine
        if brand not in tree:
            tree[brand] = {}
        if model not in tree[brand]:
            tree[brand][model] = {}
        if version not in tree[brand][model]:
            tree[brand][model][version] = []
        tree[brand][model][version].append(engine_label)
    
    conn.close()
    return tree


def is_database_exists():
    """Check if database exists and has data."""
    if not DB_PATH.exists():
        return False
    
    try:
        conn = _connect()
        c = conn.cursor()
        c.execute("SELECT COUNT(*) FROM brands")
        count = c.fetchone()[0]
        conn.close()
        return count > 0
    except:
        return False
