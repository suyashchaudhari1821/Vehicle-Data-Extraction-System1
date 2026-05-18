"""
Database management for caching vehicle model data
Provides fast searching and tree structure generation
"""

import sqlite3
import json
from datetime import datetime
from pathlib import Path
import streamlit as st
from api_client import APIClient
import config
import parser

# Database file path
DB_PATH = Path(__file__).parent / "vehicle_data.db"


def init_database():
    """Initialize the database schema."""
    conn = sqlite3.connect(DB_PATH)
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
    conn.close()


def get_last_refresh_time():
    """Get the last time the database was refreshed."""
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT value FROM metadata WHERE key='last_refresh'")
    result = c.fetchone()
    conn.close()
    return result[0] if result else "Never"


def regenerate_database():
    """Regenerate the entire database from the API."""
    init_database()
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    
    # Clear existing data
    c.execute("DELETE FROM engines")
    c.execute("DELETE FROM versions")
    c.execute("DELETE FROM models")
    c.execute("DELETE FROM brands")
    
    progress_bar = st.progress(0)
    status_text = st.empty()
    
    try:
        with APIClient(config.get_cookies()) as client:
            brand_items = list(config.BRAND_CODES.items())
            engine_issue_count = 0
            
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
                    
                    # Insert models and their versions/engines
                    for model in models:
                        api_model_name = parser.get_model_name(model)
                        model_name = config.get_model_display_name(brand_code, api_model_name)
                        
                        c.execute(
                            "INSERT INTO models (brand_id, model_name, api_model_name) VALUES (?, ?, ?)",
                            (brand_id, model_name, api_model_name)
                        )
                        conn.commit()
                        
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
                                conn.commit()
                            except Exception as e:
                                engine_issue_count += 1
                                c.execute(
                                    "INSERT INTO engines (version_id, engine_name, engine_code, engine_status) VALUES (?, ?, ?, ?)",
                                    (version_id, 'N/A', '', f'FETCH_FAILED: {e}')
                                )
                                conn.commit()
                
                except Exception as e:
                    if '401' in str(e):
                        progress_bar.empty()
                        status_text.empty()
                        return False, "Cookies expired! Please update them in Settings."
                    pass
        
        # Update refresh time
        c.execute(
            "INSERT OR REPLACE INTO metadata (key, value) VALUES (?, ?)",
            ('last_refresh', str(datetime.now()))
        )
        conn.commit()
        
        progress_bar.empty()
        status_text.empty()
        conn.close()
        message = "Database regenerated successfully!"
        if engine_issue_count:
            message += f" {engine_issue_count} versions did not return a real engine; check the model tree/export status."
        return True, message
    
    except Exception as e:
        conn.close()
        return False, str(e)


def search_models(query):
    """Search for models by display, source, or version name."""
    if not DB_PATH.exists():
        return []
    
    conn = sqlite3.connect(DB_PATH)
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
    
    conn = sqlite3.connect(DB_PATH)
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
    
    conn = sqlite3.connect(DB_PATH)
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
    
    query += " ORDER BY b.brand_name, m.model_name, v.version_name, e.engine_name"
    
    c.execute(query, params)
    rows = c.fetchall()
    
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
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        c.execute("SELECT COUNT(*) FROM brands")
        count = c.fetchone()[0]
        conn.close()
        return count > 0
    except:
        return False
