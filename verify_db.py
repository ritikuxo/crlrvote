import sqlite3
conn = sqlite3.connect('database.db')
conn.row_factory = sqlite3.Row

tables = conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
print('Tables:', [r[0] for r in tables])

count = conn.execute('SELECT COUNT(*) FROM voters').fetchone()[0]
print(f'Voter count: {count}')

print('Sample voters:')
for r in conn.execute('SELECT * FROM voters LIMIT 5').fetchall():
    print(f'  {r["roll_no"]} | {r["name"]} | voted: {r["has_voted"]}')

print('Last 3 voters:')
for r in conn.execute('SELECT * FROM voters ORDER BY id DESC LIMIT 3').fetchall():
    print(f'  {r["roll_no"]} | {r["name"]} | voted: {r["has_voted"]}')

conn.close()