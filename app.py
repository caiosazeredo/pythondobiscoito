from flask import Flask, render_template, request, redirect, url_for, flash, jsonify
from flask_login import LoginManager, login_user, logout_user, login_required, current_user
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import datetime
import os
from models import db, User, Unit, Cashier, Movement, PaymentMethod
from config import Config

# Inicialização do app
app = Flask(__name__)
app.config.from_object(Config)

# Inicialização do banco de dados
db.init_app(app)

# Configuração do Flask-Login
login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'login'

@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))

# Criar tabelas do banco de dados (se não existirem)
@app.before_first_request
def create_tables():
    db.create_all()

# Rotas de autenticação
@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        email = request.form.get('email')
        password = request.form.get('password')
        
        user = User.query.filter_by(email=email).first()
        if user and check_password_hash(user.password_hash, password):
            login_user(user)
            user.last_login = datetime.utcnow()
            db.session.commit()
            
            next_page = request.args.get('next')
            if user.is_superuser:
                return redirect(next_page or url_for('admin_home'))
            else:
                return redirect(next_page or url_for('user_home'))
        else:
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
    
    users = User.query.all()
    return render_template('admin/users_list.html', users=users)

@app.route('/admin/users/create', methods=['GET', 'POST'])
@login_required
def admin_create_user():
    if not current_user.is_superuser:
        flash('Acesso não autorizado!', 'error')
        return redirect(url_for('user_home'))
    
    units = Unit.query.filter_by(is_active=True).all()
    
    if request.method == 'POST':
        name = request.form.get('name')
        email = request.form.get('email')
        cpf = request.form.get('cpf')
        phone = request.form.get('phone')
        role = request.form.get('role')
        is_superuser = 'is_superuser' in request.form
        selected_units = request.form.getlist('units')
        
        # Verificar se o email já existe
        existing_user = User.query.filter_by(email=email).first()
        if existing_user:
            flash('Este email já está cadastrado!', 'error')
            return render_template('admin/create_user.html', units=units)
        
        # Gerar uma senha temporária
        temp_password = 'senha123'  # Em produção, gerar uma senha aleatória
        
        user = User(
            name=name,
            email=email,
            cpf=cpf,
            phone=phone,
            role=role,
            is_superuser=is_superuser
        )
        user.password_hash = generate_password_hash(temp_password)
        
        # Adicionar unidades selecionadas
        if not is_superuser and selected_units:
            for unit_id in selected_units:
                unit = Unit.query.get(unit_id)
                if unit:
                    user.units.append(unit)
        
        db.session.add(user)
        db.session.commit()
        
        flash(f'Usuário criado com sucesso! Senha temporária: {temp_password}', 'success')
        return redirect(url_for('admin_users_list'))
    
    return render_template('admin/create_user.html', units=units)

@app.route('/admin/users/<int:user_id>/edit', methods=['GET', 'POST'])
@login_required
def admin_edit_user(user_id):
    if not current_user.is_superuser:
        flash('Acesso não autorizado!', 'error')
        return redirect(url_for('user_home'))
    
    user = User.query.get_or_404(user_id)
    units = Unit.query.filter_by(is_active=True).all()
    
    if request.method == 'POST':
        user.name = request.form.get('name')
        
        # Verificar se o email está sendo alterado
        new_email = request.form.get('email')
        if new_email != user.email:
            existing_user = User.query.filter_by(email=new_email).first()
            if existing_user:
                flash('Este email já está cadastrado!', 'error')
                return render_template('admin/edit_user.html', user=user, units=units)
            user.email = new_email
            
        user.cpf = request.form.get('cpf')
        user.phone = request.form.get('phone')
        user.role = request.form.get('role')
        user.is_superuser = 'is_superuser' in request.form
        user.is_active = 'is_active' in request.form
        
        # Atualizar unidades
        user.units = []
        if not user.is_superuser:
            selected_units = request.form.getlist('units')
            for unit_id in selected_units:
                unit = Unit.query.get(unit_id)
                if unit:
                    user.units.append(unit)
        
        db.session.commit()
        flash('Usuário atualizado com sucesso!', 'success')
        return redirect(url_for('admin_users_list'))
    
    return render_template('admin/edit_user.html', user=user, units=units)

@app.route('/admin/users/<int:user_id>/delete', methods=['POST'])
@login_required
def admin_delete_user(user_id):
    if not current_user.is_superuser:
        flash('Acesso não autorizado!', 'error')
        return redirect(url_for('user_home'))
    
    user = User.query.get_or_404(user_id)
    
    # Não permitir que o usuário exclua a si mesmo
    if user.id == current_user.id:
        flash('Você não pode excluir seu próprio usuário!', 'error')
        return redirect(url_for('admin_users_list'))
    
    db.session.delete(user)
    db.session.commit()
    
    flash('Usuário excluído com sucesso!', 'success')
    return redirect(url_for('admin_users_list'))

# Rotas para Unidades (Admin)
@app.route('/admin/units')
@login_required
def admin_units_list():
    if not current_user.is_superuser:
        flash('Acesso não autorizado!', 'error')
        return redirect(url_for('user_home'))
    
    units = Unit.query.all()
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
        is_active = 'is_active' in request.form
        
        unit = Unit(
            name=name,
            address=address,
            phone=phone,
            is_active=is_active
        )
        
        db.session.add(unit)
        db.session.commit()
        
        # Criar os caixas para a unidade
        cashier_count = int(request.form.get('cashier_count', 1))
        for i in range(1, cashier_count + 1):
            cashier = Cashier(
                unit_id=unit.id,
                number=i,
                status='fechado',
                payment_methods={}
            )
            db.session.add(cashier)
        
        db.session.commit()
        
        flash('Unidade criada com sucesso!', 'success')
        return redirect(url_for('admin_units_list'))
    
    return render_template('admin/create_unit.html')

@app.route('/admin/units/<int:unit_id>/edit', methods=['GET', 'POST'])
@login_required
def admin_edit_unit(unit_id):
    if not current_user.is_superuser:
        flash('Acesso não autorizado!', 'error')
        return redirect(url_for('user_home'))
    
    unit = Unit.query.get_or_404(unit_id)
    
    if request.method == 'POST':
        unit.name = request.form.get('name')
        unit.address = request.form.get('address')
        unit.phone = request.form.get('phone')
        unit.is_active = 'is_active' in request.form
        
        db.session.commit()
        flash('Unidade atualizada com sucesso!', 'success')
        return redirect(url_for('admin_units_list'))
    
    return render_template('admin/edit_unit.html', unit=unit)

@app.route('/admin/units/<int:unit_id>/delete', methods=['POST'])
@login_required
def admin_delete_unit(unit_id):
    if not current_user.is_superuser:
        flash('Acesso não autorizado!', 'error')
        return redirect(url_for('user_home'))
    
    unit = Unit.query.get_or_404(unit_id)
    db.session.delete(unit)
    db.session.commit()
    
    flash('Unidade excluída com sucesso!', 'success')
    return redirect(url_for('admin_units_list'))

# === Rotas de Usuário ===
@app.route('/user')
@login_required
def user_home():
    units = []
    if current_user.is_superuser:
        # Super usuários podem ver todas as unidades
        units = Unit.query.filter_by(is_active=True).all()
    else:
        # Usuários normais só veem as unidades associadas a eles
        units = current_user.units
    
    return render_template('user/home.html', units=units)

@app.route('/user/unit/<int:unit_id>/cashiers')
@login_required
def user_cashiers(unit_id):
    unit = Unit.query.get_or_404(unit_id)
    
    # Verificar se o usuário tem acesso à unidade
    if not current_user.is_superuser and unit not in current_user.units:
        flash('Acesso não autorizado a esta unidade!', 'error')
        return redirect(url_for('user_home'))
    
    # Verificar se é para criar um novo caixa
    if request.args.get('create') == 'true' and current_user.is_superuser:
        # Obter o próximo número disponível para o caixa
        last_cashier = Cashier.query.filter_by(unit_id=unit_id).order_by(Cashier.number.desc()).first()
        next_number = 1 if not last_cashier else last_cashier.number + 1
        
        # Criar o novo caixa
        new_cashier = Cashier(
            unit_id=unit_id,
            number=next_number,
            status='fechado',
            payment_methods={}
        )
        db.session.add(new_cashier)
        db.session.commit()
        
        flash(f'Caixa {next_number} criado com sucesso!', 'success')
    
    cashiers = Cashier.query.filter_by(unit_id=unit_id).order_by(Cashier.number).all()
    return render_template('user/cashiers.html', unit=unit, cashiers=cashiers)

@app.route('/user/unit/<int:unit_id>/cashier/<int:cashier_id>/movements', methods=['GET', 'POST'])
@login_required
def user_movements(unit_id, cashier_id):
    unit = Unit.query.get_or_404(unit_id)
    cashier = Cashier.query.get_or_404(cashier_id)
    
    # Verificar se o usuário tem acesso à unidade
    if not current_user.is_superuser and unit not in current_user.units:
        flash('Acesso não autorizado a esta unidade!', 'error')
        return redirect(url_for('user_home'))
    
    # Verificar se o caixa pertence à unidade
    if cashier.unit_id != unit.id:
        flash('Caixa não pertence a esta unidade!', 'error')
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
    
    movements = Movement.query.filter(
        Movement.cashier_id == cashier_id,
        Movement.created_at.between(start_date, end_date)
    ).order_by(Movement.created_at.desc()).all()
    
    # Obter métodos de pagamento
    payment_methods = PaymentMethod.query.filter_by(is_active=True).all()
    
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
        
        movement = Movement(
            cashier_id=cashier_id,
            type=movement_type,
            amount=amount,
            payment_method=payment_method_id,
            description=description,
            payment_status=payment_status,
            coins_in=coins_in,
            coins_out=coins_out,
            client_name=client_name,
            document_number=document_number,
            created_at=datetime.now()
        )
        
        db.session.add(movement)
        db.session.commit()
        
        flash('Movimentação registrada com sucesso!', 'success')
        return redirect(url_for('user_movements', unit_id=unit_id, cashier_id=cashier_id, date=date_formatted))
    
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
    unit = Unit.query.get_or_404(unit_id)
    
    # Verificar se o usuário tem acesso à unidade
    if not current_user.is_superuser and unit not in current_user.units:
        flash('Acesso não autorizado a esta unidade!', 'error')
        return redirect(url_for('user_home'))
    
    movement = Movement.query.get_or_404(movement_id)
    
    # Verificar se o movimento pertence ao caixa
    if movement.cashier_id != cashier_id:
        flash('Movimento não pertence a este caixa!', 'error')
        return redirect(url_for('user_movements', unit_id=unit_id, cashier_id=cashier_id))
    
    # Obter a data do movimento para redirecionar de volta com o filtro correto
    movement_date = movement.created_at.strftime('%Y-%m-%d')
    
    db.session.delete(movement)
    db.session.commit()
    
    flash('Movimento excluído com sucesso!', 'success')
    return redirect(url_for('user_movements', unit_id=unit_id, cashier_id=cashier_id, date=movement_date))

# Página 404
@app.errorhandler(404)
def page_not_found(e):
    return render_template('404.html'), 404

# Iniciar o aplicativo
if __name__ == '__main__':
    app.run(debug=True)