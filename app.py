from flask import Flask, render_template, request, redirect, url_for, flash, jsonify
from flask_login import LoginManager, login_user, logout_user, login_required, current_user
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import datetime, timedelta, date
import calendar
import os
import pymysql
from reports import reports
from pymysql.cursors import DictCursor
from config import Config
from flask_mail import Mail, Message
from decimal import Decimal
from datetime import datetime, timezone, timedelta



# Inicialização do app
app = Flask(__name__)
app.secret_key = os.getenv('SECRET_KEY')
app.config.from_object(Config)
app.register_blueprint(reports)
# Configuração do Flask-Login
login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'login'

# Define o fuso horário brasileiro (UTC-3)
BRAZIL_TIMEZONE = timezone(timedelta(hours=-3))

# Função para obter o datetime atual no horário brasileiro
def get_brazil_datetime():
    return datetime.now(timezone.utc).astimezone(BRAZIL_TIMEZONE).replace(tzinfo=None)

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
        template = 'auth/reset_password_email.html'  # Ajustando o caminho
    else:
        subject = 'Casa do Biscoito - Boas-vindas e Senha Temporária'
        template = 'auth/new_user_email.html'  # Ajustando o caminho
    
    msg = Message(
        subject,
        recipients=[email]
    )
    
    # Remover referência à imagem do template ou anexá-la corretamente
    # Opção 1: Simplesmente render o template sem a imagem
    msg.html = render_template(template, 
                              name=name, 
                              password=password,
                              login_url=url_for('login', _external=True))
    
    try:
        mail.send(msg)
        return True
    except Exception as e:
        # Melhorando o log de erro para debugging
        print(f"Erro detalhado ao enviar e-mail: {str(e)}")
        # Se o envio de e-mail falhar, ainda podemos considerar o usuário criado
        # mas retornamos False para que a aplicação saiba que o e-mail não foi enviado
        return False

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
        is_active BOOLEAN DEFAULT TRUE,
        parent_id INT NULL,
        is_default BOOLEAN DEFAULT FALSE,
        FOREIGN KEY (parent_id) REFERENCES payment_method(id) ON DELETE CASCADE
    )
    """)
    
    # Tabela de movimentações
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS movement (
        id INT AUTO_INCREMENT PRIMARY KEY,
        cashier_id INT,
        type ENUM('entrada', 'saida', 'estorno', 'despesa_loja') NOT NULL DEFAULT 'entrada',
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
    
    # Tabela para valor base mensal do caixa
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS monthly_base_amount (
        id INT AUTO_INCREMENT PRIMARY KEY,
        unit_id INT NOT NULL,
        month INT NOT NULL,
        year INT NOT NULL,
        amount DECIMAL(10,2) NOT NULL DEFAULT 0,
        created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
        updated_at DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
        FOREIGN KEY (unit_id) REFERENCES unit(id) ON DELETE CASCADE,
        UNIQUE KEY unique_monthly_base (unit_id, month, year)
    )
    """)
    
    # Nova tabela para valores base por caixa
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS cashier_base_values (
        id INT AUTO_INCREMENT PRIMARY KEY,
        cashier_id INT NOT NULL,
        month INT NOT NULL,
        year INT NOT NULL,
        amount DECIMAL(10,2) NOT NULL DEFAULT 0,
        created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
        updated_at DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
        FOREIGN KEY (cashier_id) REFERENCES cashier(id) ON DELETE CASCADE,
        UNIQUE KEY unique_cashier_base (cashier_id, month, year)
    )
    """)
    
    # Tabela para controle de moedas do caixa
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS coins_control (
        id INT AUTO_INCREMENT PRIMARY KEY,
        unit_id INT NOT NULL,
        total_amount DECIMAL(10,2) NOT NULL DEFAULT 0,
        last_deposit_date DATETIME NULL,
        created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
        updated_at DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
        FOREIGN KEY (unit_id) REFERENCES unit(id) ON DELETE CASCADE
    )
    """)
    
    # Tabela para histórico de moedas
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS coins_history (
        id INT AUTO_INCREMENT PRIMARY KEY,
        unit_id INT NOT NULL,
        amount DECIMAL(10,2) NOT NULL,
        action ENUM('add', 'deposit', 'exchange') NOT NULL,
        created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (unit_id) REFERENCES unit(id) ON DELETE CASCADE
    )
    """)
    
    # Tabela de redefinição de senha
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS password_reset (
        id INT AUTO_INCREMENT PRIMARY KEY,
        user_id INT NOT NULL,
        token VARCHAR(255) NOT NULL,
        expires DATETIME NOT NULL,
        used BOOLEAN DEFAULT FALSE,
        created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (user_id) REFERENCES user(id) ON DELETE CASCADE
    )
    """)
    
    # Tabela para categorias de despesas da loja
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS expense_category (
        id INT AUTO_INCREMENT PRIMARY KEY,
        name VARCHAR(100) NOT NULL,
        type ENUM('fixa', 'extra', 'socio', 'fornecedor') NOT NULL,
        is_active BOOLEAN DEFAULT TRUE,
        created_at DATETIME DEFAULT CURRENT_TIMESTAMP
    )
    """)
    
    # Tabela para registrar as despesas da loja
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS store_expense (
        id INT AUTO_INCREMENT PRIMARY KEY,
        movement_id INT NOT NULL,
        category_id INT NOT NULL,
        description TEXT,
        created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (movement_id) REFERENCES movement(id) ON DELETE CASCADE,
        FOREIGN KEY (category_id) REFERENCES expense_category(id)
    )
    """)
    
    # Tabela para controle do valor Z (PDV)
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS pdv_z_values (
        id INT AUTO_INCREMENT PRIMARY KEY,
        cashier_id INT NOT NULL,
        z_value DECIMAL(10,2) NOT NULL DEFAULT 0,
        date DATE NOT NULL,
        created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
        updated_at DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
        FOREIGN KEY (cashier_id) REFERENCES cashier(id) ON DELETE CASCADE,
        UNIQUE KEY unique_z_value (cashier_id, date)
    )
    """)
    
    # Tabela para registrar devoluções e estornos (devo)
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS devo_values (
        id INT AUTO_INCREMENT PRIMARY KEY,
        cashier_id INT NOT NULL,
        devo_value DECIMAL(10,2) NOT NULL DEFAULT 0,
        date DATE NOT NULL,
        reason TEXT,
        created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
        updated_at DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
        FOREIGN KEY (cashier_id) REFERENCES cashier(id) ON DELETE CASCADE,
        UNIQUE KEY unique_devo_value (cashier_id, date)
    )
    """)
    
    # Tabela para controle do pote
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS pot_control (
        id INT AUTO_INCREMENT PRIMARY KEY,
        unit_id INT NOT NULL,
        amount DECIMAL(10,2) NOT NULL DEFAULT 0,
        created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
        updated_at DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
        FOREIGN KEY (unit_id) REFERENCES unit(id) ON DELETE CASCADE,
        UNIQUE KEY unique_pot_control (unit_id)
    )
    """)
    
    # Inserir métodos de pagamento padrão se não existirem
    cursor.execute("SELECT COUNT(*) as count FROM payment_method")
    count = cursor.fetchone()['count']
    
    if count == 0:
        payment_methods = [
            ('Débito', 'debito', True, True, None),
            ('Crédito', 'credito', True, True, None),
            ('Ticket', 'ticket', True, True, None),
            ('Dinheiro', 'dinheiro', True, True, None),
            ('PIX', 'pix', True, True, None)
        ]
        cursor.executemany(
            "INSERT INTO payment_method (name, category, is_active, is_default, parent_id) VALUES (%s, %s, %s, %s, %s)",
            payment_methods
        )
    
    # Verificar se existem categorias de despesa
    cursor.execute("SELECT COUNT(*) as count FROM expense_category")
    expense_count = cursor.fetchone()['count']
    
    if expense_count == 0:
        expense_categories = [
            ('Água', 'fixa'),
            ('Luz', 'fixa'),
            ('Internet', 'fixa'),
            ('Passagem Funcionário', 'fixa'),
            ('Cartão de Crédito da Empresa', 'fixa'),
            ('Cartão de Débito da Empresa', 'fixa'),
            ('Sócio A', 'socio'),
            ('Sócio B', 'socio'),
            ('Fornecedor A', 'fornecedor'),
            ('Fornecedor B', 'fornecedor'),
            ('Extras', 'extra')
        ]
        cursor.executemany(
            "INSERT INTO expense_category (name, type) VALUES (%s, %s)",
            expense_categories
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
            # Corrigindo o nome da tabela para "user" e removendo o campo created_at
            cursor.execute(
                "INSERT INTO user (name, email, password_hash, cpf, phone, role, is_superuser, is_active, last_login) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)",
                (name, email, password_hash, cpf, phone, role, is_superuser, 1, get_brazil_datetime())
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
        # Corrigido para usar "user" em vez de "users"
        cursor.execute("SELECT * FROM user WHERE email = %s", (email,))
        user = cursor.fetchone()
        
        if user:
            # Gerar um token único para redefinição
            import secrets
            token = secrets.token_hex(16)
            expires = get_brazil_datetime() + timedelta(hours=24)
            
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
    
    if not reset_data or reset_data['expires'] < get_brazil_datetime():
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
        
        # Atualizar senha do usuário - Corrigido para usar "user" em vez de "users"
        cursor.execute(
            "UPDATE user SET password_hash = %s WHERE id = %s",
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

# Rota para configurar valor base mensal do caixa
@app.route('/admin/unit/<int:unit_id>/monthly_base', methods=['GET', 'POST'])
@login_required
def admin_monthly_base(unit_id):
    if not current_user.is_superuser:
        flash('Acesso não autorizado!', 'error')
        return redirect(url_for('user_home'))
    
    conn = get_db_connection()
    cursor = conn.cursor()
    
    # Obter a unidade
    cursor.execute("SELECT * FROM unit WHERE id = %s", (unit_id,))
    unit = cursor.fetchone()
    
    if not unit:
        cursor.close()
        conn.close()
        flash('Unidade não encontrada!', 'error')
        return redirect(url_for('admin_units_list'))
    
    today = get_brazil_datetime()
    current_month = today.month
    current_year = today.year
    
    # Verificar se já existe um valor base para o mês atual
    cursor.execute(
        "SELECT * FROM monthly_base_amount WHERE unit_id = %s AND month = %s AND year = %s",
        (unit_id, current_month, current_year)
    )
    monthly_base = cursor.fetchone()
    
    if request.method == 'POST':
        amount = float(request.form.get('amount', 0))
        
        if monthly_base:
            # Atualizar valor existente
            cursor.execute(
                "UPDATE monthly_base_amount SET amount = %s WHERE id = %s",
                (amount, monthly_base['id'])
            )
        else:
            # Criar novo registro
            cursor.execute(
                "INSERT INTO monthly_base_amount (unit_id, month, year, amount) VALUES (%s, %s, %s, %s)",
                (unit_id, current_month, current_year, amount)
            )
        
        conn.commit()
        flash('Valor base mensal atualizado com sucesso!', 'success')
        return redirect(url_for('admin_units_list'))
    
    # Obter histórico de valores base
    cursor.execute(
        "SELECT month, year, amount FROM monthly_base_amount WHERE unit_id = %s ORDER BY year DESC, month DESC",
        (unit_id,)
    )
    base_history = cursor.fetchall()
    
    cursor.close()
    conn.close()
    
    return render_template(
        'admin/monthly_base.html',
        unit=unit,
        monthly_base=monthly_base,
        current_month=current_month,
        current_year=current_year,
        month_name=calendar.month_name[current_month],
        base_history=base_history,
        calendar=calendar
    )

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
            
            # Criar o Caixa Financeiro (número = 0)
            cursor.execute(
                "INSERT INTO cashier (unit_id, number, status) VALUES (%s, %s, %s)",
                (unit_id, 0, 'aberto')
            )
            
            # Criar caixas para a unidade
            for i in range(1, cashier_count + 1):
                cursor.execute(
                    "INSERT INTO cashier (unit_id, number, status) VALUES (%s, %s, %s)",
                    (unit_id, i, 'fechado')
                )
            
            # Criar controle de moedas para a unidade
            cursor.execute(
                "INSERT INTO coins_control (unit_id, total_amount) VALUES (%s, %s)",
                (unit_id, 0)
            )
            
            # Inicializar um valor para o pote
            cursor.execute(
                "INSERT INTO pot_control (unit_id, amount) VALUES (%s, %s)",
                (unit_id, 0)
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

# Rota para gerenciar controle de moedas
@app.route('/user/unit/<int:unit_id>/coins', methods=['GET', 'POST'])
@login_required
def user_coins_control(unit_id):
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
    
    # Obter o controle de moedas atual
    cursor.execute("SELECT * FROM coins_control WHERE unit_id = %s", (unit_id,))
    coins_control = cursor.fetchone()
    
    if not coins_control:
        # Criar novo controle de moedas se não existir
        cursor.execute(
            "INSERT INTO coins_control (unit_id) VALUES (%s)",
            (unit_id,)
        )
        conn.commit()
        cursor.execute("SELECT * FROM coins_control WHERE unit_id = %s", (unit_id,))
        coins_control = cursor.fetchone()
    
    # Obter histórico de moedas
    cursor.execute(
        "SELECT * FROM coins_history WHERE unit_id = %s ORDER BY created_at DESC LIMIT 50",
        (unit_id,)
    )
    coins_history = cursor.fetchall()
    
    if request.method == 'POST':
        action = request.form.get('action')
        
        if action == 'add':
            amount = float(request.form.get('amount', 0))
            # Corrigir o problema de tipos convertendo para Decimal
            new_total = coins_control['total_amount'] + Decimal(str(amount))
            
            cursor.execute(
                "UPDATE coins_control SET total_amount = %s, updated_at = %s WHERE id = %s",
                (new_total, get_brazil_datetime(), coins_control['id'])
            )
            
            cursor.execute(
                "INSERT INTO coins_history (unit_id, amount, action) VALUES (%s, %s, %s)",
                (unit_id, amount, 'add')
            )
            
            conn.commit()
            flash('Moedas adicionadas com sucesso!', 'success')
            
        elif action == 'deposit':
            cursor.execute(
                "UPDATE coins_control SET total_amount = 0, last_deposit_date = %s, updated_at = %s WHERE id = %s",
                (get_brazil_datetime(), get_brazil_datetime(), coins_control['id'])
            )
            
            cursor.execute(
                "INSERT INTO coins_history (unit_id, amount, action) VALUES (%s, %s, %s)",
                (unit_id, coins_control['total_amount'], 'deposit')
            )
            
            conn.commit()
            flash('Depósito de moedas registrado com sucesso!', 'success')
            
        return redirect(url_for('user_coins_control', unit_id=unit_id))
    
    cursor.close()
    conn.close()
    
    return render_template(
        'user/coins_control.html',
        unit=unit,
        coins_control=coins_control,
        coins_history=coins_history
    )

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
    
    # Verificar se o Caixa Financeiro existe e criar se não existir
    cursor.execute(
        "SELECT * FROM cashier WHERE unit_id = %s AND number = 0",
        (unit_id,)
    )
    financial_cashier = cursor.fetchone()
    financial_cashier_id = None
    
    if financial_cashier:
        financial_cashier_id = financial_cashier['id']
    else:
        # Criar o Caixa Financeiro
        try:
            cursor.execute(
                "INSERT INTO cashier (unit_id, number, status) VALUES (%s, %s, %s)",
                (unit_id, 0, 'aberto')
            )
            conn.commit()
            financial_cashier_id = cursor.lastrowid
        except Exception as e:
            conn.rollback()
            flash(f'Erro ao criar Caixa Financeiro: {str(e)}', 'error')
    
    # Verificar se é para criar um novo caixa
    if request.args.get('create') == 'true' and current_user.is_superuser:
        # Obter o próximo número disponível para o caixa
        cursor.execute(
            "SELECT MAX(number) as last_number FROM cashier WHERE unit_id = %s AND number > 0",
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
    
    # Obter valor base mensal da unidade para o mês atual
    today = get_brazil_datetime()
    cursor.execute(
        "SELECT * FROM monthly_base_amount WHERE unit_id = %s AND month = %s AND year = %s",
        (unit_id, today.month, today.year)
    )
    monthly_base = cursor.fetchone()
    base_amount = monthly_base['amount'] if monthly_base else 0
    
    # Obter o controle de moedas
    cursor.execute("SELECT * FROM coins_control WHERE unit_id = %s", (unit_id,))
    coins_control = cursor.fetchone()
    coins_amount = coins_control['total_amount'] if coins_control else 0
    
    # Criar controle de moedas se não existir
    if not coins_control:
        try:
            cursor.execute(
                "INSERT INTO coins_control (unit_id, total_amount) VALUES (%s, %s)",
                (unit_id, 0)
            )
            conn.commit()
            coins_amount = 0
        except Exception as e:
            conn.rollback()
            flash(f'Erro ao criar controle de moedas: {str(e)}', 'error')
    
    # Obter totais de movimentos do dia para cada caixa
    start_date = datetime(today.year, today.month, today.day, 0, 0, 0)
    end_date = datetime(today.year, today.month, today.day, 23, 59, 59)
    
    cashier_totals = {}
    for cashier in cashiers:
        cursor.execute(
            "SELECT SUM(CASE WHEN type = 'entrada' AND payment_status = 'realizado' THEN amount ELSE 0 END) as total_entrada, "
            "SUM(CASE WHEN type = 'saida' OR type = 'despesa_loja' OR type = 'estorno' THEN amount ELSE 0 END) as total_saida "
            "FROM movement "
            "WHERE cashier_id = %s AND created_at BETWEEN %s AND %s",
            (cashier['id'], start_date, end_date)
        )
        result = cursor.fetchone()
        
        if result:
            entrada = result['total_entrada'] or 0
            saida = result['total_saida'] or 0
            cashier_totals[cashier['id']] = {
                'entrada': entrada,
                'saida': saida,
                'saldo': entrada - saida
            }
        else:
            cashier_totals[cashier['id']] = {'entrada': 0, 'saida': 0, 'saldo': 0}
    
    # Obter totais gerais
    cursor.execute(
        "SELECT SUM(CASE WHEN type = 'entrada' AND payment_status = 'realizado' THEN amount ELSE 0 END) as total_entrada, "
        "SUM(CASE WHEN type = 'saida' OR type = 'despesa_loja' OR type = 'estorno' THEN amount ELSE 0 END) as total_saida "
        "FROM movement "
        "WHERE cashier_id IN (SELECT id FROM cashier WHERE unit_id = %s) "
        "AND created_at BETWEEN %s AND %s",
        (unit_id, start_date, end_date)
    )
    totals = cursor.fetchone()
    
    total_entrada = totals['total_entrada'] or 0
    total_saida = totals['total_saida'] or 0
    saldo_dia = total_entrada - total_saida
    
    # Calcular saldo do caixa financeiro
    cursor.execute(
        "SELECT SUM(CASE WHEN type = 'entrada' AND payment_status = 'realizado' THEN amount ELSE 0 END) as total_entrada, "
        "SUM(CASE WHEN type = 'saida' OR type = 'despesa_loja' OR type = 'estorno' THEN amount ELSE 0 END) as total_saida "
        "FROM movement "
        "WHERE cashier_id IN (SELECT id FROM cashier WHERE unit_id = %s)",
        (unit_id,)
    )
    all_time_totals = cursor.fetchone()
    
    all_time_entrada = all_time_totals['total_entrada'] or 0
    all_time_saida = all_time_totals['total_saida'] or 0
    financial_balance = all_time_entrada - all_time_saida
    
    cursor.close()
    conn.close()
    
    return render_template(
        'user/cashiers.html',
        unit=unit,
        cashiers=cashiers,
        cashier_totals=cashier_totals,
        total_entrada=total_entrada,
        total_saida=total_saida,
        saldo_dia=saldo_dia,
        base_amount=base_amount,
        coins_amount=coins_amount,
        financial_balance=financial_balance,
        financial_cashier_id=financial_cashier_id
    )

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
    
    # Verificar se é o Caixa Financeiro (número 0)
    is_financial_cashier = cashier['number'] == 0
    
    # Obter data para filtrar movimentos
    date_str = request.args.get('date')
    if date_str:
        try:
            date_obj = datetime.strptime(date_str, '%Y-%m-%d')
        except ValueError:
            date_obj = get_brazil_datetime()  # Usando horário do Brasil
    else:
        date_obj = get_brazil_datetime()  # Usando horário do Brasil
    
    # Formatar a data para uso no template
    date_formatted = date_obj.strftime('%Y-%m-%d')
    
    # Obter movimentos do dia
    start_date = datetime(date_obj.year, date_obj.month, date_obj.day, 0, 0, 0)
    end_date = datetime(date_obj.year, date_obj.month, date_obj.day, 23, 59, 59)
    date_obj_date = date_obj.date()
    
    cursor.execute(
        "SELECT m.*, pm.name as payment_method_name, pm.category as payment_method_category "
        "FROM movement m "
        "LEFT JOIN payment_method pm ON m.payment_method = pm.id "
        "WHERE m.cashier_id = %s AND m.created_at BETWEEN %s AND %s "
        "ORDER BY m.created_at DESC",
        (cashier_id, start_date, end_date)
    )
    movements = cursor.fetchall()
    
    # Obter métodos de pagamento principais
    cursor.execute(
        "SELECT * FROM payment_method WHERE parent_id IS NULL AND is_active = 1 ORDER BY name"
    )
    payment_methods_main = cursor.fetchall()
    
    # Obter todos os métodos de pagamento
    cursor.execute("SELECT * FROM payment_method WHERE is_active = 1 ORDER BY name")
    payment_methods = cursor.fetchall()
    
    # Obter categorias de despesas da loja
    cursor.execute("SELECT * FROM expense_category WHERE is_active = 1 ORDER BY type, name")
    expense_categories = cursor.fetchall()
    
    # Obter valor base mensal da unidade
    cursor.execute(
        "SELECT * FROM monthly_base_amount WHERE unit_id = %s AND month = %s AND year = %s",
        (unit_id, date_obj.month, date_obj.year)
    )
    monthly_base = cursor.fetchone()
    base_amount = monthly_base['amount'] if monthly_base else 0
    
    # Obter valor base específico para este caixa
    cursor.execute(
        "SELECT amount FROM cashier_base_values WHERE cashier_id = %s AND month = %s AND year = %s",
        (cashier_id, date_obj.month, date_obj.year)
    )
    cashier_base_result = cursor.fetchone()
    cashier_base_amount = cashier_base_result['amount'] if cashier_base_result else 0
    
    # Campo "devo" (devoluções/cancelamentos)
    cursor.execute(
        "SELECT SUM(devo_value) as total_devo FROM devo_values WHERE cashier_id = %s AND date = %s",
        (cashier_id, date_obj_date)
    )
    devo_result = cursor.fetchone()
    devo_total = devo_result['total_devo'] if devo_result and devo_result['total_devo'] else 0
    
    # Calcular vendas totais do dia (Campo T)
    cursor.execute(
        "SELECT SUM(amount) as total_t FROM movement WHERE cashier_id = %s AND type = 'entrada' AND payment_status = 'realizado' AND created_at BETWEEN %s AND %s",
        (cashier_id, start_date, end_date)
    )
    t_result = cursor.fetchone()
    t_total = (t_result['total_t'] if t_result and t_result['total_t'] else 0) - devo_total
    
    # Obter valor Z (relatório do PDV)
    cursor.execute(
        "SELECT z_value FROM pdv_z_values WHERE cashier_id = %s AND date = %s",
        (cashier_id, date_obj_date)
    )
    z_result = cursor.fetchone()
    z_total = z_result['z_value'] if z_result and z_result['z_value'] else 0
    
    # Calcular diferença (T - Z)
    dif_total = t_total - z_total
    
    # Obter valor do pote (apenas para Caixa Financeiro)
    pot_amount = 0
    if is_financial_cashier:
        cursor.execute("SELECT amount FROM pot_control WHERE unit_id = %s", (unit_id,))
        pot_result = cursor.fetchone()
        pot_amount = pot_result['amount'] if pot_result else 0
    
    # Para o formulário de adição de movimentos
    if request.method == 'POST':
        # Se for uma atualização do valor "devo"
        if 'devo_value' in request.form:
            devo_value = float(request.form.get('devo_value', 0))
            reason = request.form.get('devo_reason', '')
            
            cursor.execute(
                "INSERT INTO devo_values (cashier_id, devo_value, date, reason) VALUES (%s, %s, %s, %s) "
                "ON DUPLICATE KEY UPDATE devo_value = %s, reason = %s",
                (cashier_id, devo_value, date_obj_date, reason, devo_value, reason)
            )
            conn.commit()
            
            flash('Valor de cancelamento registrado com sucesso!', 'success')
            return redirect(url_for('user_movements', unit_id=unit_id, cashier_id=cashier_id, date=date_formatted))
        
        # Se for uma atualização do valor Z
        elif 'z_value' in request.form:
            z_value = float(request.form.get('z_value', 0))
            
            cursor.execute(
                "INSERT INTO pdv_z_values (cashier_id, z_value, date) VALUES (%s, %s, %s) "
                "ON DUPLICATE KEY UPDATE z_value = %s",
                (cashier_id, z_value, date_obj_date, z_value)
            )
            conn.commit()
            
            flash('Valor Z atualizado com sucesso!', 'success')
            return redirect(url_for('user_movements', unit_id=unit_id, cashier_id=cashier_id, date=date_formatted))
        
        # Se for uma atualização do pote
        elif 'pot_amount' in request.form:
            amount = float(request.form.get('pot_amount', 0))
            
            cursor.execute(
                "INSERT INTO pot_control (unit_id, amount) VALUES (%s, %s) "
                "ON DUPLICATE KEY UPDATE amount = %s",
                (unit_id, amount, amount)
            )
            conn.commit()
            
            flash('Valor do Pote atualizado com sucesso!', 'success')
            return redirect(url_for('user_movements', unit_id=unit_id, cashier_id=cashier_id, date=date_formatted))
        
        # Caso padrão: registro de movimentação
        movement_type = request.form.get('type')
        amount = float(request.form.get('amount'))
        payment_method_id = request.form.get('payment_method')
        description = request.form.get('description', '')
        payment_status = request.form.get('payment_status', 'realizado')
        
        # Para o Caixa Financeiro - tratamento especial para entradas
        if is_financial_cashier and movement_type == 'entrada':
            entry_type = request.form.get('entry_type', 'dinheiro')
            description = f"{entry_type.capitalize()}: {description}"
        
        # Para despesas da loja, obter a categoria
        expense_category_id = None
        if movement_type == 'despesa_loja':
            expense_category_id = request.form.get('expense_category')
            if not expense_category_id:
                cursor.close()
                conn.close()
                flash('Categoria de despesa é obrigatória!', 'error')
                return redirect(url_for('user_movements', unit_id=unit_id, cashier_id=cashier_id, date=date_formatted))
        
        # Para estorno, o status sempre é realizado
        if movement_type == 'estorno':
            payment_status = 'realizado'
        
        # Valores padrão para campos específicos
        coins_in = float(request.form.get('coins_in') or 0)
        coins_out = float(request.form.get('coins_out') or 0)
        client_name = request.form.get('client_name', '')
        document_number = request.form.get('document_number', '')
        
        try:
            # MODIFICAÇÃO AQUI: Usar a data selecionada pelo usuário, mas com a hora atual do BRASIL
            current_brazil_time = get_brazil_datetime().time()
            movement_datetime = datetime.combine(date_obj_date, current_brazil_time)
            
            # Inserir movimento com a data selecionada
            cursor.execute(
                "INSERT INTO movement "
                "(cashier_id, type, amount, payment_method, description, payment_status, "
                "coins_in, coins_out, client_name, document_number, created_at) "
                "VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)",
                (cashier_id, movement_type, amount, payment_method_id, description, 
                 payment_status, coins_in, coins_out, client_name, document_number, movement_datetime)
            )
            movement_id = cursor.lastrowid
            
            # Se for despesa da loja, registrar na tabela específica
            if movement_type == 'despesa_loja' and expense_category_id:
                cursor.execute(
                    "INSERT INTO store_expense (movement_id, category_id, description) "
                    "VALUES (%s, %s, %s)",
                    (movement_id, expense_category_id, description)
                )
            
            # Se for dinheiro (moedas), atualizar o controle de moedas
            if payment_method_id and (coins_in > 0 or coins_out > 0):
                cursor.execute("SELECT category FROM payment_method WHERE id = %s", (payment_method_id,))
                payment_method = cursor.fetchone()
                
                if payment_method and payment_method['category'] == 'dinheiro':
                    # Verificar se já existe controle de moedas para esta unidade
                    cursor.execute("SELECT * FROM coins_control WHERE unit_id = %s", (unit_id,))
                    coins_control = cursor.fetchone()
                    
                    if not coins_control:
                        # Criar um novo controle
                        cursor.execute(
                            "INSERT INTO coins_control (unit_id, total_amount) VALUES (%s, %s)",
                            (unit_id, coins_in - coins_out)
                        )
                    else:
                        # Converter para decimal para evitar o erro de tipo
                        from decimal import Decimal
                        new_total = coins_control['total_amount'] + Decimal(str(coins_in)) - Decimal(str(coins_out))
                        cursor.execute(
                            "UPDATE coins_control SET total_amount = %s, updated_at = %s WHERE id = %s",
                            (new_total, get_brazil_datetime(), coins_control['id'])  # Usar horário do Brasil
                        )
                        
                        # Registrar no histórico se houver mudança
                        if coins_in > 0 or coins_out > 0:
                            cursor.execute(
                                "INSERT INTO coins_history (unit_id, amount, action) VALUES (%s, %s, %s)",
                                (unit_id, coins_in - coins_out, 'add')
                            )
            
            conn.commit()
            flash('Movimentação registrada com sucesso!', 'success')
            return redirect(url_for('user_movements', unit_id=unit_id, cashier_id=cashier_id, date=date_formatted))
            
        except Exception as e:
            conn.rollback()
            flash(f'Erro ao registrar movimentação: {str(e)}', 'error')
    
    # Calcular saldos e totais
    total_entrada = 0
    total_saida = 0
    total_estorno = 0
    total_despesa = 0
    
    for mov in movements:
        if mov['type'] == 'entrada' and mov['payment_status'] == 'realizado':
            total_entrada += mov['amount']
        elif mov['type'] == 'saida':
            total_saida += mov['amount']
        elif mov['type'] == 'estorno':
            total_estorno += mov['amount']
        elif mov['type'] == 'despesa_loja':
            total_despesa += mov['amount']
    
    # Obter o saldo do caixa financeiro
    cursor.execute(
        "SELECT SUM(CASE WHEN type = 'entrada' AND payment_status = 'realizado' THEN amount ELSE 0 END) as total_entrada, "
        "SUM(CASE WHEN type = 'saida' OR type = 'despesa_loja' OR type = 'estorno' THEN amount ELSE 0 END) as total_saida "
        "FROM movement "
        "WHERE cashier_id IN (SELECT id FROM cashier WHERE unit_id = %s) "
        "AND created_at BETWEEN %s AND %s",
        (unit_id, start_date, end_date)
    )
    financial_result = cursor.fetchone()
    
    financial_balance = 0
    if financial_result:
        financial_balance = (financial_result['total_entrada'] or 0) - (financial_result['total_saida'] or 0)
    
    # Obter saldos de cartões do dia para exibir no resumo
    cursor.execute(
        "SELECT pm.category, SUM(m.amount) as total "
        "FROM movement m "
        "JOIN payment_method pm ON m.payment_method = pm.id "
        "WHERE m.cashier_id = %s AND m.type = 'entrada' AND m.payment_status = 'realizado' "
        "AND m.created_at BETWEEN %s AND %s "
        "GROUP BY pm.category",
        (cashier_id, start_date, end_date)
    )
    payment_category_totals = {}
    payment_results = cursor.fetchall()
    
    for result in payment_results:
        payment_category_totals[result['category']] = result['total']
    
    # Obter dados de moedas
    cursor.execute("SELECT total_amount FROM coins_control WHERE unit_id = %s", (unit_id,))
    coins_result = cursor.fetchone()
    coins_total = coins_result['total_amount'] if coins_result else 0
    
    cursor.close()
    conn.close()
    
    return render_template(
        'user/movements.html',
        unit=unit,
        cashier=cashier,
        movements=movements,
        payment_methods=payment_methods,
        payment_methods_main=payment_methods_main,
        expense_categories=expense_categories,
        date=date_formatted,
        total_entrada=total_entrada,
        total_saida=total_saida,
        total_estorno=total_estorno,
        total_despesa=total_despesa,
        financial_balance=financial_balance,
        base_amount=base_amount,
        cashier_base_amount=cashier_base_amount,
        devo_total=devo_total,
        t_total=t_total,
        z_total=z_total,
        dif_total=dif_total,
        pot_amount=pot_amount,
        is_financial_cashier=is_financial_cashier,
        payment_category_totals=payment_category_totals,
        coins_total=coins_total
    )

@app.route('/user/profile', methods=['GET', 'POST'])
@login_required
def user_edit_profile():
    """
    Rota para edição do perfil do usuário logado.
    Permite alterar nome, email, CPF, telefone e senha.
    """
    # Obter os dados atuais do usuário
    user_id = current_user.id
    
    conn = get_db_connection()
    cursor = conn.cursor()
    
    try:
        if request.method == 'POST':
            # Obter dados do formulário
            name = request.form.get('name')
            email = request.form.get('email')
            cpf = request.form.get('cpf')
            phone = request.form.get('phone')
            
            # Verificar se o email existe (caso tenha mudado)
            if email != current_user.email:
                cursor.execute("SELECT id FROM user WHERE email = %s AND id != %s", (email, user_id))
                existing_user = cursor.fetchone()
                
                if existing_user:
                    flash('Este email já está cadastrado por outro usuário!', 'error')
                    return redirect(url_for('user_edit_profile'))
            
            # Atualizar dados básicos
            cursor.execute(
                "UPDATE user SET name = %s, email = %s, cpf = %s, phone = %s WHERE id = %s",
                (name, email, cpf, phone, user_id)
            )
            
            # Verificar se há alteração de senha
            current_password = request.form.get('current_password')
            new_password = request.form.get('new_password')
            confirm_password = request.form.get('confirm_password')
            
            if current_password and new_password and confirm_password:
                # Verificar se a senha atual está correta
                cursor.execute("SELECT password_hash FROM user WHERE id = %s", (user_id,))
                user_data = cursor.fetchone()
                
                if check_password_hash(user_data['password_hash'], current_password):
                    if new_password == confirm_password:
                        # Atualizar senha
                        password_hash = generate_password_hash(new_password)
                        cursor.execute(
                            "UPDATE user SET password_hash = %s WHERE id = %s",
                            (password_hash, user_id)
                        )
                        flash('Senha atualizada com sucesso!', 'success')
                    else:
                        flash('A nova senha e a confirmação não coincidem!', 'error')
                        conn.rollback()
                        cursor.close()
                        conn.close()
                        return redirect(url_for('user_edit_profile'))
                else:
                    flash('Senha atual incorreta!', 'error')
                    conn.rollback()
                    cursor.close()
                    conn.close()
                    return redirect(url_for('user_edit_profile'))
            
            conn.commit()
            flash('Perfil atualizado com sucesso!', 'success')
            
            # Atualizar objeto do usuário atual
            current_user.name = name
            current_user.email = email
            current_user.cpf = cpf
            current_user.phone = phone
            
            return redirect(url_for('index'))
        
        cursor.close()
        conn.close()
        
        return render_template('user/edit_profile.html')
    
    except Exception as e:
        conn.rollback()
        cursor.close()
        conn.close()
        flash(f'Erro ao atualizar perfil: {str(e)}', 'error')
        return redirect(url_for('user_edit_profile'))
    
@app.route('/user/unit/<int:unit_id>/monthly_base', methods=['GET', 'POST'])
@login_required
def user_monthly_base(unit_id):
    """
    Rota para configuração do valor base mensal por usuários comuns.
    """
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
    
    today = get_brazil_datetime()
    current_month = today.month
    current_year = today.year
    
    # Verificar se já existe um valor base para o mês atual
    cursor.execute(
        "SELECT * FROM monthly_base_amount WHERE unit_id = %s AND month = %s AND year = %s",
        (unit_id, current_month, current_year)
    )
    monthly_base = cursor.fetchone()
    
    # Obter valor do mês anterior para referência
    prev_month = current_month - 1 if current_month > 1 else 12
    prev_year = current_year if current_month > 1 else current_year - 1
    
    cursor.execute(
        "SELECT amount FROM monthly_base_amount WHERE unit_id = %s AND month = %s AND year = %s",
        (unit_id, prev_month, prev_year)
    )
    prev_month_result = cursor.fetchone()
    previous_month_amount = prev_month_result['amount'] if prev_month_result else 0
    
    if request.method == 'POST':
        amount = float(request.form.get('amount', 0))
        
        if monthly_base:
            # Atualizar valor existente
            cursor.execute(
                "UPDATE monthly_base_amount SET amount = %s WHERE id = %s",
                (amount, monthly_base['id'])
            )
        else:
            # Criar novo registro
            cursor.execute(
                "INSERT INTO monthly_base_amount (unit_id, month, year, amount) VALUES (%s, %s, %s, %s)",
                (unit_id, current_month, current_year, amount)
            )
        
        conn.commit()
        flash('Valor base mensal atualizado com sucesso!', 'success')
        
        # Redirecionar para distribuição do valor base
        return redirect(url_for('user_distribute_base', unit_id=unit_id))
    
    # Obter histórico de valores base
    cursor.execute(
        "SELECT month, year, amount FROM monthly_base_amount WHERE unit_id = %s ORDER BY year DESC, month DESC LIMIT 12",
        (unit_id,)
    )
    base_history = cursor.fetchall()
    
    cursor.close()
    conn.close()
    
    return render_template(
        'user/monthly_base.html',
        unit=unit,
        monthly_base=monthly_base,
        current_month=current_month,
        current_year=current_year,
        month_name=calendar.month_name[current_month],
        base_history=base_history,
        calendar=calendar,
        previous_month_amount=previous_month_amount
    )

@app.route('/user/unit/<int:unit_id>/distribute_base', methods=['GET', 'POST'])
@login_required
def user_distribute_base(unit_id):
    """
    Rota para distribuição do valor base mensal entre os caixas.
    """
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
    
    today = get_brazil_datetime()
    current_month = today.month
    current_year = today.year
    
    # Obter valor base do mês atual
    cursor.execute(
        "SELECT * FROM monthly_base_amount WHERE unit_id = %s AND month = %s AND year = %s",
        (unit_id, current_month, current_year)
    )
    monthly_base = cursor.fetchone()
    
    if not monthly_base:
        cursor.close()
        conn.close()
        flash('Primeiro defina o valor base mensal!', 'warning')
        return redirect(url_for('user_monthly_base', unit_id=unit_id))
    
    # Obter caixas da unidade (exceto o financeiro)
    cursor.execute("SELECT * FROM cashier WHERE unit_id = %s AND number > 0 ORDER BY number", (unit_id,))
    cashiers = cursor.fetchall()
    
    # Estrutura para armazenar os valores distribuídos por caixa
    cashier_values = {}
    total_distributed = 0
    
    # Processar a distribuição se for POST
    if request.method == 'POST':
        for cashier in cashiers:
            # Obter valor para este caixa
            amount_key = f'amount_{cashier["id"]}'
            active_key = f'active_{cashier["id"]}'
            
            amount = float(request.form.get(amount_key, 0))
            is_active = active_key in request.form
            
            # Atualizar status do caixa
            status = 'aberto' if is_active else 'fechado'
            cursor.execute(
                "UPDATE cashier SET status = %s WHERE id = %s",
                (status, cashier['id'])
            )
            
            # Salvar o valor base para este caixa na nova tabela
            cursor.execute(
                "INSERT INTO cashier_base_values (cashier_id, month, year, amount) VALUES (%s, %s, %s, %s) "
                "ON DUPLICATE KEY UPDATE amount = %s",
                (cashier['id'], current_month, current_year, amount, amount)
            )
            
            cashier_values[cashier['id']] = amount
            total_distributed += amount
        
        conn.commit()
        flash('Distribuição de valores realizada com sucesso!', 'success')
        return redirect(url_for('user_cashiers', unit_id=unit_id))
    else:
        # No caso de GET, verificar se existem valores previamente distribuídos
        for cashier in cashiers:
            cursor.execute(
                "SELECT amount FROM cashier_base_values WHERE cashier_id = %s AND month = %s AND year = %s",
                (cashier['id'], current_month, current_year)
            )
            base_value = cursor.fetchone()
            
            if base_value:
                # Usar o valor previamente distribuído
                cashier_values[cashier['id']] = base_value['amount']
                total_distributed += base_value['amount']
            else:
                # Se não tiver valor previamente distribuído
                if cashier['status'] == 'aberto':
                    # Distribuir igualmente entre os caixas ativos
                    active_cashiers = [c for c in cashiers if c['status'] == 'aberto']
                    if active_cashiers:
                        equal_amount = monthly_base['amount'] / len(active_cashiers)
                        cashier_values[cashier['id']] = equal_amount
                        total_distributed += equal_amount
                else:
                    cashier_values[cashier['id']] = 0
    
    cursor.close()
    conn.close()
    
    return render_template(
        'user/distribute_base.html',
        unit=unit,
        cashiers=cashiers,
        monthly_base=monthly_base,
        current_month=current_month,
        current_year=current_year,
        month_name=calendar.month_name[current_month],
        cashier_values=cashier_values,
        total_distributed=total_distributed
    )  

# Rota para obter métodos de pagamento via AJAX
@app.route('/api/payment_methods/<int:parent_id>', methods=['GET'])
@login_required
def get_payment_methods(parent_id):
    conn = get_db_connection()
    cursor = conn.cursor()
    
    cursor.execute(
        "SELECT * FROM payment_method WHERE parent_id = %s AND is_active = 1 ORDER BY name",
        (parent_id,)
    )
    methods = cursor.fetchall()
    
    cursor.close()
    conn.close()
    
    # Converter para formato JSON
    result = []
    for method in methods:
        result.append({
            'id': method['id'],
            'name': method['name'],
            'category': method['category']
        })
    
    return jsonify(result)

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
        # Verificar se é despesa da loja
        if movement['type'] == 'despesa_loja':
            cursor.execute("DELETE FROM store_expense WHERE movement_id = %s", (movement_id,))
        
        # Verificar se há moedas a ajustar
        if movement['coins_in'] > 0 or movement['coins_out'] > 0:
            cursor.execute("SELECT * FROM coins_control WHERE unit_id = %s", (unit_id,))
            coins_control = cursor.fetchone()
            
            if coins_control:
                # Calcular novo total (reverter a operação)
                new_total = coins_control['total_amount'] - movement['coins_in'] + movement['coins_out']
                cursor.execute(
                    "UPDATE coins_control SET total_amount = %s WHERE id = %s",
                    (new_total, coins_control['id'])
                )
                
                # Registrar no histórico
                cursor.execute(
                    "INSERT INTO coins_history (unit_id, amount, action) VALUES (%s, %s, %s)",
                    (unit_id, -(movement['coins_in'] - movement['coins_out']), 'add')
                )
        
        # Excluir movimento
        cursor.execute("DELETE FROM movement WHERE id = %s", (movement_id,))
        conn.commit()
        
        flash('Movimento excluído com sucesso!', 'success')
    except Exception as e:
        conn.rollback()
        flash(f'Erro ao excluir movimento: {str(e)}', 'error')
    
    cursor.close()
    conn.close()
    return redirect(url_for('user_movements', unit_id=unit_id, cashier_id=cashier_id, date=movement_date))

# Rota para processar movimentações em lote
@app.route('/user/unit/<int:unit_id>/cashier/<int:cashier_id>/batch_movements', methods=['POST'])
@login_required
def batch_movements(unit_id, cashier_id):
    conn = get_db_connection()
    cursor = conn.cursor()
    
    # Verificar se a unidade existe
    cursor.execute("SELECT * FROM unit WHERE id = %s", (unit_id,))
    unit = cursor.fetchone()
    
    if not unit:
        cursor.close()
        conn.close()
        return jsonify({'success': False, 'message': 'Unidade não encontrada!'})
    
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
            return jsonify({'success': False, 'message': 'Acesso não autorizado a esta unidade!'})
    
    # Verificar se o caixa existe e pertence à unidade
    cursor.execute(
        "SELECT * FROM cashier WHERE id = %s AND unit_id = %s",
        (cashier_id, unit_id)
    )
    cashier = cursor.fetchone()
    
    if not cashier:
        cursor.close()
        conn.close()
        return jsonify({'success': False, 'message': 'Caixa não encontrado ou não pertence a esta unidade!'})
    
    # MODIFICAÇÃO AQUI: Obter a data selecionada da URL (referrer) no horário do Brasil
    selected_date = get_brazil_datetime().date()
    
    # Obter URL de referência
    referrer = request.referrer
    if referrer and 'date=' in referrer:
        # Extrair a data da URL
        date_str = referrer.split('date=')[1].split('&')[0]
        try:
            selected_date = datetime.strptime(date_str, '%Y-%m-%d').date()
        except (ValueError, IndexError):
            # Em caso de erro, manter a data atual do Brasil
            pass
    
    # Obter número de entradas
    entry_count = int(request.form.get('entry_count', 0))
    
    if entry_count <= 0:
        cursor.close()
        conn.close()
        return jsonify({'success': False, 'message': 'Nenhuma movimentação para processar!'})
    
    try:
        # Processar cada entrada
        for i in range(1, entry_count + 1):
            # Verificar se a entrada existe (pode ter sido removida pelo usuário)
            if f'batch_payment_detail_{i}' not in request.form:
                continue
            
            payment_method_id = request.form.get(f'batch_payment_detail_{i}')
            amount = float(request.form.get(f'batch_amount_{i}', 0))
            description = request.form.get(f'batch_description_{i}', '')
            
            if payment_method_id and amount > 0:
                # Combinar a data selecionada com a hora atual do Brasil
                current_brazil_time = get_brazil_datetime().time()
                movement_datetime = datetime.combine(selected_date, current_brazil_time)
                
                # Inserir movimentação usando a data selecionada
                cursor.execute(
                    "INSERT INTO movement "
                    "(cashier_id, type, amount, payment_method, description, payment_status, created_at) "
                    "VALUES (%s, %s, %s, %s, %s, %s, %s)",
                    (cashier_id, 'entrada', amount, payment_method_id, description, 'realizado', movement_datetime)
                )
        
        conn.commit()
        cursor.close()
        conn.close()
        
        return jsonify({
            'success': True, 
            'message': f'{entry_count} movimentações foram registradas com sucesso!'
        })
        
    except Exception as e:
        conn.rollback()
        cursor.close()
        conn.close()
        return jsonify({'success': False, 'message': f'Erro ao registrar movimentações: {str(e)}'})

# Página 404
@app.errorhandler(404)
def page_not_found(e):
    return render_template('404.html'), 404

# Iniciar o aplicativo
if __name__ == '__main__':
    port = int(os.environ.get("PORT", 5000))
    app.run(host='0.0.0.0', port=port)