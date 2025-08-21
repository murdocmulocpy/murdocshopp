
from flask import Flask, render_template, request, redirect, url_for, session, flash
from werkzeug.security import generate_password_hash, check_password_hash
import sqlite3, os

app = Flask(__name__)
app.config['SECRET_KEY'] = os.environ.get('APP_SECRET_KEY', 'cambiame_por_una_clave_secreta_segura')
DB_PATH = os.path.join(os.path.dirname(__file__), 'cobranzas.db')

def get_conn():
    return sqlite3.connect(DB_PATH, detect_types=sqlite3.PARSE_DECLTYPES)

def init_db():
    conn = get_conn()
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS users (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        username TEXT UNIQUE NOT NULL,
        password_hash TEXT NOT NULL
    )''')
    c.execute('''CREATE TABLE IF NOT EXISTS movements (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER NOT NULL,
        tipo TEXT NOT NULL CHECK(tipo IN ('ingreso','egreso')),
        descripcion TEXT NOT NULL,
        metodo_pago TEXT NOT NULL,
        monto REAL NOT NULL,
        fecha TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (user_id) REFERENCES users(id)
    )''')
    conn.commit()
    conn.close()

init_db()

@app.template_filter('gs')
def format_guarani(value):
    try:
        value = float(value)
    except (TypeError, ValueError):
        return value
    entero, _, dec = f"{value:,.2f}".partition('.')
    entero = entero.replace(',', '.')
    return f"₲ {entero},{dec}"

def login_required():
    return 'user_id' in session

def current_user_id():
    return session.get('user_id')

@app.route('/register', methods=['GET','POST'])
def register():
    if request.method == 'POST':
        username = request.form.get('username','').strip().lower()
        password = request.form.get('password','').strip()
        if not username or not password:
            flash('Usuario y contraseña son obligatorios.','danger')
        else:
            pw_hash = generate_password_hash(password)
            try:
                conn = get_conn()
                c = conn.cursor()
                c.execute('INSERT INTO users (username, password_hash) VALUES (?,?)',(username, pw_hash))
                conn.commit()
                conn.close()
                flash('Usuario registrado. Iniciá sesión.','success')
                return redirect(url_for('login'))
            except sqlite3.IntegrityError:
                flash('Ese usuario ya existe.','warning')
    return render_template('register.html')

@app.route('/', methods=['GET','POST'])
@app.route('/login', methods=['GET','POST'])
def login():
    if request.method == 'POST':
        username = request.form.get('username','').strip().lower()
        password = request.form.get('password','').strip()
        conn = get_conn()
        c = conn.cursor()
        c.execute('SELECT id, password_hash FROM users WHERE username=?',(username,))
        row = c.fetchone()
        conn.close()
        if row and check_password_hash(row[1], password):
            session['user_id'] = row[0]
            session['username'] = username
            flash('Sesión iniciada.','success')
            return redirect(url_for('dashboard'))
        flash('Usuario o contraseña incorrectos.','danger')
    return render_template('login.html')

@app.route('/logout')
def logout():
    session.clear()
    flash('Sesión cerrada.','info')
    return redirect(url_for('login'))

@app.route('/dashboard')
def dashboard():
    if not login_required():
        return redirect(url_for('login'))
    uid = current_user_id()
    conn = get_conn()
    c = conn.cursor()
    c.execute("""SELECT COALESCE(SUM(CASE WHEN tipo='ingreso' THEN monto ELSE -monto END), 0)
              FROM movements WHERE user_id=?""", (uid,))
    saldo = c.fetchone()[0] or 0.0
    c.execute("SELECT COALESCE(SUM(monto),0) FROM movements WHERE user_id=? AND tipo='ingreso'", (uid,))
    total_ingresos = c.fetchone()[0] or 0.0
    c.execute("SELECT COALESCE(SUM(monto),0) FROM movements WHERE user_id=? AND tipo='egreso'", (uid,))
    total_egresos = c.fetchone()[0] or 0.0
    conn.close()
    return render_template('dashboard.html', saldo=saldo, total_ingresos=total_ingresos, total_egresos=total_egresos)

@app.route('/movimientos', methods=['GET','POST'])
def movimientos():
    if not login_required():
        return redirect(url_for('login'))
    uid = current_user_id()
    conn = get_conn()
    c = conn.cursor()
    if request.method == 'POST':
        tipo = request.form.get('tipo','ingreso')
        descripcion = request.form.get('descripcion','').strip()
        metodo_pago = request.form.get('metodo_pago','').strip()
        monto_raw = request.form.get('monto','0').replace('.','').replace(',','.').strip()
        try:
            monto = float(monto_raw)
        except ValueError:
            monto = 0.0
        if not descripcion or not metodo_pago or monto <= 0 or tipo not in ('ingreso','egreso'):
            flash('Revisá los datos del formulario.','warning')
        else:
            c.execute('INSERT INTO movements (user_id,tipo,descripcion,metodo_pago,monto) VALUES (?,?,?,?,?)',
                      (uid, tipo, descripcion, metodo_pago, monto))
            conn.commit()
            flash('Movimiento registrado.','success')
    c.execute('SELECT id, tipo, descripcion, metodo_pago, monto, fecha FROM movements WHERE user_id=? ORDER BY fecha DESC, id DESC', (uid,))
    registros = c.fetchall()
    conn.close()
    return render_template('movimientos.html', registros=registros)

@app.route('/movimientos/<int:mid>/edit', methods=['GET','POST'])
def edit_movimiento(mid):
    if not login_required():
        return redirect(url_for('login'))
    uid = current_user_id()
    conn = get_conn()
    c = conn.cursor()
    if request.method == 'POST':
        tipo = request.form.get('tipo','ingreso')
        descripcion = request.form.get('descripcion','').strip()
        metodo_pago = request.form.get('metodo_pago','').strip()
        monto_raw = request.form.get('monto','0').replace('.','').replace(',','.').strip()
        try:
            monto = float(monto_raw)
        except ValueError:
            monto = 0.0
        if not descripcion or not metodo_pago or monto <= 0 or tipo not in ('ingreso','egreso'):
            flash('Revisá los datos del formulario.','warning')
        else:
            c.execute('UPDATE movements SET tipo=?, descripcion=?, metodo_pago=?, monto=? WHERE id=? AND user_id=?',
                      (tipo, descripcion, metodo_pago, monto, mid, uid))
            conn.commit()
            conn.close()
            flash('Movimiento actualizado.','success')
            return redirect(url_for('movimientos'))
    c.execute('SELECT id, tipo, descripcion, metodo_pago, monto, fecha FROM movements WHERE id=? AND user_id=?', (mid, uid))
    mov = c.fetchone()
    conn.close()
    if not mov:
        flash('Movimiento no encontrado.','warning')
        return redirect(url_for('movimientos'))
    return render_template('edit_movimiento.html', mov=mov)

@app.route('/movimientos/<int:mid>/delete', methods=['POST'])
def delete_movimiento(mid):
    if not login_required():
        return redirect(url_for('login'))
    uid = current_user_id()
    conn = get_conn()
    c = conn.cursor()
    c.execute('DELETE FROM movements WHERE id=? AND user_id=?', (mid, uid))
    conn.commit()
    conn.close()
    flash('Movimiento eliminado.','info')
    return redirect(url_for('movimientos'))

if __name__ == '__main__':
    app.run(debug=True)
