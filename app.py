import sqlite3


from werkzeug.security import generate_password_hash, check_password_hash
from flask import Flask, render_template, request, jsonify, session, redirect

app = Flask(__name__)
app.secret_key = 'super-secret-key-change-me-in-production'

def load_emails():
    with open('emails.txt', 'r', encoding='utf-8') as f:
        emails = []
        for line in f:
            email = line.strip()
            if email != '':
                emails.append(email)
        return emails

EMAILS = load_emails()

def init_db():
    conn = sqlite3.connect('emails.db')
    c = conn.cursor()
    c.execute('''
        CREATE TABLE IF NOT EXISTS assignments (
            datetime TEXT,
            email TEXT,
            PRIMARY KEY (datetime, email)
        )
    ''')

    c.execute('''
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT UNIQUE NOT NULL,
                password TEXT NOT NULL,
                role TEXT NOT NULL
            )
        ''')

    conn.commit()
    conn.close()


init_db()


def create_admin_if_not_exists():
    conn=sqlite3.connect('emails.db')
    c = conn.cursor()
    c.execute('SELECT id FROM users WHERE role = ?', ('admin',))
    admin = c.fetchone()

    if admin is None:
        password_hash = generate_password_hash('QazwsX14!!')
        c.execute(
            'INSERT INTO users (username, password, role) VALUES (?, ?, ?)',
            ('admin', password_hash, 'admin')
        )
        conn.commit()
        print('✅ Админ создан! Логин: admin, пароль: QazwsX14!!')

    conn.close()

create_admin_if_not_exists()


@app.route('/')
def home():
    if 'user_id' not in session:
        return redirect('/login')

    is_admin = session.get('role') == 'admin'
    return render_template('index.html', is_admin=is_admin)


@app.route('/get-email', methods=['POST'])
def get_email():
    data = request.json
    dt = data['datetime']

    conn = sqlite3.connect('emails.db')
    c = conn.cursor()

    c.execute('SELECT email FROM assignments WHERE datetime = ?', (dt,))
    used_rows = c.fetchall()
    used = [row[0] for row in used_rows]

    available = None
    for email in EMAILS:
        if email not in used:
            available = email
            break

    if available is None:
        conn.close()
        return jsonify({'error': 'Почты на это время закончились'}), 400

    c.execute('INSERT INTO assignments (datetime, email) VALUES (?, ?)', (dt, available))
    conn.commit()
    conn.close()

    return jsonify({
        'email': available,
        'is_new': True
    })


@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        conn = sqlite3.connect('emails.db')
        c = conn.cursor()
        c.execute('SELECT id, username, password, role FROM users WHERE username = ?', (username,))
        user = c.fetchone()
        conn.close()

        if user and check_password_hash(user[2], password):
            session['user_id'] = user[0]
            session['username'] = user[1]
            session['role'] = user[3]

            if user[3] == 'admin':
                return redirect('/admin')
            else:
                return redirect('/')
        else:
            return render_template('login.html', error='Неверный логин или пароль')
    return render_template('login.html')


@app.route('/logout')
def logout():
    session.clear()
    return redirect('/login')


@app.route('/admin')
def admin():
    if 'user_id' not in session:
        return redirect('/login')

    if session.get('role') != 'admin':
        return redirect('/')

    return render_template('admin.html')


@app.route('/admin/emails')
def admin_emails():
    if session.get('role') != 'admin':
        return jsonify({'error': 'Нет доступа'}), 403

    return jsonify({'emails': EMAILS})


@app.route('/admin/users')
def admin_users():
    if session.get('role') != 'admin':
        return jsonify({'error': 'Нет доступа'}), 403

    conn = sqlite3.connect('emails.db')
    c = conn.cursor()
    c.execute('''
        SELECT username, role FROM users 
        ORDER BY CASE WHEN role = 'admin' THEN 0 ELSE 1 END, username ASC
    ''')
    rows = c.fetchall()
    conn.close()

    users = [{'username': row[0], 'role': row[1]} for row in rows]
    return jsonify({'users': users})


@app.route('/admin/add-user', methods=['POST'])
def admin_add_user():
    if session.get('role') != 'admin':
        return jsonify({'error': 'Нет доступа'}), 403

    data = request.json
    username = data.get('username', '').strip()
    password = data.get('password', '')

    if not username:
        return jsonify({'error': 'Введите логин'}), 400

    if not password:
        return jsonify({'error': 'Введите пароль'}), 400

    if len(username) < 3:
        return jsonify({'error': 'Логин минимум 3 символа'}), 400

    if not username.replace('_', '').isalnum() or not username.isascii():
        return jsonify({'error': 'Логин: только латиница, цифры и _'}), 400

    if len(password) < 6:
        return jsonify({'error': 'Пароль минимум 6 символов'}), 400

    conn = sqlite3.connect('emails.db')
    c = conn.cursor()

    c.execute('SELECT id FROM users WHERE username = ?', (username,))
    existing = c.fetchone()

    if existing:
        conn.close()
        return jsonify({'error': 'Такой логин уже занят'}), 400

    password_hash = generate_password_hash(password)
    c.execute(
        'INSERT INTO users (username, password, role) VALUES (?, ?, ?)',
        (username, password_hash, 'user')
    )
    conn.commit()
    conn.close()

    return jsonify({'ok': True, 'username': username})


@app.route('/admin/delete-user', methods=['POST'])
def admin_delete_user():
    if session.get('role') != 'admin':
        return jsonify({'error': 'Нет доступа'}), 403

    data = request.json
    username = data.get('username', '').strip()

    if not username:
        return jsonify({'error': 'Не указан логин'}), 400

    if username == 'admin':
        return jsonify({'error': 'Нельзя удалить админа'}), 403

    if username == session.get('username'):
        return jsonify({'error': 'Нельзя удалить себя'}), 403

    conn = sqlite3.connect('emails.db')
    c = conn.cursor()

    c.execute('SELECT id FROM users WHERE username = ? AND role = ?', (username, 'user'))
    existing = c.fetchone()

    if not existing:
        conn.close()
        return jsonify({'error': 'Работник не найден'}), 404

    c.execute('DELETE FROM users WHERE username = ?', (username,))
    conn.commit()
    conn.close()

    return jsonify({'ok': True, 'username': username})


@app.route('/admin/add-emails', methods=['POST'])
def admin_add_emails():
    if session.get('role') != 'admin':
        return jsonify({'error': 'Нет доступа'}), 403

    data = request.json
    new_emails = data.get('emails', [])

    if not new_emails:
        return jsonify({'error': 'Нет почт для добавления'}), 400

    with open('emails.txt', 'r', encoding='utf-8') as f:
        existing = [line.strip() for line in f if line.strip()]

    added = []
    for email in new_emails:
        email = email.strip()
        if email and email not in existing:
            existing.append(email)
            added.append(email)

    with open('emails.txt', 'w', encoding='utf-8') as f:
        f.write('\n'.join(existing))

    global EMAILS
    EMAILS = existing

    return jsonify({'added': added, 'total': len(existing)})


@app.route('/admin/delete-email', methods=['POST'])
def admin_delete_email():
    if session.get('role') != 'admin':
        return jsonify({'error': 'Нет доступа'}), 403

    data = request.json
    email_to_delete = data.get('email', '').strip()

    if not email_to_delete:
        return jsonify({'error': 'Не указана почта'}), 400

    with open('emails.txt', 'r', encoding='utf-8') as f:
        existing = [line.strip() for line in f if line.strip()]

    if email_to_delete not in existing:
        return jsonify({'error': 'Почта не найдена'}), 404

    existing.remove(email_to_delete)

    with open('emails.txt', 'w', encoding='utf-8') as f:
        f.write('\n'.join(existing))

    global EMAILS
    EMAILS = existing

    return jsonify({'ok': True, 'total': len(existing)})


@app.route('/admin/delete-emails', methods=['POST'])
def admin_delete_emails():
    if session.get('role') != 'admin':
        return jsonify({'error': 'Нет доступа'}), 403

    data = request.json
    emails_to_delete = data.get('emails', [])

    if not emails_to_delete:
        return jsonify({'error': 'Не выбрано ни одной почты'}), 400

    with open('emails.txt', 'r', encoding='utf-8') as f:
        existing = [line.strip() for line in f if line.strip()]

    deleted = []
    for email in emails_to_delete:
        if email in existing:
            existing.remove(email)
            deleted.append(email)

    with open('emails.txt', 'w', encoding='utf-8') as f:
        f.write('\n'.join(existing))

    global EMAILS
    EMAILS = existing

    return jsonify({'deleted': len(deleted), 'total': len(existing)})


if __name__ == '__main__':
    app.run(debug=False)