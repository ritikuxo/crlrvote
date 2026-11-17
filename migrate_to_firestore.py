"""
Migration script: Copy data from SQLite (database.db) to Firebase Firestore.
Run this ONCE before deploying to Render.
"""
import sqlite3
import os
import json
import firebase_admin
from firebase_admin import credentials, firestore, storage

# --- Load service account ---
SERVICE_ACCOUNT_PATH = "serviceAccountKey.json"

if not os.path.exists(SERVICE_ACCOUNT_PATH):
    print(f"❌ ERROR: {SERVICE_ACCOUNT_PATH} not found in root folder!")
    print("Please place your serviceAccountKey.json in the project root and run again.")
    exit(1)

cred = credentials.Certificate(SERVICE_ACCOUNT_PATH)
firebase_admin.initialize_app(cred, {
    'storageBucket': 'crlrvote-f6453.firebasestorage.app'
})

db = firestore.client()
bucket = storage.bucket()

# --- Connect to SQLite ---
SQLITE_DB = "database.db"
if not os.path.exists(SQLITE_DB):
    print(f"❌ ERROR: {SQLITE_DB} not found!")
    exit(1)

conn = sqlite3.connect(SQLITE_DB)
conn.row_factory = sqlite3.Row

print("🔄 Starting migration from SQLite to Firestore...\n")

# ============================================================
# 1. MIGRATE CANDIDATES
# ============================================================
print("📦 Migrating candidates...")
candidates = conn.execute("SELECT * FROM candidates").fetchall()
cand_count = 0
for c in candidates:
    data = dict(c)
    # Use roll_no as document ID for easy lookup
    roll_no = data.pop('roll_no', None)
    if not roll_no:
        continue
    # Convert datetime to string
    if data.get('created_at'):
        data['created_at'] = str(data['created_at'])
    # photo_filename -> photo_url (we'll keep filename for now, upload to storage later if file exists)
    photo_filename = data.get('photo_filename')
    if photo_filename and os.path.exists(os.path.join('static/uploads', photo_filename)):
        try:
            blob = bucket.blob(f"candidate_photos/{photo_filename}")
            blob.upload_from_filename(os.path.join('static/uploads', photo_filename))
            blob.make_public()
            data['photo_url'] = blob.public_url
            print(f"   📸 Uploaded photo: {photo_filename}")
        except Exception as e:
            print(f"   ⚠️  Could not upload photo {photo_filename}: {e}")
            data['photo_url'] = None
    else:
        data['photo_url'] = None
    # Remove photo_filename since we now use photo_url
    data.pop('photo_filename', None)
    db.collection('candidates').document(roll_no).set(data)
    cand_count += 1
print(f"   ✅ {cand_count} candidates migrated\n")

# ============================================================
# 2. MIGRATE VOTERS
# ============================================================
print("📦 Migrating voters...")
voters = conn.execute("SELECT * FROM voters").fetchall()
voter_count = 0
for v in voters:
    data = dict(v)
    roll_no = data.pop('roll_no', None)
    if not roll_no:
        continue
    if data.get('created_at'):
        data['created_at'] = str(data['created_at'])
    if data.get('voted_at'):
        data['voted_at'] = str(data['voted_at'])
    db.collection('voters').document(roll_no).set(data)
    voter_count += 1
print(f"   ✅ {voter_count} voters migrated\n")

# ============================================================
# 3. MIGRATE VOTES
# ============================================================
print("📦 Migrating votes...")
votes = conn.execute("SELECT * FROM votes").fetchall()
vote_count = 0
for v in votes:
    data = dict(v)
    if data.get('voted_at'):
        data['voted_at'] = str(data['voted_at'])
    db.collection('votes').add(data)
    vote_count += 1
print(f"   ✅ {vote_count} votes migrated\n")

conn.close()
print("=" * 50)
print("🎉 MIGRATION COMPLETE!")
print(f"   Candidates: {cand_count}")
print(f"   Voters:     {voter_count}")
print(f"   Votes:      {vote_count}")
print("=" * 50)
print("\n✅ Your data is now in Firestore. You can deploy to Render!")