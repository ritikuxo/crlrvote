import sqlite3
conn = sqlite3.connect('database.db')
conn.row_factory = sqlite3.Row

print('=== Database Summary ===')

# Count candidates by status
print('Candidates by Status:')
for row in conn.execute('SELECT status, COUNT(*) as count FROM candidates GROUP BY status'):
    print(f'  {row["status"]}: {row["count"]}')

total = conn.execute('SELECT COUNT(*) as count FROM candidates').fetchone()['count']
print(f'Total Candidates: {total}')

print('Total Votes:')
print(f'  {conn.execute("SELECT COUNT(*) as count FROM votes").fetchone()["count"]}')

print('Sample Candidates:')
for row in conn.execute('SELECT id, name, roll_no, status, post FROM candidates LIMIT 5'):
    print(f'  {row["name"]} ({row["roll_no"]}) - {row["status"]} - post={row["post"]}')

conn.close()
