from flask import Flask, render_template, request, redirect, url_for, session, flash, Response
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename
import os
import re
import json
from datetime import datetime
import firebase_admin
from firebase_admin import credentials, firestore, storage
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

app = Flask(__name__)
app.secret_key = os.getenv('SECRET_KEY', 'college-election-secret-key-2026')
app.config['UPLOAD_FOLDER'] = 'static/uploads'
app.config['MAX_CONTENT_LENGTH'] = 2 * 1024 * 1024  # 2MB max file size

ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif'}

# Admin credentials from environment variables
ADMIN_USERNAME = os.getenv('ADMIN_USERNAME', 'HODCSE')
ADMIN_PASSWORD = os.getenv('ADMIN_PASSWORD', 'HODCSE@123')
ADMIN_PASSWORD_HASH = generate_password_hash(ADMIN_PASSWORD)

# --- Initialize Firebase (supports FIREBASE_SERVICE_ACCOUNT env var for Render) ---
SERVICE_ACCOUNT_PATH = "serviceAccountKey.json"

service_account_info = os.getenv('FIREBASE_SERVICE_ACCOUNT')

if service_account_info and service_account_info.strip().startswith('{'):
    try:
        service_account_dict = json.loads(service_account_info)
        cred = credentials.Certificate(service_account_dict)
        print("✅ Firebase initialized from FIREBASE_SERVICE_ACCOUNT env variable")
    except json.JSONDecodeError as e:
        print(f"❌ ERROR: FIREBASE_SERVICE_ACCOUNT is not valid JSON: {e}")
        raise
elif os.path.exists(SERVICE_ACCOUNT_PATH):
    cred = credentials.Certificate(SERVICE_ACCOUNT_PATH)
    print(f"✅ Firebase initialized from {SERVICE_ACCOUNT_PATH}")
else:
    print(f"❌ ERROR: Neither FIREBASE_SERVICE_ACCOUNT env var nor {SERVICE_ACCOUNT_PATH} found!")
    raise FileNotFoundError(
        f"Set FIREBASE_SERVICE_ACCOUNT environment variable or place {SERVICE_ACCOUNT_PATH} in project root."
    )

firebase_admin.initialize_app(cred, {
    'storageBucket': os.getenv('FIREBASE_STORAGE_BUCKET', 'crlrvote-f6453.firebasestorage.app')
})

db = firestore.client()
bucket = storage.bucket()

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)

# ============================================================
# HELPER FUNCTIONS (Firestore replacements for SQLite)
# ============================================================

def get_candidate_by_roll_no(roll_no):
    doc = db.collection('candidates').document(roll_no).get()
    if doc.exists:
        data = doc.to_dict()
        data['id'] = doc.id
        data['roll_no'] = doc.id
        return data
    return None

def get_candidate_by_id(doc_id):
    doc = db.collection('candidates').document(doc_id).get()
    if doc.exists:
        data = doc.to_dict()
        data['id'] = doc.id
        data['roll_no'] = doc.id
        return data
    return None

def get_voter_by_roll_no(roll_no):
    doc = db.collection('voters').document(roll_no).get()
    if doc.exists:
        data = doc.to_dict()
        data['id'] = doc.id
        data['roll_no'] = doc.id  # Firestore doc ID = roll_no (was stripped during migration)
        return data
    return None

def get_all_candidates():
    docs = db.collection('candidates').stream()
    result = []
    for doc in docs:
        data = doc.to_dict()
        data['id'] = doc.id
        result.append(data)
    return result

def get_approved_candidates(post=None):
    query = db.collection('candidates').where('status', '==', 'approved')
    if post:
        query = query.where('post', '==', post)
    docs = query.stream()
    result = []
    for doc in docs:
        data = doc.to_dict()
        data['id'] = doc.id
        result.append(data)
    return result

def get_pending_candidates():
    docs = db.collection('candidates').where('status', '==', 'pending').stream()
    result = []
    for doc in docs:
        data = doc.to_dict()
        data['id'] = doc.id
        result.append(data)
    return result

def get_rejected_candidates():
    docs = db.collection('candidates').where('status', '==', 'rejected').stream()
    result = []
    for doc in docs:
        data = doc.to_dict()
        data['id'] = doc.id
        result.append(data)
    return result

def get_all_voters():
    docs = db.collection('voters').stream()
    result = []
    for doc in docs:
        data = doc.to_dict()
        data['id'] = doc.id
        data['roll_no'] = doc.id  # Firestore doc ID = roll_no (was stripped during migration)
        result.append(data)
    return result

# ============================================================
# ROUTES
# ============================================================

@app.route('/')
def index():
    return render_template('index.html')

# ---------- CANDIDATE REGISTRATION ----------
@app.route('/candidate/register', methods=['GET', 'POST'])
def candidate_register():
    if request.method == 'POST':
        name = request.form.get('name')
        roll_no = request.form.get('roll_no')
        department = request.form.get('department')
        year = request.form.get('year')
        post = request.form.get('post')
        password = request.form.get('password')
        confirm_password = request.form.get('confirm_password')
        photo = request.files.get('photo')

        if not all([name, roll_no, department, year, post, password, confirm_password]):
            flash('All fields are required.', 'error')
            return redirect(url_for('candidate_register'))

        if post not in ['CR', 'LR']:
            flash('Please select a valid post (CR or LR).', 'error')
            return redirect(url_for('candidate_register'))

        if password != confirm_password:
            flash('Passwords do not match.', 'error')
            return redirect(url_for('candidate_register'))

        if len(password) < 6:
            flash('Password must be at least 6 characters.', 'error')
            return redirect(url_for('candidate_register'))

        existing = get_candidate_by_roll_no(roll_no)
        if existing and existing.get('can_register_again') == 0:
            flash('This candidate has been rejected by admin. Permission to re-register is required before registration.', 'error')
            return redirect(url_for('candidate_register'))

        photo_filename = None
        photo_url = None
        if photo and photo.filename != '':
            if not allowed_file(photo.filename):
                flash('Only image files (png, jpg, jpeg, gif) are allowed.', 'error')
                return redirect(url_for('candidate_register'))
            photo_filename = secure_filename(f"{roll_no}_{photo.filename}")
            local_path = os.path.join(app.config['UPLOAD_FOLDER'], photo_filename)
            photo.save(local_path)
            try:
                blob = bucket.blob(f"candidate_photos/{photo_filename}")
                blob.upload_from_filename(local_path)
                blob.make_public()
                photo_url = blob.public_url
                os.remove(local_path)
            except Exception as e:
                flash(f'Photo upload failed: {str(e)}', 'error')
                return redirect(url_for('candidate_register'))

        try:
            password_hash = generate_password_hash(password)
            candidate_data = {
                'name': name,
                'roll_no': roll_no,
                'department': department,
                'year': year,
                'post': post,
                'photo_filename': photo_filename,
                'photo_url': photo_url,
                'password_hash': password_hash,
                'status': 'pending',
                'can_register_again': 0,
                'created_at': datetime.now().isoformat()
            }
            db.collection('candidates').document(roll_no).set(candidate_data)
            flash('Registration successful! Your nomination is pending admin approval.', 'info')
            return redirect(url_for('index'))
        except Exception as e:
            flash(f'Registration failed: {str(e)}', 'error')
            return redirect(url_for('candidate_register'))

    return render_template('candidate_register.html')


# ---------- CANDIDATE CHECK NOMINATION STATUS ----------
@app.route('/candidate/status')
def candidate_status():
    if 'candidate_id' not in session:
        flash('Please login to check your nomination status.', 'error')
        return redirect(url_for('index'))

    candidate = get_candidate_by_id(session['candidate_id'])
    if not candidate:
        flash('Candidate not found.', 'error')
        return redirect(url_for('index'))

    return render_template('candidate_status.html', candidate=candidate)


# ---------- CANDIDATE LOGOUT ----------
@app.route('/candidate/logout')
def candidate_logout():
    session.pop('candidate_id', None)
    session.pop('candidate_name', None)
    session.pop('candidate_roll_no', None)
    flash('You have been logged out.', 'info')
    return redirect(url_for('index'))

def get_all_votes():
    docs = db.collection('votes').stream()
    result = []
    for doc in docs:
        data = doc.to_dict()
        data['id'] = doc.id
        result.append(data)
    return result

def count_votes_for_candidate(candidate_id, post):
    field = 'cr_candidate_id' if post == 'CR' else 'lr_candidate_id'
    docs = db.collection('votes').where(field, '==', candidate_id).stream()
    return sum(1 for _ in docs)

# ---------- VOTER LOGIN ----------
@app.route('/voter/login', methods=['GET', 'POST'])
def voter_login():
    if request.method == 'POST':
        roll_no = request.form.get('roll_no', '').strip().upper()
        password = request.form.get('password', '').strip()

        if not roll_no:
            flash('Please enter your roll number.', 'error')
            return redirect(url_for('voter_login'))

        if len(roll_no) != 11:
            flash('Roll number must be exactly 11 characters long.', 'error')
            return redirect(url_for('voter_login'))

        if not re.match(r'^[A-Z0-9]{11}$', roll_no):
            flash('Roll number must be exactly 11 capital letters or digits (A-Z, 0-9) only.', 'error')
            return redirect(url_for('voter_login'))

        voter = get_voter_by_roll_no(roll_no)
        if not voter:
            flash('Roll number not found in the voter list.', 'error')
            return redirect(url_for('voter_login'))

        if voter.get('voter_status') == 'rejected':
            flash('Your voting access has been revoked by admin. You cannot vote.', 'error')
            return redirect(url_for('voter_login'))

        if not voter.get('password_hash'):
            session['voter_roll_no'] = voter['roll_no']
            session['voter_name'] = voter['name']
            flash('Please set your 6-digit voting password.', 'info')
            return redirect(url_for('voter_set_password'))

        if password:
            if not check_password_hash(voter['password_hash'], password):
                flash('Invalid password.', 'error')
                return render_template('voter_login.html', show_password=True, roll_no=roll_no)

            session['voter_roll_no'] = voter['roll_no']
            session['voter_name'] = voter['name']
            session.pop('voter_roll_no_temp', None)
            flash(f'Welcome back, {voter["name"]}!', 'success')
            return redirect(url_for('voter_dashboard'))
        else:
            session['voter_roll_no_temp'] = roll_no
            return render_template('voter_login.html', show_password=True, roll_no=roll_no)

    if session.get('voter_roll_no_temp'):
        roll_no = session.pop('voter_roll_no_temp')
        return render_template('voter_login.html', show_password=True, roll_no=roll_no)

    return render_template('voter_login.html', show_password=False)


# ---------- VOTER SET PASSWORD ----------
@app.route('/voter/set-password', methods=['GET', 'POST'])
def voter_set_password():
    if 'voter_roll_no' not in session:
        flash('Please enter your roll number first.', 'error')
        return redirect(url_for('voter_login'))

    if request.method == 'POST':
        password = request.form.get('password', '').strip()
        confirm_password = request.form.get('confirm_password', '').strip()

        if not password or not confirm_password:
            flash('Please enter and confirm your password.', 'error')
            return redirect(url_for('voter_set_password'))

        if len(password) != 6 or not password.isdigit():
            flash('Password must be exactly 6 digits.', 'error')
            return redirect(url_for('voter_set_password'))

        if password != confirm_password:
            flash('Passwords do not match.', 'error')
            return redirect(url_for('voter_set_password'))

        roll_no = session['voter_roll_no']
        password_hash = generate_password_hash(password)
        db.collection('voters').document(roll_no).update({'password_hash': password_hash})

        flash('Your voting password has been set successfully! You can now log in to vote.', 'success')
        session.pop('voter_roll_no', None)
        session.pop('voter_name', None)
        return redirect(url_for('voter_login'))

    return render_template('voter_set_password.html')


# ---------- VOTER DASHBOARD ----------
@app.route('/voter/dashboard')
def voter_dashboard():
    if 'voter_roll_no' not in session:
        flash('Please login to vote.', 'error')
        return redirect(url_for('voter_login'))

    voter = get_voter_by_roll_no(session['voter_roll_no'])

    if not voter:
        session.pop('voter_roll_no', None)
        session.pop('voter_name', None)
        flash('Voter not found.', 'error')
        return redirect(url_for('voter_login'))

    if voter.get('voter_status') == 'rejected':
        session.pop('voter_roll_no', None)
        session.pop('voter_name', None)
        flash('Your voting access has been revoked by the admin.', 'error')
        return redirect(url_for('voter_login'))

    if voter.get('has_voted'):
        flash('You have already voted. You cannot vote again.', 'info')
        return render_template('voter_already_voted.html', voter=voter)

    cr_candidates = get_approved_candidates(post='CR')
    lr_candidates = get_approved_candidates(post='LR')

    cr_candidates.sort(key=lambda x: x.get('name', ''))
    lr_candidates.sort(key=lambda x: x.get('name', ''))

    return render_template('voter_dashboard.html', voter=voter, cr_candidates=cr_candidates, lr_candidates=lr_candidates)

# ---------- CAST VOTE ----------
@app.route('/voter/vote', methods=['POST'])
def cast_vote():
    if 'voter_roll_no' not in session:
        flash('Please login to vote.', 'error')
        return redirect(url_for('voter_login'))

    roll_no = session['voter_roll_no']
    cr_candidate_id = request.form.get('cr_candidate_id')
    lr_candidate_id = request.form.get('lr_candidate_id')

    voter = get_voter_by_roll_no(roll_no)

    if voter.get('has_voted'):
        flash('You have already voted. You cannot vote again.', 'error')
        return redirect(url_for('voter_dashboard'))

    vote_data = {
        'roll_no': roll_no,
        'cr_candidate_id': cr_candidate_id if cr_candidate_id else None,
        'lr_candidate_id': lr_candidate_id if lr_candidate_id else None,
        'voted_at': datetime.now().isoformat()
    }
    db.collection('votes').add(vote_data)

    db.collection('voters').document(roll_no).update({
        'has_voted': 1,
        'voted_at': datetime.now().isoformat()
    })

    session.pop('voter_roll_no', None)
    session.pop('voter_name', None)
    flash('Your vote has been cast successfully! Thank you for participating.', 'success')
    return redirect(url_for('index'))


# ---------- VOTER LOGOUT ----------
@app.route('/voter/logout')
def voter_logout():
    session.pop('voter_roll_no', None)
    session.pop('voter_name', None)
    flash('You have been logged out.', 'info')
    return redirect(url_for('index'))


# ---------- VIEW ALL CANDIDATES ----------
@app.route('/candidates')
def view_candidates():
    candidates = get_approved_candidates()
    candidates.sort(key=lambda x: x.get('created_at', ''), reverse=True)
    return render_template('view_candidates.html', candidates=candidates)

# ---------- ADMIN LOGIN ----------
@app.route('/admin/login', methods=['GET', 'POST'])
def admin_login():
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')

        if username == ADMIN_USERNAME and check_password_hash(ADMIN_PASSWORD_HASH, password):
            session['admin_logged_in'] = True
            flash('Admin login successful.', 'success')
            return redirect(url_for('admin_dashboard'))
        else:
            flash('Invalid admin credentials.', 'error')
            return redirect(url_for('admin_login'))

    return render_template('admin_login.html')


# ---------- ADMIN DASHBOARD ----------
@app.route('/admin/dashboard')
def admin_dashboard():
    if not session.get('admin_logged_in'):
        flash('Please login as admin.', 'error')
        return redirect(url_for('admin_login'))

    pending = get_pending_candidates()
    approved = get_approved_candidates()
    rejected = get_rejected_candidates()
    all_voters = get_all_voters()
    total_voters = len(all_voters)
    voted_count = sum(1 for v in all_voters if v.get('has_voted') == 1)

    return render_template('admin_dashboard.html',
                           pending=pending, approved=approved, rejected=rejected,
                           total_voters=total_voters, voted_count=voted_count)

# ---------- ADMIN VOTING RECORDS ----------
@app.route('/admin/voting-records')
def admin_voting_records():
    if not session.get('admin_logged_in'):
        flash('Please login as admin.', 'error')
        return redirect(url_for('admin_login'))

    votes = get_all_votes()
    candidates_map = {}
    for c in get_all_candidates():
        candidates_map[c['id']] = c

    voters_map = {}
    for v in get_all_voters():
        voters_map[v['id']] = v

    voting_records = []
    for v in votes:
        roll_no = v.get('roll_no')
        cr_id = v.get('cr_candidate_id')
        lr_id = v.get('lr_candidate_id')

        voter_name = voters_map.get(roll_no, {}).get('name', 'Unknown')
        cr_name = candidates_map.get(cr_id, {}).get('name', 'N/A') if cr_id else 'N/A'
        lr_name = candidates_map.get(lr_id, {}).get('name', 'N/A') if lr_id else 'N/A'
        cr_post = candidates_map.get(cr_id, {}).get('post', '') if cr_id else ''

        voting_records.append({
            'id': v.get('id'),
            'roll_no': roll_no,
            'cr_candidate_id': cr_id,
            'lr_candidate_id': lr_id,
            'voted_at': v.get('voted_at'),
            'voter_name': voter_name,
            'cr_post': cr_post,
            'cr_candidate_name': cr_name,
            'lr_candidate_name': lr_name
        })

    voting_records.sort(key=lambda x: x.get('voted_at', ''), reverse=True)

    return render_template('admin_voting_records.html', voting_records=voting_records)


# ---------- ADMIN REJECT A VOTE ----------
@app.route('/admin/reject-vote/<vote_id>')
def admin_reject_vote(vote_id):
    if not session.get('admin_logged_in'):
        flash('Please login as admin.', 'error')
        return redirect(url_for('admin_login'))

    vote_doc = db.collection('votes').document(vote_id).get()
    if not vote_doc.exists:
        flash('Vote not found.', 'error')
        return redirect(url_for('admin_voting_records'))

    vote_data = vote_doc.to_dict()
    roll_no = vote_data.get('roll_no')

    db.collection('votes').document(vote_id).delete()
    db.collection('voters').document(roll_no).update({
        'has_voted': 0,
        'voted_at': None
    })

    flash('Vote rejected and voter status reset. The voter can vote again.', 'info')
    return redirect(url_for('admin_voting_records'))


# ---------- ADMIN APPROVE CANDIDATE ----------
@app.route('/admin/approve/<candidate_id>')
def admin_approve(candidate_id):
    if not session.get('admin_logged_in'):
        flash('Please login as admin.', 'error')
        return redirect(url_for('admin_login'))

    db.collection('candidates').document(candidate_id).update({'status': 'approved'})
    flash('Candidate approved successfully!', 'success')
    return redirect(url_for('admin_dashboard'))


# ---------- ADMIN REJECT CANDIDATE ----------
@app.route('/admin/reject/<candidate_id>', methods=['GET', 'POST'])
def admin_reject(candidate_id):
    if not session.get('admin_logged_in'):
        flash('Please login as admin.', 'error')
        return redirect(url_for('admin_login'))

    candidate = get_candidate_by_id(candidate_id)
    if not candidate:
        flash('Candidate not found.', 'error')
        return redirect(url_for('admin_dashboard'))

    if request.method == 'POST':
        allow_re_register = request.form.get('allow_re_register') == 'on'
        db.collection('candidates').document(candidate_id).update({
            'status': 'rejected',
            'can_register_again': 1 if allow_re_register else 0
        })

        if allow_re_register:
            flash(f'{candidate["name"]} has been rejected and permission granted to re-register.', 'info')
        else:
            flash(f'{candidate["name"]} has been rejected.', 'info')
        return redirect(url_for('admin_dashboard'))

    return render_template('admin_reject_confirm.html', candidate=candidate)


# ---------- ADMIN REMOVE CANDIDATE ----------
@app.route('/admin/remove/<candidate_id>')
def admin_remove(candidate_id):
    if not session.get('admin_logged_in'):
        flash('Please login as admin.', 'error')
        return redirect(url_for('admin_login'))

    votes = get_all_votes()
    for v in votes:
        if v.get('cr_candidate_id') == candidate_id or v.get('lr_candidate_id') == candidate_id:
            db.collection('votes').document(v['id']).delete()

    db.collection('candidates').document(candidate_id).delete()

    flash('Candidate removed completely!', 'success')
    return redirect(url_for('admin_dashboard'))

# ---------- ADMIN ALLOW RE-REGISTRATION ----------
@app.route('/admin/allow-re-register/<candidate_id>')
def admin_allow_re_register(candidate_id):
    if not session.get('admin_logged_in'):
        flash('Please login as admin.', 'error')
        return redirect(url_for('admin_login'))

    db.collection('candidates').document(candidate_id).update({'can_register_again': 1})
    flash('Re-registration permission granted!', 'success')
    return redirect(url_for('admin_dashboard'))


# ---------- ADMIN CLEAR ALL CANDIDATES ----------
@app.route('/admin/clear-candidates', methods=['GET', 'POST'])
def admin_clear_candidates():
    if not session.get('admin_logged_in'):
        flash('Please login as admin.', 'error')
        return redirect(url_for('admin_login'))

    if request.method == 'POST':
        votes = get_all_votes()
        for v in votes:
            db.collection('votes').document(v['id']).delete()

        candidates = get_all_candidates()
        for c in candidates:
            db.collection('candidates').document(c['id']).delete()

        flash('All candidate data has been cleared. Candidates can now re-register with the same roll numbers.', 'success')
        return redirect(url_for('admin_dashboard'))

    total_candidates = len(get_all_candidates())
    total_votes = len(get_all_votes())
    return render_template('admin_clear_candidates.html', total_candidates=total_candidates, total_votes=total_votes)


# ---------- ADMIN: ADD VOTERS ----------
@app.route('/admin/add-voters', methods=['GET', 'POST'])
def admin_add_voters():
    if not session.get('admin_logged_in'):
        flash('Please login as admin.', 'error')
        return redirect(url_for('admin_login'))

    if request.method == 'POST':
        roll_numbers = request.form.get('roll_numbers')
        names = request.form.get('names')

        if not roll_numbers:
            flash('Please enter roll numbers.', 'error')
            return redirect(url_for('admin_add_voters'))

        roll_list = [r.strip() for r in roll_numbers.replace('\n', ',').split(',') if r.strip()]
        name_list = [n.strip() for n in names.replace('\n', ',').split(',')] if names else []

        added = 0
        skipped = 0
        for i, roll in enumerate(roll_list):
            name = name_list[i] if i < len(name_list) else f'Student {roll}'
            try:
                existing = get_voter_by_roll_no(roll)
                if existing:
                    skipped += 1
                    continue
                db.collection('voters').document(roll).set({
                    'roll_no': roll,
                    'name': name,
                    'department': None,
                    'year': None,
                    'password_hash': None,
                    'has_voted': 0,
                    'voted_at': None,
                    'voter_status': 'active',
                    'created_at': datetime.now().isoformat()
                })
                added += 1
            except Exception as e:
                skipped += 1

        flash(f'Added {added} voter(s). {skipped} already existed.', 'success')
        return redirect(url_for('admin_dashboard'))

    return render_template('admin_add_voters.html')

# ---------- ADMIN: DECLARE RESULTS (Login) ----------
@app.route('/admin/declare-results', methods=['GET', 'POST'])
def admin_declare_results_login():
    if request.method == 'POST':
        admin_id = request.form.get('admin_id', '').strip()
        admin_password = request.form.get('admin_password', '').strip()

        if not admin_id or not admin_password:
            flash('Please enter both Admin ID and Password.', 'error')
            return render_template('admin_declare_login.html')

        if admin_id == ADMIN_USERNAME and check_password_hash(ADMIN_PASSWORD_HASH, admin_password):
            session['admin_results_verified'] = True
            flash('Admin verified. Accessing election results...', 'success')
            return redirect(url_for('admin_results'))
        else:
            flash('Invalid Admin ID or Password.', 'error')
            return render_template('admin_declare_login.html')

    return render_template('admin_declare_login.html')


# ---------- ADMIN: SHOW RESULTS ----------
@app.route('/admin/results')
def admin_results():
    if not session.get('admin_results_verified'):
        flash('Please authenticate first.', 'error')
        return redirect(url_for('admin_declare_results_login'))

    cr_candidates = get_approved_candidates(post='CR')
    for c in cr_candidates:
        c['vote_count'] = count_votes_for_candidate(c['id'], 'CR')
    cr_candidates.sort(key=lambda x: (-x['vote_count'], x.get('name', '')))

    lr_candidates = get_approved_candidates(post='LR')
    for c in lr_candidates:
        c['vote_count'] = count_votes_for_candidate(c['id'], 'LR')
    lr_candidates.sort(key=lambda x: (-x['vote_count'], x.get('name', '')))

    votes = get_all_votes()
    candidates_map = {c['id']: c for c in get_all_candidates()}

    voting_log = []
    for v in votes:
        cr_id = v.get('cr_candidate_id')
        lr_id = v.get('lr_candidate_id')
        cr_name = candidates_map.get(cr_id, {}).get('name', 'N/A') if cr_id else 'N/A'
        lr_name = candidates_map.get(lr_id, {}).get('name', 'N/A') if lr_id else 'N/A'
        voting_log.append({
            'id': v.get('id'),
            'roll_no': v.get('roll_no'),
            'cr_candidate_id': cr_id,
            'lr_candidate_id': lr_id,
            'voted_at': v.get('voted_at'),
            'cr_candidate_name': cr_name,
            'lr_candidate_name': lr_name
        })
    voting_log.sort(key=lambda x: x.get('voted_at', ''))

    total_cr_votes = sum(c['vote_count'] for c in cr_candidates)
    total_lr_votes = sum(c['vote_count'] for c in lr_candidates)
    total_votes = total_cr_votes + total_lr_votes

    return render_template('admin_results.html',
                           cr_candidates=cr_candidates,
                           lr_candidates=lr_candidates,
                           voting_log=voting_log,
                           total_votes=total_votes)

# ---------- ADMIN: DOWNLOAD RESULTS ----------
@app.route('/admin/download-results')
def admin_download_results():
    if not session.get('admin_results_verified'):
        flash('Please authenticate first.', 'error')
        return redirect(url_for('admin_declare_results_login'))

    cr_candidates = get_approved_candidates(post='CR')
    for c in cr_candidates:
        c['vote_count'] = count_votes_for_candidate(c['id'], 'CR')
    cr_candidates.sort(key=lambda x: (-x['vote_count'], x.get('name', '')))

    lr_candidates = get_approved_candidates(post='LR')
    for c in lr_candidates:
        c['vote_count'] = count_votes_for_candidate(c['id'], 'LR')
    lr_candidates.sort(key=lambda x: (-x['vote_count'], x.get('name', '')))

    votes = get_all_votes()
    candidates_map = {c['id']: c for c in get_all_candidates()}

    voting_log = []
    for v in votes:
        cr_id = v.get('cr_candidate_id')
        lr_id = v.get('lr_candidate_id')
        cr_name = candidates_map.get(cr_id, {}).get('name', 'N/A') if cr_id else 'N/A'
        lr_name = candidates_map.get(lr_id, {}).get('name', 'N/A') if lr_id else 'N/A'
        voting_log.append({
            'roll_no': v.get('roll_no'),
            'voted_at': v.get('voted_at'),
            'cr_name': cr_name,
            'lr_name': lr_name
        })

    csv_content = "COLLEGE CR & LR ELECTION RESULTS\n"
    csv_content += "=" * 50 + "\n\n"

    csv_content += "CR (Class Representative) RESULTS:\n"
    csv_content += "-" * 40 + "\n"
    csv_content += "Candidate Name,Roll No,Votes\n"
    for c in cr_candidates:
        csv_content += f"{c.get('name','')},{c.get('roll_no','')},{c.get('vote_count',0)}\n"
    csv_content += "\n"

    csv_content += "LR (Lady Representative) RESULTS:\n"
    csv_content += "-" * 40 + "\n"
    csv_content += "Candidate Name,Roll No,Votes\n"
    for c in lr_candidates:
        csv_content += f"{c.get('name','')},{c.get('roll_no','')},{c.get('vote_count',0)}\n"
    csv_content += "\n"

    csv_content += "DETAILED VOTING LOG:\n"
    csv_content += "-" * 40 + "\n"
    csv_content += "Voter Roll No,Voted At,CR Candidate,LR Candidate\n"
    for v in voting_log:
        csv_content += f"{v['roll_no']},{v['voted_at']},{v['cr_name'] or 'N/A'},{v['lr_name'] or 'N/A'}\n"

    return Response(
        csv_content,
        mimetype='text/csv',
        headers={'Content-Disposition': 'attachment; filename=election_results.csv'}
    )

# ---------- ADMIN: VIEW ALL VOTERS ----------
@app.route('/admin/view-voters')
def admin_view_voters():
    if not session.get('admin_logged_in'):
        flash('Please login as admin.', 'error')
        return redirect(url_for('admin_login'))

    voters = get_all_voters()
    voters.sort(key=lambda x: x.get('roll_no', ''))
    return render_template('admin_view_voters.html', voters=voters)


# ---------- ADMIN: REJECT/APPROVE VOTER ----------
@app.route('/admin/reject-voter/<voter_id>')
def admin_reject_voter(voter_id):
    if not session.get('admin_logged_in'):
        flash('Please login as admin.', 'error')
        return redirect(url_for('admin_login'))

    voter = get_voter_by_roll_no(voter_id)
    if not voter:
        flash('Voter not found.', 'error')
        return redirect(url_for('admin_view_voters'))

    new_status = 'rejected' if voter.get('voter_status') == 'active' else 'active'
    db.collection('voters').document(voter_id).update({'voter_status': new_status})

    if new_status == 'rejected':
        flash(f'Voter {voter.get("roll_no")} has been REJECTED and cannot vote.', 'warning')
    else:
        flash(f'Voter {voter.get("roll_no")} has been APPROVED and can now vote.', 'success')

    return redirect(url_for('admin_view_voters'))


# ---------- ADMIN LOGOUT ----------
@app.route('/admin/logout')
def admin_logout():
    session.pop('admin_logged_in', None)
    flash('Admin logged out.', 'info')
    return redirect(url_for('index'))


if __name__ == '__main__':
    app.run(debug=True, port=5000)