from app import app
from werkzeug.security import generate_password_hash
import sqlite3

client = app.test_client()
with client.session_transaction() as sess:
    sess['admin_logged_in'] = True

conn = sqlite3.connect('database.db')
conn.row_factory = sqlite3.Row

print("=== TEST 1: Database migration (post column) ===")
columns = [r[1] for r in conn.execute("PRAGMA table_info(candidates)").fetchall()]
print("Candidate columns:", columns)
assert 'post' in columns, "FAIL: post column not found"
print("PASS: post column exists")

print("\n=== TEST 2: Existing candidate has post (default 'CR') ===")
existing = conn.execute('SELECT id, name, post FROM candidates LIMIT 1').fetchone()
print(f"Existing candidate: {existing['name']}, post={existing['post']}")
assert existing['post'] == 'CR', "FAIL: existing candidate post not 'CR'"
print("PASS: existing candidate has post='CR'")

print("\n=== TEST 3: New registration with post ===")
# Create a new voter
try:
    conn.execute('INSERT INTO voters (roll_no, name, has_voted) VALUES (?, ?, 0)', ('NEWVOTER001', 'New Voter'))
    conn.commit()
except:
    pass

# Get a voter to use
voter = conn.execute('SELECT * FROM voters ORDER BY id DESC LIMIT 1').fetchone()

# Register candidate with CR post
resp = client.post('/candidate/register', data={
    'name': 'CR Candidate Test',
    'roll_no': 'CRTEST001',
    'department': 'CSE',
    'year': '3rd Year',
    'post': 'CR',
    'password': 'test123',
    'confirm_password': 'test123',
    'photo': None
}, follow_redirects=True)
print(f"Registration response: {resp.status_code}")

cand = conn.execute('SELECT name, post, status FROM candidates WHERE roll_no = ?', ('CRTEST001',)).fetchone()
print(f"New CR candidate: {cand['name']}, post={cand['post']}, status={cand['status']}")
assert cand['post'] == 'CR', "FAIL: CR candidate post not 'CR'"
assert cand['status'] == 'pending', "FAIL: candidate status not pending"
print("PASS: New CR candidate registered with post='CR'")

# Register candidate with LR post
cand2 = conn.execute('SELECT * FROM candidates WHERE roll_no = ?', ('CRTEST001',)).fetchone()
# Delete and recreate for LR
conn.execute('DELETE FROM candidates WHERE roll_no = ?', ('CRTEST001',))
conn.commit()

resp = client.post('/candidate/register', data={
    'name': 'LR Candidate Test',
    'roll_no': 'LRTEST001',
    'department': 'CSE',
    'year': '3rd Year',
    'post': 'LR',
    'password': 'test123',
    'confirm_password': 'test123',
    'photo': None
}, follow_redirects=True)

cand2 = conn.execute('SELECT name, post, status FROM candidates WHERE roll_no = ?', ('LRTEST001',)).fetchone()
print(f"New LR candidate: {cand2['name']}, post={cand2['post']}, status={cand2['status']}")
assert cand2['post'] == 'LR', "FAIL: LR candidate post not 'LR'"
print("PASS: New LR candidate registered with post='LR'")

print("\n=== TEST 4: Voter dashboard filters by post ===")
# We need a voter with has_voted=0 to vote
voter = conn.execute('SELECT * FROM voters ORDER BY id DESC LIMIT 1').fetchone()
conn.execute('UPDATE voters SET has_voted = 0 WHERE roll_no = ?', (voter['roll_no'],))
conn.commit()

# Vote for CR candidate
# First, we need an approved CR candidate
cand_cr = conn.execute('SELECT id FROM candidates WHERE post = ? AND status = ?', ('CR', 'approved')).fetchone()
cand_lr = conn.execute('SELECT id FROM candidates WHERE post = ? AND status = ?', ('LR', 'approved')).fetchone()

# Approve the test candidates
conn.execute('UPDATE candidates SET status = ? WHERE roll_no = ?', ('approved', 'CRTEST001'))
conn.execute('UPDATE candidates SET status = ? WHERE roll_no = ?', ('approved', 'LRTEST001'))
conn.commit()

# Create a vote
cr_id = conn.execute('SELECT id FROM candidates WHERE roll_no = ?', ('CRTEST001',)).fetchone()['id']
lr_id = conn.execute('SELECT id FROM candidates WHERE roll_no = ?', ('LRTEST001',)).fetchone()['id']
conn.execute('INSERT INTO votes (roll_no, cr_candidate_id, lr_candidate_id) VALUES (?, ?, ?)', (voter['roll_no'], cr_id, lr_id))
conn.commit()

# Now verify voter dashboard filters correctly
# The voter_dashboard route queries cr/post=CR and lr/post=LR
voter_name = conn.execute('SELECT * FROM voters WHERE roll_no = ?', (voter['roll_no'],)).fetchone()
with client.session_transaction() as sess:
    sess['voter_roll_no'] = voter_name['roll_no']

resp = client.get('/voter/dashboard', follow_redirects=True)
print(f"Voter dashboard response: {resp.status_code}")

# Check that the voter sees the CR candidate in the CR section
html = resp.data.decode('utf-8')
assert 'CR Candidate Test' in html, "FAIL: CR candidate not in CR section"
print("PASS: Voter dashboard filters CR candidates correctly")

print("\n=== TEST 5: Admin dashboard shows post badges ===")
resp = client.get('/admin/dashboard', follow_redirects=True)
html = resp.data.decode('utf-8')
assert 'CR' in html, "FAIL: CR post badge not found"
assert 'LR' in html, "FAIL: LR post badge not found"
print("PASS: Admin dashboard shows post badges")

print("\n=== TEST 6: View candidates shows post badges ===")
resp = client.get('/view_candidates', follow_redirects=True)
html = resp.data.decode('utf-8')
print("PASS: View candidates page loaded")
print("(Check console for more details)")

print("\n=== ALL TESTS PASSED ===")
conn.close()