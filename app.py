from flask import Flask, render_template, request, redirect, url_for, flash, jsonify
from flask_login import LoginManager, login_user, logout_user, login_required, current_user
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import datetime
import os
import pymysql
from pymysql.cursors import DictCursor
from config import Config
from flask_mail import Mail, Message

# Inicialização do app
app = Flask(__name__)
app.config.from_object(Config)

# Configuração do Flask-Login
login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'login'

# Função para obter conexão com o banco
def get_db_connection():
    return pymysql.connect(
        host=app.config['MYSQL_HOST'],
        port=int(app.config['MYSQL_PORT']),
        user=app.config['MYSQL_USER'],
        password=app.config['MYSQL_PASSWORD'],
        database=app.config['MYSQL_DB'],
        cursorclass=DictCursor,
        ssl={}  # Habilita SSL sem configurações específicas
    )

# Classe de usuário para o Flask-Login
class User:
    def __init__(self, user_data):
        self.id = user_data['id']
        self.name = user_data['name']
        self.email = user_data['email']
        self.password_hash = user_data['password_hash']
        self.cpf = user_data['cpf']
        self.phone = user_data['phone']
        self.role = user_data['role']
        self.is_superuser = bool(user_data['is_superuser'])
        self.is_active = bool(user_data['is_active'])
        self._units = None
    
    def get_id(self):
        return str(self.id)
    
    @property
    def is_authenticated(self):
        return True
        
    @property
    def is_anonymous(self):
        return False
    
    @property
    def units(self):
        if self._units is None:
            conn = get_db_connection()
            cursor = conn.cursor()
            cursor.execute(
                "SELECT u.* FROM unit u "
                "JOIN user_unit uu ON u.id = uu.unit_id "
                "WHERE uu.user_id = %s",
                (self.id,)
            )
            self._units = cursor.fetchall()
            cursor.close()
            conn.close()
        return self._units

@login_manager.user_loader
def load_user(user_id):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM user WHERE id = %s", (user_id,))
    user_data = cursor.fetchone()
    cursor.close()
    conn.close()
    
    if not user_data:
        return None
    
    return User(user_data)
# Inicialização do mail
mail = Mail(app)

# Função para enviar e-mail com senha temporária
def send_password_email(email, password, name, is_reset=False):
    if is_reset:
        subject = 'Casa do Biscoito - Redefinição de Senha'
        template = 'reset_password_email.html'
    else:
        subject = 'Casa do Biscoito - Boas-vindas e Senha Temporária'
        template = 'new_user_email.html'
    
    msg = Message(
        subject,
        recipients=[email]
    )
    
    msg.html = render_template(template, 
                              name=name, 
                              password=password,
                              login_url=url_for('login', _external=True))
    
    try:
        mail.send(msg)
        return True
    except Exception as e:
        print(f"Erro ao enviar e-mail: {str(e)}")
        return False
# Criar tabelas do banco de dados (se não existirem)
def initialize_database():
    conn = get_db_connection()
    cursor = conn.cursor()
    
    # Tabela de usuários
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS user (
        id INT AUTO_INCREMENT PRIMARY KEY,
        name VARCHAR(100) NOT NULL,
        email VARCHAR(100) UNIQUE NOT NULL,
        password_hash VARCHAR(255) NOT NULL,
        cpf VARCHAR(20),
        phone VARCHAR(20),
        role VARCHAR(50),
        is_superuser BOOLEAN DEFAULT FALSE,
        is_active BOOLEAN DEFAULT TRUE,
        last_login DATETIME
    )
    """)
    
    # Tabela de unidades
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS unit (
        id INT AUTO_INCREMENT PRIMARY KEY,
        name VARCHAR(100) NOT NULL,
        address VARCHAR(255),
        phone VARCHAR(20),
        is_active BOOLEAN DEFAULT TRUE
    )
    """)
    
    # Tabela de relação usuário-unidade
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS user_unit (
        user_id INT,
        unit_id INT,
        PRIMARY KEY (user_id, unit_id),
        FOREIGN KEY (user_id) REFERENCES user(id) ON DELETE CASCADE,
        FOREIGN KEY (unit_id) REFERENCES unit(id) ON DELETE CASCADE
    )
    """)
    
    # Tabela de caixas
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS cashier (
        id INT AUTO_INCREMENT PRIMARY KEY,
        unit_id INT,
        number INT,
        status VARCHAR(20) DEFAULT 'fechado',
        FOREIGN KEY (unit_id) REFERENCES unit(id) ON DELETE CASCADE
    )
    """)
    
    # Tabela de métodos de pagamento
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS payment_method (
        id INT AUTO_INCREMENT PRIMARY KEY,
        name VARCHAR(50) NOT NULL,
        category VARCHAR(20) NOT NULL,
        is_active BOOLEAN DEFAULT TRUE
    )
    """)
    
    # Tabela de movimentações
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS movement (
        id INT AUTO_INCREMENT PRIMARY KEY,
        cashier_id INT,
        type VARCHAR(20) NOT NULL,
        amount DECIMAL(10,2) NOT NULL,
        payment_method INT,
        description TEXT,
        payment_status VARCHAR(20) DEFAULT 'realizado',
        coins_in DECIMAL(10,2) DEFAULT 0,
        coins_out DECIMAL(10,2) DEFAULT 0,
        client_name VARCHAR(100),
        document_number VARCHAR(50),
        created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (cashier_id) REFERENCES cashier(id) ON DELETE CASCADE,
        FOREIGN KEY (payment_method) REFERENCES payment_method(id)
    )
    """)
    
    # Inserir métodos de pagamento padrão se não existirem
    cursor.execute("SELECT COUNT(*) as count FROM payment_method")
    count = cursor.fetchone()['count']
    
    if count == 0:
        payment_methods = [
            ('Dinheiro', 'dinheiro', True),
            ('Cartão de Crédito', 'credito', True),
            ('Cartão de Débito', 'debito', True),
            ('PIX', 'pix', True),
            ('Vale Alimentação', 'ticket', True)
        ]
        cursor.executemany(
            "INSERT INTO payment_method (name, category, is_active) VALUES (%s, %s, %s)",
            payment_methods
        )
    
    conn.commit()
    cursor.close()
    conn.close()

@app.before_first_request
def create_tables():
    initialize_database()

# Rotas de autenticação
@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        email = request.form.get('email')
        password = request.form.get('password')
        
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM user WHERE email = %s", (email,))
        user_data = cursor.fetchone()
        cursor.close()
        
        if user_data and check_password_hash(user_data['password_hash'], password):
            user = User(user_data)
            login_user(user)
            
            # Atualizar último login
            conn.cursor().execute(
                "UPDATE user SET last_login = %s WHERE id = %s", 
                (datetime.utcnow(), user.id)
            )
            conn.commit()
            conn.close()
            
            next_page = request.args.get('next')
            if user.is_superuser:
                return redirect(next_page or url_for('admin_home'))
            else:
                return redirect(next_page or url_for('user_home'))
        else:
            if conn:
                conn.close()
            flash('Email ou senha inválidos!', 'error')
    
    return render_template('auth/login.html')

@app.route('/logout')
@login_required
def logout():
    logout_user()
    return redirect(url_for('login'))

# Rota padrão - redireciona para área adequada
@app.route('/')
@login_required
def index():
    if current_user.is_superuser:
        return redirect(url_for('admin_home'))
    else:
        return redirect(url_for('user_home'))

# === Rotas de Administrador ===
@app.route('/admin')
@login_required
def admin_home():
    if not current_user.is_superuser:
        flash('Acesso não autorizado!', 'error')
        return redirect(url_for('user_home'))
    
    return render_template('admin/home.html')

@app.route('/admin/users')
@login_required
def admin_users_list():
    if not current_user.is_superuser:
        flash('Acesso não autorizado!', 'error')
        return redirect(url_for('user_home'))
    
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM user ORDER BY name")
    users = cursor.fetchall()
    cursor.close()
    conn.close()
    
    return render_template('admin/users_list.html', users=users)

@app.route('/admin/users/create', methods=['GET', 'POST'])
@login_required
def admin_create_user():
    if not current_user.is_superuser:
        flash('Acesso não autorizado!', 'error')
        return redirect(url_for('user_home'))
    
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM unit WHERE is_active = 1 ORDER BY name")
    units = cursor.fetchall()
    cursor.close()
    
    if request.method == 'POST':
        name = request.form.get('name')
        email = request.form.get('email')
        cpf = request.form.get('cpf')
        phone = request.form.get('phone')
        role = request.form.get('role')
        is_superuser = 1 if 'is_superuser' in request.form else 0
        selected_units = request.form.getlist('units')
        
        # Verificar se o email já existe
        cursor = conn.cursor()
        cursor.execute("SELECT id FROM user WHERE email = %s", (email,))
        existing_user = cursor.fetchone()
        cursor.close()
        
        if existing_user:
            conn.close()
            flash('Este email já está cadastrado!', 'error')
            return render_template('admin/create_user.html', units=units)
        
        # Gerar uma senha temporária (6 caracteres alfanuméricos)
        import random
        import string
        temp_password = ''.join(random.choices(string.ascii_letters + string.digits, k=6))
        password_hash = generate_password_hash(temp_password)
        
        try:
            cursor = conn.cursor()
            cursor.execute(
                "INSERT INTO users (name, email, password_hash, cpf, phone, role, is_superuser, is_active, created_at) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)",
                (name, email, password_hash, cpf, phone, role, is_superuser, 1, datetime.now())
            )
            user_id = cursor.lastrowid
            
            # Adicionar unidades selecionadas
            if not is_superuser and selected_units:
                unit_values = [(user_id, int(unit_id)) for unit_id in selected_units]
                cursor.executemany(
                    "INSERT INTO user_unit (user_id, unit_id) VALUES (%s, %s)",
                    unit_values
                )
            
            conn.commit()
            cursor.close()
            
            # Enviar e-mail com senha temporária
            email_sent = send_password_email(email, temp_password, name)
            
            if email_sent:
                flash(f'Usuário criado com sucesso! Uma senha temporária foi enviada para o e-mail {email}.', 'success')
            else:
                flash(f'Usuário criado com sucesso! Não foi possível enviar o e-mail. Senha temporária: {temp_password}', 'warning')
            
            return redirect(url_for('admin_users_list'))
            
        except Exception as e:
            conn.rollback()
            conn.close()
            flash(f'Erro ao criar usuário: {str(e)}', 'error')
    
    return render_template('admin/create_user.html', units=units)

@app.route('/reset-password', methods=['GET', 'POST'])
def reset_password_request():
    if current_user.is_authenticated:
        return redirect(url_for('index'))
    
    if request.method == 'POST':
        email = request.form.get('email')
        
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM users WHERE email = %s", (email,))
        user = cursor.fetchone()
        
        if user:
            # Gerar um token único para redefinição
            import secrets
            token = secrets.token_hex(16)
            expires = datetime.now() + datetime.timedelta(hours=24)
            
            # Salvar o token no banco
            cursor.execute(
                "INSERT INTO password_reset (user_id, token, expires) VALUES (%s, %s, %s)",
                (user['id'], token, expires)
            )
            conn.commit()
            
            # Enviar e-mail com link para redefinição
            reset_url = url_for('reset_password', token=token, _external=True)
            
            msg = Message('Casa do Biscoito - Redefinição de Senha',
                         recipients=[email])
            msg.html = render_template('auth/reset_password_email.html', 
                                     name=user['name'], 
                                     reset_url=reset_url)
            
            try:
                mail.send(msg)
                flash('Um e-mail foi enviado com instruções para redefinir sua senha.', 'success')
            except Exception as e:
                flash('Não foi possível enviar o e-mail. Por favor, tente novamente mais tarde.', 'error')
                print(f"Erro ao enviar e-mail: {str(e)}")
        else:
            # Por segurança, não informar se o e-mail existe ou não
            flash('Um e-mail foi enviado com instruções para redefinir sua senha, se o endereço estiver registrado.', 'success')
        
        cursor.close()
        conn.close()
        return redirect(url_for('login'))
    
    return render_template('auth/reset_request.html')

@app.route('/reset-password/<token>', methods=['GET', 'POST'])
def reset_password(token):
    if current_user.is_authenticated:
        return redirect(url_for('index'))
    
    conn = get_db_connection()
    cursor = conn.cursor()
    
    # Verificar se o token é válido
    cursor.execute(
        "SELECT user_id, expires FROM password_reset WHERE token = %s AND used = 0",
        (token,)
    )
    reset_data = cursor.fetchone()
    
    if not reset_data or reset_data['expires'] < datetime.now():
        cursor.close()
        conn.close()
        flash('O link de redefinição de senha é inválido ou expirou.', 'error')
        return redirect(url_for('reset_password_request'))
    
    if request.method == 'POST':
        password = request.form.get('password')
        password_confirm = request.form.get('password_confirm')
        
        if password != password_confirm:
            flash('As senhas não coincidem.', 'error')
            return render_template('auth/reset_password.html', token=token)
        
        # Atualizar senha do usuário
        cursor.execute(
            "UPDATE users SET password_hash = %s WHERE id = %s",
            (generate_password_hash(password), reset_data['user_id'])
        )
        
        # Marcar token como usado
        cursor.execute(
            "UPDATE password_reset SET used = 1 WHERE token = %s",
            (token,)
        )
        
        conn.commit()
        flash('Sua senha foi redefinida com sucesso! Você pode fazer login agora.', 'success')
        
        cursor.close()
        conn.close()
        return redirect(url_for('login'))
    
    cursor.close()
    conn.close()
    return render_template('auth/reset_password.html', token=token)



@app.route('/admin/users/<int:user_id>/edit', methods=['GET', 'POST'])
@login_required
def admin_edit_user(user_id):
    if not current_user.is_superuser:
        flash('Acesso não autorizado!', 'error')
        return redirect(url_for('user_home'))
    
    conn = get_db_connection()
    cursor = conn.cursor()
    
    # Obter informações do usuário
    cursor.execute("SELECT * FROM user WHERE id = %s", (user_id,))
    user = cursor.fetchone()
    
    if not user:
        cursor.close()
        conn.close()
        flash('Usuário não encontrado!', 'error')
        return redirect(url_for('admin_users_list'))
    
    # Obter unidades ativas
    cursor.execute("SELECT * FROM unit WHERE is_active = 1 ORDER BY name")
    units = cursor.fetchall()
    
    # Obter unidades do usuário
    cursor.execute("SELECT unit_id FROM user_unit WHERE user_id = %s", (user_id,))
    user_units = [row['unit_id'] for row in cursor.fetchall()]
    
    # Para cada unidade, adicionar se está associada ao usuário
    for unit in units:
        unit['user_has_unit'] = unit['id'] in user_units
    
    if request.method == 'POST':
        name = request.form.get('name')
        new_email = request.form.get('email')
        cpf = request.form.get('cpf')
        phone = request.form.get('phone')
        role = request.form.get('role')
        is_superuser = 1 if 'is_superuser' in request.form else 0
        is_active = 1 if 'is_active' in request.form else 0
        
        # Verificar se o email está sendo alterado
        if new_email != user['email']:
            cursor.execute("SELECT id FROM user WHERE email = %s AND id != %s", (new_email, user_id))
            existing_user = cursor.fetchone()
            
            if existing_user:
                cursor.close()
                conn.close()
                flash('Este email já está cadastrado!', 'error')
                return render_template('admin/edit_user.html', user=user, units=units)
        
        try:
            # Atualizar dados do usuário
            cursor.execute(
                "UPDATE user SET name = %s, email = %s, cpf = %s, phone = %s, role = %s, is_superuser = %s, is_active = %s WHERE id = %s",
                (name, new_email, cpf, phone, role, is_superuser, is_active, user_id)
            )
            
            # Atualizar unidades (remover todas e adicionar selecionadas)
            cursor.execute("DELETE FROM user_unit WHERE user_id = %s", (user_id,))
            
            if not is_superuser:
                selected_units = request.form.getlist('units')
                if selected_units:
                    unit_values = [(user_id, int(unit_id)) for unit_id in selected_units]
                    cursor.executemany(
                        "INSERT INTO user_unit (user_id, unit_id) VALUES (%s, %s)",
                        unit_values
                    )
            
            conn.commit()
            flash('Usuário atualizado com sucesso!', 'success')
            return redirect(url_for('admin_users_list'))
            
        except Exception as e:
            conn.rollback()
            flash(f'Erro ao atualizar usuário: {str(e)}', 'error')
    
    cursor.close()
    conn.close()
    return render_template('admin/edit_user.html', user=user, units=units)

@app.route('/admin/users/<int:user_id>/delete', methods=['POST'])
@login_required
def admin_delete_user(user_id):
    if not current_user.is_superuser:
        flash('Acesso não autorizado!', 'error')
        return redirect(url_for('user_home'))
    
    # Não permitir que o usuário exclua a si mesmo
    if user_id == current_user.id:
        flash('Você não pode excluir seu próprio usuário!', 'error')
        return redirect(url_for('admin_users_list'))
    
    conn = get_db_connection()
    cursor = conn.cursor()
    
    try:
        cursor.execute("DELETE FROM user WHERE id = %s", (user_id,))
        conn.commit()
        flash('Usuário excluído com sucesso!', 'success')
    except Exception as e:
        conn.rollback()
        flash(f'Erro ao excluir usuário: {str(e)}', 'error')
    
    cursor.close()
    conn.close()
    return redirect(url_for('admin_users_list'))

# Rotas para Unidades (Admin)
@app.route('/admin/units')
@login_required
def admin_units_list():
    if not current_user.is_superuser:
        flash('Acesso não autorizado!', 'error')
        return redirect(url_for('user_home'))
    
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM unit ORDER BY name")
    units = cursor.fetchall()
    cursor.close()
    conn.close()
    
    return render_template('admin/units_list.html', units=units)

@app.route('/admin/units/create', methods=['GET', 'POST'])
@login_required
def admin_create_unit():
    if not current_user.is_superuser:
        flash('Acesso não autorizado!', 'error')
        return redirect(url_for('user_home'))
    
    if request.method == 'POST':
        name = request.form.get('name')
        address = request.form.get('address')
        phone = request.form.get('phone')
        is_active = 1 if 'is_active' in request.form else 0
        cashier_count = int(request.form.get('cashier_count', 1))
        
        conn = get_db_connection()
        cursor = conn.cursor()
        
        try:
            # Criar unidade
            cursor.execute(
                "INSERT INTO unit (name, address, phone, is_active) VALUES (%s, %s, %s, %s)",
                (name, address, phone, is_active)
            )
            unit_id = cursor.lastrowid
            
            # Criar caixas para a unidade
            for i in range(1, cashier_count + 1):
                cursor.execute(
                    "INSERT INTO cashier (unit_id, number, status) VALUES (%s, %s, %s)",
                    (unit_id, i, 'fechado')
                )
            
            conn.commit()
            flash('Unidade criada com sucesso!', 'success')
            return redirect(url_for('admin_units_list'))
            
        except Exception as e:
            conn.rollback()
            flash(f'Erro ao criar unidade: {str(e)}', 'error')
        
        cursor.close()
        conn.close()
    
    return render_template('admin/create_unit.html')

@app.route('/admin/units/<int:unit_id>/edit', methods=['GET', 'POST'])
@login_required
def admin_edit_unit(unit_id):
    if not current_user.is_superuser:
        flash('Acesso não autorizado!', 'error')
        return redirect(url_for('user_home'))
    
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM unit WHERE id = %s", (unit_id,))
    unit = cursor.fetchone()
    
    if not unit:
        cursor.close()
        conn.close()
        flash('Unidade não encontrada!', 'error')
        return redirect(url_for('admin_units_list'))
    
    if request.method == 'POST':
        name = request.form.get('name')
        address = request.form.get('address')
        phone = request.form.get('phone')
        is_active = 1 if 'is_active' in request.form else 0
        
        try:
            cursor.execute(
                "UPDATE unit SET name = %s, address = %s, phone = %s, is_active = %s WHERE id = %s",
                (name, address, phone, is_active, unit_id)
            )
            conn.commit()
            flash('Unidade atualizada com sucesso!', 'success')
            return redirect(url_for('admin_units_list'))
            
        except Exception as e:
            conn.rollback()
            flash(f'Erro ao atualizar unidade: {str(e)}', 'error')
    
    cursor.close()
    conn.close()
    return render_template('admin/edit_unit.html', unit=unit)

@app.route('/admin/units/<int:unit_id>/delete', methods=['POST'])
@login_required
def admin_delete_unit(unit_id):
    if not current_user.is_superuser:
        flash('Acesso não autorizado!', 'error')
        return redirect(url_for('user_home'))
    
    conn = get_db_connection()
    cursor = conn.cursor()
    
    try:
        cursor.execute("DELETE FROM unit WHERE id = %s", (unit_id,))
        conn.commit()
        flash('Unidade excluída com sucesso!', 'success')
    except Exception as e:
        conn.rollback()
        flash(f'Erro ao excluir unidade: {str(e)}', 'error')
    
    cursor.close()
    conn.close()
    return redirect(url_for('admin_units_list'))

# === Rotas de Usuário ===
@app.route('/user')
@login_required
def user_home():
    conn = get_db_connection()
    cursor = conn.cursor()
    
    if current_user.is_superuser:
        # Super usuários podem ver todas as unidades ativas
        cursor.execute("SELECT * FROM unit WHERE is_active = 1 ORDER BY name")
        units = cursor.fetchall()
    else:
        # Usuários normais só veem as unidades associadas a eles
        cursor.execute(
            "SELECT u.* FROM unit u "
            "JOIN user_unit uu ON u.id = uu.unit_id "
            "WHERE uu.user_id = %s AND u.is_active = 1 ORDER BY u.name",
            (current_user.id,)
        )
        units = cursor.fetchall()
    
    cursor.close()
    conn.close()
    return render_template('user/home.html', units=units)

@app.route('/user/unit/<int:unit_id>/cashiers')
@login_required
def user_cashiers(unit_id):
    conn = get_db_connection()
    cursor = conn.cursor()
    
    # Verificar se a unidade existe
    cursor.execute("SELECT * FROM unit WHERE id = %s", (unit_id,))
    unit = cursor.fetchone()
    
    if not unit:
        cursor.close()
        conn.close()
        flash('Unidade não encontrada!', 'error')
        return redirect(url_for('user_home'))
    
    # Verificar se o usuário tem acesso à unidade
    if not current_user.is_superuser:
        cursor.execute(
            "SELECT * FROM user_unit WHERE user_id = %s AND unit_id = %s",
            (current_user.id, unit_id)
        )
        has_access = cursor.fetchone() is not None
        
        if not has_access:
            cursor.close()
            conn.close()
            flash('Acesso não autorizado a esta unidade!', 'error')
            return redirect(url_for('user_home'))
    
    # Verificar se é para criar um novo caixa
    if request.args.get('create') == 'true' and current_user.is_superuser:
        # Obter o próximo número disponível para o caixa
        cursor.execute(
            "SELECT MAX(number) as last_number FROM cashier WHERE unit_id = %s",
            (unit_id,)
        )
        result = cursor.fetchone()
        next_number = 1 if not result or result['last_number'] is None else result['last_number'] + 1
        
        # Criar o novo caixa
        try:
            cursor.execute(
                "INSERT INTO cashier (unit_id, number, status) VALUES (%s, %s, %s)",
                (unit_id, next_number, 'fechado')
            )
            conn.commit()
            flash(f'Caixa {next_number} criado com sucesso!', 'success')
        except Exception as e:
            conn.rollback()
            flash(f'Erro ao criar caixa: {str(e)}', 'error')
    
    # Obter todos os caixas da unidade
    cursor.execute(
        "SELECT * FROM cashier WHERE unit_id = %s ORDER BY number",
        (unit_id,)
    )
    cashiers = cursor.fetchall()
    
    cursor.close()
    conn.close()
    return render_template('user/cashiers.html', unit=unit, cashiers=cashiers)

@app.route('/user/unit/<int:unit_id>/cashier/<int:cashier_id>/movements', methods=['GET', 'POST'])
@login_required
def user_movements(unit_id, cashier_id):
    conn = get_db_connection()
    cursor = conn.cursor()
    
    # Verificar se a unidade existe
    cursor.execute("SELECT * FROM unit WHERE id = %s", (unit_id,))
    unit = cursor.fetchone()
    
    if not unit:
        cursor.close()
        conn.close()
        flash('Unidade não encontrada!', 'error')
        return redirect(url_for('user_home'))
    
    # Verificar se o usuário tem acesso à unidade
    if not current_user.is_superuser:
        cursor.execute(
            "SELECT * FROM user_unit WHERE user_id = %s AND unit_id = %s",
            (current_user.id, unit_id)
        )
        has_access = cursor.fetchone() is not None
        
        if not has_access:
            cursor.close()
            conn.close()
            flash('Acesso não autorizado a esta unidade!', 'error')
            return redirect(url_for('user_home'))
    
    # Verificar se o caixa existe e pertence à unidade
    cursor.execute(
        "SELECT * FROM cashier WHERE id = %s AND unit_id = %s",
        (cashier_id, unit_id)
    )
    cashier = cursor.fetchone()
    
    if not cashier:
        cursor.close()
        conn.close()
        flash('Caixa não encontrado ou não pertence a esta unidade!', 'error')
        return redirect(url_for('user_cashiers', unit_id=unit_id))
    
    # Obter data para filtrar movimentos
    date_str = request.args.get('date')
    if date_str:
        try:
            date = datetime.strptime(date_str, '%Y-%m-%d')
        except ValueError:
            date = datetime.now()
    else:
        date = datetime.now()
    
    # Formatar a data para uso no template
    date_formatted = date.strftime('%Y-%m-%d')
    
    # Obter movimentos do dia
    start_date = datetime(date.year, date.month, date.day, 0, 0, 0)
    end_date = datetime(date.year, date.month, date.day, 23, 59, 59)
    
    cursor.execute(
        "SELECT m.*, pm.name as payment_method_name, pm.category as payment_method_category "
        "FROM movement m "
        "LEFT JOIN payment_method pm ON m.payment_method = pm.id "
        "WHERE m.cashier_id = %s AND m.created_at BETWEEN %s AND %s "
        "ORDER BY m.created_at DESC",
        (cashier_id, start_date, end_date)
    )
    movements = cursor.fetchall()
    
    # Obter métodos de pagamento
    cursor.execute("SELECT * FROM payment_method WHERE is_active = 1 ORDER BY name")
    payment_methods = cursor.fetchall()
    
    # Para o formulário de adição de movimentos
    if request.method == 'POST':
        movement_type = request.form.get('type')
        amount = float(request.form.get('amount'))
        payment_method_id = request.form.get('payment_method')
        description = request.form.get('description')
        payment_status = request.form.get('payment_status', 'realizado')
        coins_in = float(request.form.get('coins_in') or 0)
        coins_out = float(request.form.get('coins_out') or 0)
        client_name = request.form.get('client_name', '')
        document_number = request.form.get('document_number', '')
        
        # Se for saída, o status sempre é realizado
        if movement_type == 'saida':
            payment_status = 'realizado'
        
        try:
            cursor.execute(
                "INSERT INTO movement "
                "(cashier_id, type, amount, payment_method, description, payment_status, "
                "coins_in, coins_out, client_name, document_number, created_at) "
                "VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)",
                (cashier_id, movement_type, amount, payment_method_id, description, 
                 payment_status, coins_in, coins_out, client_name, document_number, datetime.now())
            )
            conn.commit()
            flash('Movimentação registrada com sucesso!', 'success')
            return redirect(url_for('user_movements', unit_id=unit_id, cashier_id=cashier_id, date=date_formatted))
            
        except Exception as e:
            conn.rollback()
            flash(f'Erro ao registrar movimentação: {str(e)}', 'error')
    
    cursor.close()
    conn.close()
    
    return render_template(
        'user/movements.html',
        unit=unit,
        cashier=cashier,
        movements=movements,
        payment_methods=payment_methods,
        date=date_formatted
    )

@app.route('/user/unit/<int:unit_id>/cashier/<int:cashier_id>/movement/<int:movement_id>/delete', methods=['POST'])
@login_required
def delete_movement(unit_id, cashier_id, movement_id):
    conn = get_db_connection()
    cursor = conn.cursor()
    
    # Verificar se a unidade existe
    cursor.execute("SELECT * FROM unit WHERE id = %s", (unit_id,))
    unit = cursor.fetchone()
    
    if not unit:
        cursor.close()
        conn.close()
        flash('Unidade não encontrada!', 'error')
        return redirect(url_for('user_home'))
    
    # Verificar se o usuário tem acesso à unidade
    if not current_user.is_superuser:
        cursor.execute(
            "SELECT * FROM user_unit WHERE user_id = %s AND unit_id = %s",
            (current_user.id, unit_id)
        )
        has_access = cursor.fetchone() is not None
        
        if not has_access:
            cursor.close()
            conn.close()
            flash('Acesso não autorizado a esta unidade!', 'error')
            return redirect(url_for('user_home'))
    
    # Verificar se o movimento existe e pertence ao caixa
    cursor.execute(
        "SELECT * FROM movement WHERE id = %s AND cashier_id = %s",
        (movement_id, cashier_id)
    )
    movement = cursor.fetchone()
    
    if not movement:
        cursor.close()
        conn.close()
        flash('Movimento não encontrado ou não pertence a este caixa!', 'error')
        return redirect(url_for('user_movements', unit_id=unit_id, cashier_id=cashier_id))
    
    # Obter a data do movimento para redirecionar de volta com o filtro correto
    movement_date = movement['created_at'].strftime('%Y-%m-%d')
    
    try:
        cursor.execute("DELETE FROM movement WHERE id = %s", (movement_id,))
        conn.commit()
        flash('Movimento excluído com sucesso!', 'success')
    except Exception as e:
        conn.rollback()
        flash(f'Erro ao excluir movimento: {str(e)}', 'error')
    
    cursor.close()
    conn.close()
    return redirect(url_for('user_movements', unit_id=unit_id, cashier_id=cashier_id, date=movement_date))

# Página 404
@app.errorhandler(404)
def page_not_found(e):
    return render_template('404.html'), 404

# Iniciar o aplicativo
if __name__ == '__main__':
    app.run(debug=True)