import sqlite3

# List of authorized student roll numbers (11 chars, uppercase alphanumeric)
ROLL_NUMBERS = [
    "25ASUR07071", "25ASUR07072", "25ASUR07073", "25ASUR07074", "25ASUR07075",
    "25ASUR07076", "25ASUR07077", "25ASUR07078", "25ASUR07079", "25ASUR07080",
    "25ASUR07081", "25ASUR07082", "25ASUR07083", "25ASUR07084", "25ASUR07085",
    "25ASUR07086", "25ASUR07087", "25ASUR07088", "25ASUR07089", "25ASUR07090",
    "25ASUR07091", "25ASUR07092", "25ASUR07093", "25ASUR07094", "25ASUR07095",
    "25ASUR07096", "25ASUR07097", "25ASUR07098", "25ASUR07099", "25ASUR07100",
    "25ASUR07101", "25ASUR07102", "25ASUR07103", "25ASUR07104", "25ASUR07105",
    "25ASUR07106", "25ASUR07107", "25ASUR07108", "25ASUR07109", "25ASUR07110",
    "25ASUR07111", "25ASUR07112", "25ASUR07113", "25ASUR07114", "25ASUR07115",
    "25ASUR07116", "25ASUR07117", "25ASUR07118", "25ASUR07119", "25ASUR07120",
    "25ASUR07121", "25ASUR07122", "25ASUR07123", "25ASUR07124", "25ASUR07125",
    "25ASUR07126", "25ASUR07127", "25ASUR07128", "25ASUR07129", "25ASUR07130",
    "25ASUR07131", "25ASUR07132", "25ASUR07133", "25ASUR07134", "25ASUR07135",
    "25ASUR07136", "25ASUR07137", "25ASUR07138", "25ASUR07139",
    # Note: 25ASUR07105 appears twice in your list - duplicates will be skipped automatically
]

conn = sqlite3.connect('database.db')
conn.row_factory = sqlite3.Row

# Ensure tables exist
conn.execute('''
    CREATE TABLE IF NOT EXISTS voters (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        roll_no TEXT NOT NULL UNIQUE,
        name TEXT NOT NULL,
        department TEXT,
        year TEXT,
        has_voted INTEGER DEFAULT 0,
        voted_at TIMESTAMP,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )
''')

conn.execute('''
    CREATE TABLE IF NOT EXISTS votes (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        roll_no TEXT NOT NULL,
        cr_candidate_id INTEGER,
        lr_candidate_id INTEGER,
        voted_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (roll_no) REFERENCES voters(roll_no),
        FOREIGN KEY (cr_candidate_id) REFERENCES candidates(id),
        FOREIGN KEY (lr_candidate_id) REFERENCES candidates(id)
    )
''')

added = 0
skipped = 0
for roll in ROLL_NUMBERS:
    try:
        conn.execute(
            'INSERT INTO voters (roll_no, name, has_voted) VALUES (?, ?, 0)',
            (roll, f'Student {roll}')
        )
        added += 1
    except sqlite3.IntegrityError:
        skipped += 1

conn.commit()

# Verify
count = conn.execute('SELECT COUNT(*) FROM voters').fetchone()[0]
print(f"✅ Seeded {added} new voter(s). {skipped} duplicate(s) skipped.")
print(f"📊 Total voters in database: {count}")

conn.close()