import sqlite3
import os
import json
import datetime
import threading
import re

DB_PATH = os.path.abspath("./asmr_studio.db")
BACKUP_ROOT = os.path.abspath("./projects")
MASTER_GLOSSARY_PATH = os.path.abspath("./master_glossary.json")

db_lock = threading.Lock()

def local_extract_rj_code(text: str) -> str | None:
    if not text:
        return None
    match = re.search(r'(?<![a-zA-Z])(RJ|rj)\d{6,8}', text)
    if match:
        return match.group(0).upper()
    return None

class ASMRDatabase:
    _instance = None
    _initialized = False

    def __new__(cls, *args, **kwargs):
        if cls._instance is None:
            cls._instance = super(ASMRDatabase, cls).__new__(cls)
        return cls._instance

    def __init__(self, db_path=DB_PATH):
        if not self._initialized:
            self.db_path = db_path
            self.init_db()
            self._initialized = True

    def get_conn(self):
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def init_db(self):
        with db_lock:
            with self.get_conn() as conn:
                conn.execute("PRAGMA foreign_keys = ON;")
                
                # 1. Projects table
                conn.execute("""
                    CREATE TABLE IF NOT EXISTS projects (
                        project_name TEXT PRIMARY KEY,
                        rj_code TEXT,
                        file_name TEXT,
                        metadata_text TEXT,
                        original_script TEXT,
                        translated_script TEXT,
                        tone TEXT,
                        relationship TEXT,
                        situation TEXT,
                        key_rules TEXT,       -- JSON array
                        script_summary TEXT,  -- JSON dict
                        created_at TEXT,
                        updated_at TEXT
                    );
                """)

                # 2. Chunks table
                conn.execute("""
                    CREATE TABLE IF NOT EXISTS chunks (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        project_name TEXT,
                        chunk_index INTEGER,
                        original_text TEXT,
                        translated_text TEXT,
                        status TEXT DEFAULT 'pending',
                        FOREIGN KEY (project_name) REFERENCES projects(project_name) ON DELETE CASCADE
                    );
                """)

                # 3. Glossary table (both project-specific and master)
                conn.execute("""
                    CREATE TABLE IF NOT EXISTS glossary (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        project_name TEXT,    -- NULL for master glossary
                        source TEXT,
                        target TEXT,
                        context TEXT,
                        is_proper_noun INTEGER DEFAULT 0, -- 0 or 1
                        FOREIGN KEY (project_name) REFERENCES projects(project_name) ON DELETE CASCADE
                    );
                """)

                # 4. Image Notes table
                conn.execute("""
                    CREATE TABLE IF NOT EXISTS image_notes (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        project_name TEXT,
                        image_path TEXT UNIQUE,
                        analysis_note TEXT,
                        FOREIGN KEY (project_name) REFERENCES projects(project_name) ON DELETE CASCADE
                    );
                """)
                conn.commit()

    def run_query(self, query, params=(), commit=False, fetch_all=False, fetch_one=False):
        """Execute a query thread-safely."""
        with db_lock:
            with self.get_conn() as conn:
                cursor = conn.execute(query, params)
                if commit:
                    conn.commit()
                if fetch_all:
                    return [dict(row) for row in cursor.fetchall()]
                if fetch_one:
                    row = cursor.fetchone()
                    return dict(row) if row else None
                return cursor.lastrowid

    def migrate_legacy_data(self):
        """Scan projects folder and master glossary JSON and import them to SQLite if they are not already there."""
        # 1. Migrate Master Glossary
        if os.path.exists(MASTER_GLOSSARY_PATH):
            try:
                with open(MASTER_GLOSSARY_PATH, "r", encoding="utf-8") as f:
                    data = json.load(f)
                if isinstance(data, list):
                    # Check if master glossary table is already populated
                    existing_master_count = self.run_query(
                        "SELECT COUNT(*) as cnt FROM glossary WHERE project_name IS NULL",
                        fetch_one=True
                    )["cnt"]
                    if existing_master_count == 0:
                        print(f"[MIGRATION] Migrating {len(data)} master glossary terms...")
                        for item in data:
                            src = (item.get("원어 (Source)") or item.get("source") or "").strip()
                            tgt = (item.get("번역어 (Target)") or item.get("target") or "").strip()
                            ctx = (item.get("설명/뉘앙스 (Context)") or item.get("context") or item.get("설명") or "").strip()
                            is_proper = 1 if item.get("고유명사 (Proper Noun)", False) else 0
                            if src:
                                self.run_query(
                                    "INSERT OR IGNORE INTO glossary (project_name, source, target, context, is_proper_noun) VALUES (NULL, ?, ?, ?, ?)",
                                    (src, tgt, ctx, is_proper),
                                    commit=True
                                )
            except Exception as e:
                print(f"[MIGRATION WARNING] Failed to migrate master glossary: {e}")

        # 2. Migrate Projects
        if not os.path.exists(BACKUP_ROOT):
            return

        for project_name in os.listdir(BACKUP_ROOT):
            project_dir = os.path.join(BACKUP_ROOT, project_name)
            if not os.path.isdir(project_dir) or project_name.startswith("."):
                continue

            progress_path = os.path.join(project_dir, "progress.json")
            persona_path = os.path.join(project_dir, "persona.json")

            if not os.path.exists(progress_path):
                continue

            # Check if project already exists in SQLite
            exists = self.run_query(
                "SELECT 1 FROM projects WHERE project_name = ?",
                (project_name,),
                fetch_one=True
            )
            if exists:
                continue

            print(f"[MIGRATION] Migrating project '{project_name}'...")
            try:
                # Load progress
                with open(progress_path, "r", encoding="utf-8") as f:
                    progress_data = json.load(f)
                
                file_name = progress_data.get("file_name", f"{project_name}_script.txt")
                original_chunks = progress_data.get("original_chunks", [])
                translated_chunks = progress_data.get("translated_chunks", [])

                # Load scenario.txt if exists to populate original_script
                original_script = ""
                scenario_path = os.path.join(project_dir, "scenario.txt")
                if os.path.exists(scenario_path):
                    with open(scenario_path, "r", encoding="utf-8") as sf:
                        original_script = sf.read()
                else:
                    original_script = "\n".join(original_chunks)

                # Load persona
                persona = {}
                glossary = []
                script_summary = {}
                if os.path.exists(persona_path):
                    with open(persona_path, "r", encoding="utf-8") as f:
                        p_data = json.load(f)
                    persona = p_data.get("persona", {})
                    glossary = p_data.get("glossary_data", [])
                    script_summary = p_data.get("script_summary", {})

                # Extract rj_code
                rj_code = local_extract_rj_code(project_name) or local_extract_rj_code(file_name) or local_extract_rj_code(original_script) or ""

                now = datetime.datetime.now().isoformat()
                
                # Insert Project
                self.run_query(
                    """
                    INSERT OR IGNORE INTO projects (
                        project_name, rj_code, file_name, metadata_text, 
                        original_script, translated_script, tone, relationship, 
                        situation, key_rules, script_summary, created_at, updated_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        project_name, rj_code, file_name, "", original_script, 
                        "\n".join([c for c in translated_chunks if c]), 
                        persona.get("tone", ""), persona.get("relationship", ""), 
                        persona.get("situation", ""), json.dumps(persona.get("key_rules", [])),
                        json.dumps(script_summary), now, now
                    ),
                    commit=True
                )

                # Insert Chunks
                for idx, (orig, trans) in enumerate(zip(original_chunks, translated_chunks)):
                    self.run_query(
                        """
                        INSERT OR IGNORE INTO chunks (project_name, chunk_index, original_text, translated_text, status)
                        VALUES (?, ?, ?, ?, ?)
                        """,
                        (project_name, idx, orig, trans, 'completed' if trans.strip() else 'pending'),
                        commit=True
                    )

                # Insert Glossary
                for item in glossary:
                    src = (item.get("원어 (Source)") or item.get("source") or "").strip()
                    tgt = (item.get("번역어 (Target)") or item.get("target") or "").strip()
                    ctx = (item.get("설명/뉘앙스 (Context)") or item.get("context") or item.get("설명") or "").strip()
                    is_proper = 1 if item.get("고유명사 (Proper Noun)", False) else 0
                    if src:
                        self.run_query(
                            """
                            INSERT OR IGNORE INTO glossary (project_name, source, target, context, is_proper_noun)
                            VALUES (?, ?, ?, ?, ?)
                            """,
                            (project_name, src, tgt, ctx, is_proper),
                            commit=True
                        )

                # Migrate image notes if any analysis.txt files exist in images directory
                images_dir = os.path.join(project_dir, "images")
                if os.path.exists(images_dir):
                    for img_name in os.listdir(images_dir):
                        if img_name.endswith(".analysis.txt"):
                            note_path = os.path.join(images_dir, img_name)
                            # Find matching image
                            img_base = img_name[:-13] # strip .analysis.txt
                            for ext in [".jpg", ".png", ".webp", ".jpeg"]:
                                img_path = os.path.join(images_dir, img_base + ext)
                                if os.path.exists(img_path):
                                    with open(note_path, "r", encoding="utf-8") as nf:
                                        note_content = nf.read()
                                    self.run_query(
                                        """
                                        INSERT OR REPLACE INTO image_notes (project_name, image_path, analysis_note)
                                        VALUES (?, ?, ?)
                                        """,
                                        (project_name, img_path, note_content),
                                        commit=True
                                    )
                                    break

            except Exception as e:
                print(f"[MIGRATION ERROR] Failed migrating '{project_name}': {e}")

# Global singleton DB reference
db = ASMRDatabase()
db.migrate_legacy_data()
