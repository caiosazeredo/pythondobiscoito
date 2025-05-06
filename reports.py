from flask import Blueprint, render_template, request, redirect, url_for, flash, jsonify
from flask_login import login_required, current_user
from datetime import datetime, timedelta, date
import calendar
from decimal import Decimal
import pymysql
from pymysql.cursors import DictCursor
from config import Config
import json

# Criação do Blueprint para relatórios
reports = Blueprint('reports', __name__)

# Função para obter conexão com o banco
def get_db_connection():
    return pymysql.connect(
        host=Config.MYSQL_HOST,
        port=int(Config.MYSQL_PORT),
        user=Config.MYSQL_USER,
        password=Config.MYSQL_PASSWORD,
        database=Config.MYSQL_DB,
        cursorclass=DictCursor,
        ssl={}
    )

# Verificar acesso à unidade
def verify_unit_access(unit_id):
    conn = get_db_connection()
    cursor = conn.cursor()
    
    # Verificar se a unidade existe
    cursor.execute("SELECT * FROM unit WHERE id = %s", (unit_id,))
    unit = cursor.fetchone()
    
    if not unit:
        cursor.close()
        conn.close()
        return None, "Unidade não encontrada"
    
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
            return None, "Acesso não autorizado a esta unidade"
    
    cursor.close()
    conn.close()
    return unit, None

# Página principal de relatórios
@reports.route('/reports')
@login_required
def reports_home():
    conn = get_db_connection()
    cursor = conn.cursor()
    
    if current_user.is_superuser:
        # Super usuários podem ver todas as unidades
        cursor.execute("SELECT * FROM unit WHERE is_active = 1 ORDER BY name")
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
    
    return render_template('reports/home.html', units=units)

# 1. Relatório Diário de Vendas (Acessível por todos)
@reports.route('/reports/daily_sales/<int:unit_id>', methods=['GET', 'POST'])
@login_required
def daily_sales_report(unit_id):
    unit, error = verify_unit_access(unit_id)
    if error:
        flash(error, 'error')
        return redirect(url_for('reports.reports_home'))
    
    # Obter data para o relatório
    if request.method == 'POST':
        date_str = request.form.get('report_date')
        try:
            report_date = datetime.strptime(date_str, '%Y-%m-%d').date()
        except (ValueError, TypeError):
            report_date = date.today()
    else:
        date_str = request.args.get('date')
        try:
            report_date = datetime.strptime(date_str, '%Y-%m-%d').date() if date_str else date.today()
        except (ValueError, TypeError):
            report_date = date.today()
    
    conn = get_db_connection()
    cursor = conn.cursor()
    
    # Definir período
    start_datetime = datetime.combine(report_date, datetime.min.time())
    end_datetime = datetime.combine(report_date, datetime.max.time())
    
    # Obter caixas da unidade
    cursor.execute("SELECT * FROM cashier WHERE unit_id = %s ORDER BY number", (unit_id,))
    cashiers = cursor.fetchall()
    
    # Dados de vendas por caixa
    sales_by_cashier = {}
    total_z = 0
    total_t = 0
    total_devo = 0
    
    for cashier in cashiers:
        # Obter vendas do caixa
        cursor.execute(
            "SELECT SUM(amount) as total FROM movement "
            "WHERE cashier_id = %s AND type = 'entrada' AND payment_status = 'realizado' "
            "AND created_at BETWEEN %s AND %s",
            (cashier['id'], start_datetime, end_datetime)
        )
        sales = cursor.fetchone()
        t_value = sales['total'] if sales and sales['total'] else 0
        
        # Obter cancelamentos
        cursor.execute(
            "SELECT SUM(devo_value) as total FROM devo_values "
            "WHERE cashier_id = %s AND date = %s",
            (cashier['id'], report_date)
        )
        devo = cursor.fetchone()
        devo_value = devo['total'] if devo and devo['total'] else 0
        
        # Obter valor Z
        cursor.execute(
            "SELECT z_value FROM pdv_z_values "
            "WHERE cashier_id = %s AND date = %s",
            (cashier['id'], report_date)
        )
        z = cursor.fetchone()
        z_value = z['z_value'] if z and z['z_value'] else 0
        
        # Vendas por forma de pagamento
        cursor.execute(
            "SELECT pm.name, pm.category, SUM(m.amount) as total "
            "FROM movement m "
            "JOIN payment_method pm ON m.payment_method = pm.id "
            "WHERE m.cashier_id = %s AND m.type = 'entrada' AND m.payment_status = 'realizado' "
            "AND m.created_at BETWEEN %s AND %s "
            "GROUP BY pm.name, pm.category "
            "ORDER BY pm.category, pm.name",
            (cashier['id'], start_datetime, end_datetime)
        )
        payment_methods = cursor.fetchall()
        
        # Armazenar dados do caixa
        sales_by_cashier[cashier['id']] = {
            'cashier': cashier,
            't_value': t_value,
            'devo_value': devo_value,
            'z_value': z_value,
            'diff_value': t_value - devo_value - z_value,
            'payment_methods': payment_methods
        }
        
        # Acumular totais
        total_t += t_value
        total_devo += devo_value
        total_z += z_value
    
    # Vendas totais por método de pagamento
    cursor.execute(
        "SELECT pm.name, pm.category, SUM(m.amount) as total "
        "FROM movement m "
        "JOIN payment_method pm ON m.payment_method = pm.id "
        "JOIN cashier c ON m.cashier_id = c.id "
        "WHERE c.unit_id = %s AND m.type = 'entrada' AND m.payment_status = 'realizado' "
        "AND m.created_at BETWEEN %s AND %s "
        "GROUP BY pm.name, pm.category "
        "ORDER BY pm.category, pm.name",
        (unit_id, start_datetime, end_datetime)
    )
    total_by_payment_method = cursor.fetchall()
    
    # Agrupar por categoria
    totals_by_category = {}
    for method in total_by_payment_method:
        category = method['category']
        if category not in totals_by_category:
            totals_by_category[category] = 0
        totals_by_category[category] += method['total']
    
    cursor.close()
    conn.close()
    
    return render_template(
        'reports/daily_sales.html',
        unit=unit,
        report_date=report_date,
        sales_by_cashier=sales_by_cashier,
        total_t=total_t,
        total_devo=total_devo,
        total_z=total_z,
        total_diff=total_t - total_devo - total_z,
        total_by_payment_method=total_by_payment_method,
        totals_by_category=totals_by_category
    )

# 2. Relatório Mensal de Faturamento (Acesso apenas superusuários)
@reports.route('/reports/monthly_revenue', methods=['GET', 'POST'])
@login_required
def monthly_revenue_report():
    if not current_user.is_superuser:
        flash('Acesso não autorizado!', 'error')
        return redirect(url_for('reports.reports_home'))
    
    conn = get_db_connection()
    cursor = conn.cursor()
    
    # Obter todas as unidades
    cursor.execute("SELECT * FROM unit WHERE is_active = 1 ORDER BY name")
    units = cursor.fetchall()
    
    # Definir período para o relatório
    if request.method == 'POST':
        year = int(request.form.get('year', datetime.now().year))
        month = int(request.form.get('month', datetime.now().month))
    else:
        year = int(request.args.get('year', datetime.now().year))
        month = int(request.args.get('month', datetime.now().month))
    
    # Obter dados para os últimos 12 meses para comparativo
    months_data = []
    current_date = datetime.now()
    
    # Dados de faturamento por unidade para o mês selecionado
    revenue_by_unit = {}
    total_month_revenue = 0
    
    for unit in units:
        # Primeiro dia do mês
        first_day = datetime(year, month, 1)
        # Último dia do mês
        last_day = datetime(year, month, calendar.monthrange(year, month)[1], 23, 59, 59)
        
        cursor.execute(
            "SELECT SUM(m.amount) as total_revenue "
            "FROM movement m "
            "JOIN cashier c ON m.cashier_id = c.id "
            "WHERE c.unit_id = %s AND m.type = 'entrada' AND m.payment_status = 'realizado' "
            "AND m.created_at BETWEEN %s AND %s",
            (unit['id'], first_day, last_day)
        )
        result = cursor.fetchone()
        
        revenue = result['total_revenue'] if result and result['total_revenue'] else 0
        revenue_by_unit[unit['id']] = {
            'unit': unit,
            'revenue': revenue
        }
        total_month_revenue += revenue
    
    # Dados para o gráfico de evolução nos últimos 12 meses
    graph_data = []
    for i in range(12):
        month_to_check = current_date.month - i
        year_to_check = current_date.year
        
        # Ajuste para meses anteriores
        while month_to_check <= 0:
            month_to_check += 12
            year_to_check -= 1
            
        # Primeiro e último dia do mês
        first_day = datetime(year_to_check, month_to_check, 1)
        last_day = datetime(year_to_check, month_to_check, 
                           calendar.monthrange(year_to_check, month_to_check)[1], 23, 59, 59)
        
        # Obter faturamento do mês
        cursor.execute(
            "SELECT SUM(m.amount) as total_revenue "
            "FROM movement m "
            "JOIN cashier c ON m.cashier_id = c.id "
            "WHERE m.type = 'entrada' AND m.payment_status = 'realizado' "
            "AND m.created_at BETWEEN %s AND %s",
            (first_day, last_day)
        )
        result = cursor.fetchone()
        month_revenue = float(result['total_revenue'] if result and result['total_revenue'] else 0)
        
        graph_data.append({
            'month': calendar.month_name[month_to_check],
            'year': year_to_check,
            'revenue': month_revenue
        })
    
    # Reverter para ordem cronológica
    graph_data.reverse()
    
    cursor.close()
    conn.close()
    
    return render_template(
        'reports/monthly_revenue.html',
        units=units,
        revenue_by_unit=revenue_by_unit,
        total_month_revenue=total_month_revenue,
        year=year,
        month=month,
        month_name=calendar.month_name[month],
        graph_data=json.dumps(graph_data),
        calendar=calendar
    )

# 3. Relatório de Formas de Pagamento (Acessível por todos)
@reports.route('/reports/payment_methods/<int:unit_id>', methods=['GET', 'POST'])
@login_required
def payment_methods_report(unit_id):
    unit, error = verify_unit_access(unit_id)
    if error:
        flash(error, 'error')
        return redirect(url_for('reports.reports_home'))
    
    # Definir período para o relatório
    if request.method == 'POST':
        start_date_str = request.form.get('start_date')
        end_date_str = request.form.get('end_date')
    else:
        start_date_str = request.args.get('start_date')
        end_date_str = request.args.get('end_date')
    
    try:
        start_date = datetime.strptime(start_date_str, '%Y-%m-%d').date() if start_date_str else date.today().replace(day=1)
        end_date = datetime.strptime(end_date_str, '%Y-%m-%d').date() if end_date_str else date.today()
    except (ValueError, TypeError):
        start_date = date.today().replace(day=1)
        end_date = date.today()
    
    conn = get_db_connection()
    cursor = conn.cursor()
    
    # Converter datas para datetime
    start_datetime = datetime.combine(start_date, datetime.min.time())
    end_datetime = datetime.combine(end_date, datetime.max.time())
    
    # Totais por categoria de pagamento
    cursor.execute(
        "SELECT pm.category, SUM(m.amount) as total, COUNT(m.id) as count "
        "FROM movement m "
        "JOIN payment_method pm ON m.payment_method = pm.id "
        "JOIN cashier c ON m.cashier_id = c.id "
        "WHERE c.unit_id = %s AND m.type = 'entrada' AND m.payment_status = 'realizado' "
        "AND m.created_at BETWEEN %s AND %s "
        "GROUP BY pm.category "
        "ORDER BY total DESC",
        (unit_id, start_datetime, end_datetime)
    )
    categories = cursor.fetchall()
    
    # Totais por método de pagamento
    cursor.execute(
        "SELECT pm.name, pm.category, SUM(m.amount) as total, COUNT(m.id) as count "
        "FROM movement m "
        "JOIN payment_method pm ON m.payment_method = pm.id "
        "JOIN cashier c ON m.cashier_id = c.id "
        "WHERE c.unit_id = %s AND m.type = 'entrada' AND m.payment_status = 'realizado' "
        "AND m.created_at BETWEEN %s AND %s "
        "GROUP BY pm.name, pm.category "
        "ORDER BY pm.category, total DESC",
        (unit_id, start_datetime, end_datetime)
    )
    methods = cursor.fetchall()
    
    # Calcular valor médio por transação
    for method in methods:
        method['average'] = method['total'] / method['count'] if method['count'] > 0 else 0
    
    # Total geral
    cursor.execute(
        "SELECT SUM(m.amount) as grand_total, COUNT(m.id) as total_count "
        "FROM movement m "
        "JOIN cashier c ON m.cashier_id = c.id "
        "WHERE c.unit_id = %s AND m.type = 'entrada' AND m.payment_status = 'realizado' "
        "AND m.created_at BETWEEN %s AND %s",
        (unit_id, start_datetime, end_datetime)
    )
    totals = cursor.fetchone()
    grand_total = totals['grand_total'] if totals and totals['grand_total'] else 0
    total_count = totals['total_count'] if totals and totals['total_count'] else 0
    
    # Calcular percentuais
    for category in categories:
        category['percentage'] = (category['total'] / grand_total * 100) if grand_total > 0 else 0
    
    for method in methods:
        method['percentage'] = (method['total'] / grand_total * 100) if grand_total > 0 else 0
    
    # Dados para o gráfico
    graph_data = [{'name': method['name'], 'value': float(method['total'])} for method in methods]
    
    cursor.close()
    conn.close()
    
    return render_template(
        'reports/payment_methods.html',
        unit=unit,
        start_date=start_date,
        end_date=end_date,
        categories=categories,
        methods=methods,
        grand_total=grand_total,
        total_count=total_count,
        graph_data=json.dumps(graph_data),
        is_superuser=current_user.is_superuser
    )

# 4. Relatório de Despesas (Acesso apenas superusuários)
@reports.route('/reports/expenses', methods=['GET', 'POST'])
@login_required
def expenses_report():
    if not current_user.is_superuser:
        flash('Acesso não autorizado!', 'error')
        return redirect(url_for('reports.reports_home'))
    
    conn = get_db_connection()
    cursor = conn.cursor()
    
    # Obter todas as unidades
    cursor.execute("SELECT * FROM unit WHERE is_active = 1 ORDER BY name")
    units = cursor.fetchall()
    
    # Obter todas as categorias de despesa
    cursor.execute("SELECT * FROM expense_category WHERE is_active = 1 ORDER BY type, name")
    expense_categories = cursor.fetchall()
    
    # Filtros
    if request.method == 'POST':
        unit_id = request.form.get('unit_id', 'all')
        start_date_str = request.form.get('start_date')
        end_date_str = request.form.get('end_date')
        category_type = request.form.get('category_type', 'all')
    else:
        unit_id = request.args.get('unit_id', 'all')
        start_date_str = request.args.get('start_date')
        end_date_str = request.args.get('end_date')
        category_type = request.args.get('category_type', 'all')
    
    try:
        start_date = datetime.strptime(start_date_str, '%Y-%m-%d').date() if start_date_str else date.today().replace(day=1)
        end_date = datetime.strptime(end_date_str, '%Y-%m-%d').date() if end_date_str else date.today()
    except (ValueError, TypeError):
        start_date = date.today().replace(day=1)
        end_date = date.today()
    
    # Converter datas para datetime
    start_datetime = datetime.combine(start_date, datetime.min.time())
    end_datetime = datetime.combine(end_date, datetime.max.time())
    
    # Consulta base para despesas
    base_query = """
        SELECT se.id, se.description, se.created_at, ec.name as category_name, ec.type as category_type,
               m.amount, u.name as unit_name, u.id as unit_id
        FROM store_expense se
        JOIN movement m ON se.movement_id = m.id
        JOIN expense_category ec ON se.category_id = ec.id
        JOIN cashier c ON m.cashier_id = c.id
        JOIN unit u ON c.unit_id = u.id
        WHERE m.created_at BETWEEN %s AND %s
    """
    
    params = [start_datetime, end_datetime]
    
    # Adicionar filtro de unidade se especificado
    if unit_id != 'all':
        base_query += " AND u.id = %s"
        params.append(unit_id)
    
    # Adicionar filtro de categoria se especificado
    if category_type != 'all':
        base_query += " AND ec.type = %s"
        params.append(category_type)
    
    base_query += " ORDER BY se.created_at DESC"
    
    cursor.execute(base_query, params)
    expenses = cursor.fetchall()
    
    # Calcular totais por categoria
    totals_by_category = {}
    for expense in expenses:
        cat_key = expense['category_name']
        if cat_key not in totals_by_category:
            totals_by_category[cat_key] = {
                'name': expense['category_name'],
                'type': expense['category_type'],
                'total': 0
            }
        totals_by_category[cat_key]['total'] += expense['amount']
    
    # Calcular totais por tipo de categoria
    totals_by_type = {}
    for expense in expenses:
        type_key = expense['category_type']
        if type_key not in totals_by_type:
            totals_by_type[type_key] = 0
        totals_by_type[type_key] += expense['amount']
    
    # Calcular total geral
    total_expenses = sum(expense['amount'] for expense in expenses)
    
    # Calcular impacto sobre o faturamento
    total_revenue = 0
    if unit_id != 'all':
        cursor.execute(
            "SELECT SUM(m.amount) as total "
            "FROM movement m "
            "JOIN cashier c ON m.cashier_id = c.id "
            "WHERE c.unit_id = %s AND m.type = 'entrada' AND m.payment_status = 'realizado' "
            "AND m.created_at BETWEEN %s AND %s",
            (unit_id, start_datetime, end_datetime)
        )
        result = cursor.fetchone()
        total_revenue = result['total'] if result and result['total'] else 0
    else:
        cursor.execute(
            "SELECT SUM(m.amount) as total "
            "FROM movement m "
            "WHERE m.type = 'entrada' AND m.payment_status = 'realizado' "
            "AND m.created_at BETWEEN %s AND %s",
            (start_datetime, end_datetime)
        )
        result = cursor.fetchone()
        total_revenue = result['total'] if result and result['total'] else 0
    
    impact_percentage = (total_expenses / total_revenue * 100) if total_revenue > 0 else 0
    
    cursor.close()
    conn.close()
    
    return render_template(
        'reports/expenses.html',
        units=units,
        expense_categories=expense_categories,
        expenses=expenses,
        totals_by_category=totals_by_category,
        totals_by_type=totals_by_type,
        total_expenses=total_expenses,
        total_revenue=total_revenue,
        impact_percentage=impact_percentage,
        start_date=start_date,
        end_date=end_date,
        selected_unit_id=unit_id,
        selected_category_type=category_type
    )

# 5. Relatório de Desempenho por Unidade (Acesso apenas superusuários)
@reports.route('/reports/unit_performance', methods=['GET', 'POST'])
@login_required
def unit_performance_report():
    if not current_user.is_superuser:
        flash('Acesso não autorizado!', 'error')
        return redirect(url_for('reports.reports_home'))
    
    conn = get_db_connection()
    cursor = conn.cursor()
    
    # Obter todas as unidades
    cursor.execute("SELECT * FROM unit WHERE is_active = 1 ORDER BY name")
    units = cursor.fetchall()
    
    # Definir período para o relatório
    if request.method == 'POST':
        start_date_str = request.form.get('start_date')
        end_date_str = request.form.get('end_date')
    else:
        start_date_str = request.args.get('start_date')
        end_date_str = request.args.get('end_date')
    
    try:
        start_date = datetime.strptime(start_date_str, '%Y-%m-%d').date() if start_date_str else date.today().replace(day=1)
        end_date = datetime.strptime(end_date_str, '%Y-%m-%d').date() if end_date_str else date.today()
    except (ValueError, TypeError):
        start_date = date.today().replace(day=1)
        end_date = date.today()
    
    # Converter datas para datetime
    start_datetime = datetime.combine(start_date, datetime.min.time())
    end_datetime = datetime.combine(end_date, datetime.max.time())
    
    # Desempenho por unidade
    unit_performance = []
    
    for unit in units:
        # Faturamento
        cursor.execute(
            "SELECT SUM(m.amount) as revenue "
            "FROM movement m "
            "JOIN cashier c ON m.cashier_id = c.id "
            "WHERE c.unit_id = %s AND m.type = 'entrada' AND m.payment_status = 'realizado' "
            "AND m.created_at BETWEEN %s AND %s",
            (unit['id'], start_datetime, end_datetime)
        )
        revenue_result = cursor.fetchone()
        revenue = revenue_result['revenue'] if revenue_result and revenue_result['revenue'] else 0
        
        # Despesas
        cursor.execute(
            "SELECT SUM(m.amount) as expenses "
            "FROM movement m "
            "JOIN cashier c ON m.cashier_id = c.id "
            "WHERE c.unit_id = %s AND (m.type = 'despesa_loja' OR m.type = 'saida') "
            "AND m.created_at BETWEEN %s AND %s",
            (unit['id'], start_datetime, end_datetime)
        )
        expenses_result = cursor.fetchone()
        expenses = expenses_result['expenses'] if expenses_result and expenses_result['expenses'] else 0
        
        # Estornos
        cursor.execute(
            "SELECT SUM(m.amount) as refunds "
            "FROM movement m "
            "JOIN cashier c ON m.cashier_id = c.id "
            "WHERE c.unit_id = %s AND m.type = 'estorno' "
            "AND m.created_at BETWEEN %s AND %s",
            (unit['id'], start_datetime, end_datetime)
        )
        refunds_result = cursor.fetchone()
        refunds = refunds_result['refunds'] if refunds_result and refunds_result['refunds'] else 0
        
        # Quantidade de transações
        cursor.execute(
            "SELECT COUNT(m.id) as transactions "
            "FROM movement m "
            "JOIN cashier c ON m.cashier_id = c.id "
            "WHERE c.unit_id = %s AND m.type = 'entrada' AND m.payment_status = 'realizado' "
            "AND m.created_at BETWEEN %s AND %s",
            (unit['id'], start_datetime, end_datetime)
        )
        transactions_result = cursor.fetchone()
        transactions = transactions_result['transactions'] if transactions_result else 0
        
        # Cálculo do lucro
        profit = revenue - expenses - refunds
        profit_margin = (profit / revenue * 100) if revenue > 0 else 0
        
        unit_performance.append({
            'unit': unit,
            'revenue': revenue,
            'expenses': expenses,
            'refunds': refunds,
            'profit': profit,
            'profit_margin': profit_margin,
            'transactions': transactions,
            'avg_ticket': revenue / transactions if transactions > 0 else 0
        })
    
    # Ordenar por faturamento
    unit_performance.sort(key=lambda x: x['revenue'], reverse=True)
    
    # Dados para o gráfico
    revenue_data = [{'name': unit['unit']['name'], 'value': float(unit['revenue'])} for unit in unit_performance]
    profit_data = [{'name': unit['unit']['name'], 'value': float(unit['profit'])} for unit in unit_performance]
    
    cursor.close()
    conn.close()
    
    return render_template(
        'reports/unit_performance.html',
        unit_performance=unit_performance,
        start_date=start_date,
        end_date=end_date,
        revenue_data=json.dumps(revenue_data),
        profit_data=json.dumps(profit_data)
    )

# 6. Relatório de Fechamento de Caixa (Acessível por todos)
@reports.route('/reports/cashier_closing/<int:unit_id>', methods=['GET', 'POST'])
@login_required
def cashier_closing_report(unit_id):
    unit, error = verify_unit_access(unit_id)
    if error:
        flash(error, 'error')
        return redirect(url_for('reports.reports_home'))
    
    conn = get_db_connection()
    cursor = conn.cursor()
    
    # Obter caixas da unidade
    cursor.execute("SELECT * FROM cashier WHERE unit_id = %s ORDER BY number", (unit_id,))
    cashiers = cursor.fetchall()
    
    # Definir parâmetros de filtro
    if request.method == 'POST':
        cashier_id = request.form.get('cashier_id', 'all')
        date_str = request.form.get('report_date')
    else:
        cashier_id = request.args.get('cashier_id', 'all')
        date_str = request.args.get('report_date')
    
    try:
        report_date = datetime.strptime(date_str, '%Y-%m-%d').date() if date_str else date.today()
    except (ValueError, TypeError):
        report_date = date.today()
    
    # Definir intervalo de data
    start_datetime = datetime.combine(report_date, datetime.min.time())
    end_datetime = datetime.combine(report_date, datetime.max.time())
    
    # Preparar query base
    base_query = """
        SELECT c.number, m.id, m.type, m.amount, m.payment_status, m.description, m.created_at,
               pm.name as payment_method_name, pm.category as payment_method_category
        FROM movement m
        JOIN cashier c ON m.cashier_id = c.id
        LEFT JOIN payment_method pm ON m.payment_method = pm.id
        WHERE c.unit_id = %s AND m.created_at BETWEEN %s AND %s
    """
    
    params = [unit_id, start_datetime, end_datetime]
    
    # Adicionar filtro de caixa
    if cashier_id != 'all':
        base_query += " AND c.id = %s"
        params.append(cashier_id)
    
    base_query += " ORDER BY c.number, m.created_at"
    
    cursor.execute(base_query, params)
    movements = cursor.fetchall()
    
    # Agrupar movimentos por caixa
    cashier_movements = {}
    for movement in movements:
        cashier_number = movement['number']
        if cashier_number not in cashier_movements:
            cashier_movements[cashier_number] = []
        cashier_movements[cashier_number].append(movement)
    
    # Calcular totais por caixa
    cashier_totals = {}
    for number, movs in cashier_movements.items():
        total_entrada = sum(m['amount'] for m in movs if m['type'] == 'entrada' and m['payment_status'] == 'realizado')
        total_saida = sum(m['amount'] for m in movs if m['type'] == 'saida')
        total_estorno = sum(m['amount'] for m in movs if m['type'] == 'estorno')
        total_despesa = sum(m['amount'] for m in movs if m['type'] == 'despesa_loja')
        
        # Totais por método de pagamento
        payment_methods = {}
        for m in movs:
            if m['type'] == 'entrada' and m['payment_status'] == 'realizado':
                method_key = m['payment_method_name']
                if method_key not in payment_methods:
                    payment_methods[method_key] = {
                        'name': m['payment_method_name'],
                        'category': m['payment_method_category'],
                        'total': 0
                    }
                payment_methods[method_key]['total'] += m['amount']
        
        # Obter valor Z
        cursor.execute(
            "SELECT z_value FROM pdv_z_values WHERE cashier_id = %s AND date = %s",
            (cashier_id if cashier_id != 'all' else 0, report_date)
        )
        z_result = cursor.fetchone()
        z_value = z_result['z_value'] if z_result and z_result['z_value'] else 0
        
        # Obter cancelamentos
        cursor.execute(
            "SELECT SUM(devo_value) as total FROM devo_values WHERE cashier_id = %s AND date = %s",
            (cashier_id if cashier_id != 'all' else 0, report_date)
        )
        devo_result = cursor.fetchone()
        devo_value = devo_result['total'] if devo_result and devo_result['total'] else 0
        
        cashier_totals[number] = {
            'total_entrada': total_entrada,
            'total_saida': total_saida,
            'total_estorno': total_estorno,
            'total_despesa': total_despesa,
            'payment_methods': payment_methods,
            'z_value': z_value,
            'devo_value': devo_value,
            'saldo': total_entrada - total_saida - total_estorno - total_despesa
        }
    
    cursor.close()
    conn.close()
    
    return render_template(
        'reports/cashier_closing.html',
        unit=unit,
        cashiers=cashiers,
        selected_cashier_id=cashier_id,
        report_date=report_date,
        cashier_movements=cashier_movements,
        cashier_totals=cashier_totals
    )

# 7. Relatório de Movimentação de Moedas (Acessível por todos)
@reports.route('/reports/coins_movement/<int:unit_id>', methods=['GET', 'POST'])
@login_required
def coins_movement_report(unit_id):
    unit, error = verify_unit_access(unit_id)
    if error:
        flash(error, 'error')
        return redirect(url_for('reports.reports_home'))
    
    conn = get_db_connection()
    cursor = conn.cursor()
    
    # Definir período para o relatório
    if request.method == 'POST':
        start_date_str = request.form.get('start_date')
        end_date_str = request.form.get('end_date')
    else:
        start_date_str = request.args.get('start_date')
        end_date_str = request.args.get('end_date')
    
    try:
        start_date = datetime.strptime(start_date_str, '%Y-%m-%d').date() if start_date_str else date.today().replace(day=1)
        end_date = datetime.strptime(end_date_str, '%Y-%m-%d').date() if end_date_str else date.today()
    except (ValueError, TypeError):
        start_date = date.today().replace(day=1)
        end_date = date.today()
    
    # Converter datas para datetime
    start_datetime = datetime.combine(start_date, datetime.min.time())
    end_datetime = datetime.combine(end_date, datetime.max.time())
    
    # Obter histórico de movimentação de moedas
    cursor.execute(
        "SELECT * FROM coins_history "
        "WHERE unit_id = %s AND created_at BETWEEN %s AND %s "
        "ORDER BY created_at DESC",
        (unit_id, start_datetime, end_datetime)
    )
    coins_history = cursor.fetchall()
    
    # Obter saldo atual
    cursor.execute("SELECT total_amount FROM coins_control WHERE unit_id = %s", (unit_id,))
    coins_control = cursor.fetchone()
    current_balance = coins_control['total_amount'] if coins_control and coins_control['total_amount'] else 0
    
    # Calcular totais
    total_added = sum(h['amount'] for h in coins_history if h['action'] == 'add' and h['amount'] > 0)
    total_subtracted = sum(abs(h['amount']) for h in coins_history if h['action'] == 'add' and h['amount'] < 0)
    total_deposited = sum(h['amount'] for h in coins_history if h['action'] == 'deposit')
    
    # Tendência diária
    daily_trends = {}
    for history in coins_history:
        day = history['created_at'].date()
        if day not in daily_trends:
            daily_trends[day] = {
                'date': day,
                'added': 0,
                'subtracted': 0,
                'deposited': 0,
                'net': 0
            }
        
        if history['action'] == 'add':
            if history['amount'] > 0:
                daily_trends[day]['added'] += history['amount']
            else:
                daily_trends[day]['subtracted'] += abs(history['amount'])
        elif history['action'] == 'deposit':
            daily_trends[day]['deposited'] += history['amount']
        
        daily_trends[day]['net'] = daily_trends[day]['added'] - daily_trends[day]['subtracted']
    
    # Converter para lista e ordenar
    daily_trends_list = list(daily_trends.values())
    daily_trends_list.sort(key=lambda x: x['date'])
    
    # Dados para o gráfico
    graph_data = [{'date': day['date'].strftime('%Y-%m-%d'), 'value': float(day['net'])} for day in daily_trends_list]
    
    # Verificar alertas - volumes acima da média
    average_daily_net = sum(day['net'] for day in daily_trends_list) / len(daily_trends_list) if daily_trends_list else 0
    alerts = []
    
    for day in daily_trends_list:
        if day['net'] > average_daily_net * 1.5:  # 50% acima da média
            alerts.append({
                'date': day['date'],
                'value': day['net'],
                'percentage': (day['net'] / average_daily_net - 1) * 100 if average_daily_net > 0 else 0
            })
    
    cursor.close()
    conn.close()
    
    return render_template(
        'reports/coins_movement.html',
        unit=unit,
        coins_history=coins_history,
        current_balance=current_balance,
        total_added=total_added,
        total_subtracted=total_subtracted,
        total_deposited=total_deposited,
        daily_trends=daily_trends_list,
        start_date=start_date,
        end_date=end_date,
        graph_data=json.dumps(graph_data),
        alerts=alerts,
        average_daily_net=average_daily_net
    )

# 8. Relatório de Fluxo de Caixa (Acesso apenas superusuários)
@reports.route('/reports/cash_flow', methods=['GET', 'POST'])
@login_required
def cash_flow_report():
    if not current_user.is_superuser:
        flash('Acesso não autorizado!', 'error')
        return redirect(url_for('reports.reports_home'))
    
    conn = get_db_connection()
    cursor = conn.cursor()
    
    # Obter todas as unidades
    cursor.execute("SELECT * FROM unit WHERE is_active = 1 ORDER BY name")
    units = cursor.fetchall()
    
    # Definir parâmetros de filtro
    if request.method == 'POST':
        unit_id = request.form.get('unit_id', 'all')
        period = request.form.get('period', 'month')
    else:
        unit_id = request.args.get('unit_id', 'all')
        period = request.args.get('period', 'month')
    
    # Definir período de análise
    today = date.today()
    
    if period == 'week':
        # Último dia da semana atual (domingo)
        end_date = today + timedelta(days=(6 - today.weekday()))
        # Primeiro dia (segunda) da semana anterior
        start_date = end_date - timedelta(days=13)
        # Data para projeção futura
        projection_date = end_date + timedelta(days=7)
    elif period == 'month':
        # Último dia do mês atual
        end_date = date(today.year, today.month, calendar.monthrange(today.year, today.month)[1])
        # Primeiro dia do mês anterior
        if today.month == 1:
            start_date = date(today.year - 1, 12, 1)
        else:
            start_date = date(today.year, today.month - 1, 1)
        # Data para projeção futura
        if today.month == 12:
            projection_date = date(today.year + 1, 1, 31)
        else:
            projection_date = date(today.year, today.month + 1, calendar.monthrange(today.year, today.month + 1)[1])
    else:  # quarter
        # Identificar trimestre atual
        current_quarter = (today.month - 1) // 3 + 1
        # Último dia do trimestre
        last_month_of_quarter = current_quarter * 3
        end_date = date(today.year, last_month_of_quarter, calendar.monthrange(today.year, last_month_of_quarter)[1])
        # Primeiro dia do trimestre anterior
        prev_quarter = 4 if current_quarter == 1 else current_quarter - 1
        prev_quarter_year = today.year - 1 if current_quarter == 1 else today.year
        start_date = date(prev_quarter_year, (prev_quarter - 1) * 3 + 1, 1)
        # Data para projeção futura
        next_quarter = 1 if current_quarter == 4 else current_quarter + 1
        next_quarter_year = today.year + 1 if current_quarter == 4 else today.year
        projection_date = date(next_quarter_year, next_quarter * 3, calendar.monthrange(next_quarter_year, next_quarter * 3)[1])
    
    # Converter datas para datetime
    start_datetime = datetime.combine(start_date, datetime.min.time())
    end_datetime = datetime.combine(end_date, datetime.max.time())
    
    # Construir query base para o fluxo
    base_query = """
        SELECT DATE(m.created_at) as day, 
               SUM(CASE WHEN m.type = 'entrada' AND m.payment_status = 'realizado' THEN m.amount ELSE 0 END) as income,
               SUM(CASE WHEN m.type IN ('saida', 'despesa_loja', 'estorno') THEN m.amount ELSE 0 END) as outcome
        FROM movement m
        JOIN cashier c ON m.cashier_id = c.id
    """
    
    where_clause = "WHERE m.created_at BETWEEN %s AND %s"
    params = [start_datetime, end_datetime]
    
    if unit_id != 'all':
        where_clause += " AND c.unit_id = %s"
        params.append(unit_id)
    
    group_by = " GROUP BY day ORDER BY day"
    
    cursor.execute(base_query + where_clause + group_by, params)
    flow_data = cursor.fetchall()
    
    # Preencher dias sem movimentação
    flow_by_day = {}
    current_date = start_date
    while current_date <= end_date:
        flow_by_day[current_date] = {'date': current_date, 'income': 0, 'outcome': 0, 'net': 0}
        current_date += timedelta(days=1)
    
    for flow in flow_data:
        flow_by_day[flow['day']]['income'] = flow['income']
        flow_by_day[flow['day']]['outcome'] = flow['outcome']
        flow_by_day[flow['day']]['net'] = flow['income'] - flow['outcome']
    
    # Converter para lista
    flow_list = list(flow_by_day.values())
    
    # Calcular médias para projeção
    avg_income = sum(day['income'] for day in flow_list) / len(flow_list) if flow_list else 0
    avg_outcome = sum(day['outcome'] for day in flow_list) / len(flow_list) if flow_list else 0
    
    # Identificar período de maior/menor movimento
    flow_list.sort(key=lambda x: x['income'], reverse=True)
    best_income_days = flow_list[:min(5, len(flow_list))]
    
    flow_list.sort(key=lambda x: x['income'])
    worst_income_days = flow_list[:min(5, len(flow_list))]
    
    # Ordenar novamente por data para exibição
    flow_list.sort(key=lambda x: x['date'])
    
    # Dados para o gráfico
    graph_data = [
        {'date': day['date'].strftime('%Y-%m-%d'), 'income': float(day['income']), 'outcome': float(day['outcome']), 'net': float(day['net'])} 
        for day in flow_list
    ]
    
    # Projeção para o próximo período
    projection_flow = []
    current_date = end_date + timedelta(days=1)
    while current_date <= projection_date:
        # Considerar dia da semana para projeção mais precisa
        day_of_week = current_date.weekday()
        
        # Calcular médias por dia da semana
        matching_days = [day for day in flow_list if day['date'].weekday() == day_of_week]
        
        if matching_days:
            day_avg_income = sum(day['income'] for day in matching_days) / len(matching_days)
            day_avg_outcome = sum(day['outcome'] for day in matching_days) / len(matching_days)
        else:
            day_avg_income = avg_income
            day_avg_outcome = avg_outcome
        
        projection_flow.append({
            'date': current_date,
            'income': day_avg_income,
            'outcome': day_avg_outcome,
            'net': day_avg_income - day_avg_outcome
        })
        
        current_date += timedelta(days=1)
    
    # Dados de projeção para o gráfico
    projection_graph_data = [
        {'date': day['date'].strftime('%Y-%m-%d'), 'income': float(day['income']), 'outcome': float(day['outcome']), 'net': float(day['net'])} 
        for day in projection_flow
    ]
    
    cursor.close()
    conn.close()
    
    return render_template(
        'reports/cash_flow.html',
        units=units,
        selected_unit_id=unit_id,
        period=period,
        start_date=start_date,
        end_date=end_date,
        flow_data=flow_list,
        projection_flow=projection_flow,
        graph_data=json.dumps(graph_data),
        projection_graph_data=json.dumps(projection_graph_data),
        best_income_days=best_income_days,
        worst_income_days=worst_income_days,
        avg_income=avg_income,
        avg_outcome=avg_outcome
    )

# 9. Relatório de Lucratividade (Acesso apenas superusuários)
@reports.route('/reports/profitability', methods=['GET', 'POST'])
@login_required
def profitability_report():
    if not current_user.is_superuser:
        flash('Acesso não autorizado!', 'error')
        return redirect(url_for('reports.reports_home'))
    
    conn = get_db_connection()
    cursor = conn.cursor()
    
    # Obter todas as unidades
    cursor.execute("SELECT * FROM unit WHERE is_active = 1 ORDER BY name")
    units = cursor.fetchall()
    
    # Definir período para o relatório
    if request.method == 'POST':
        year = int(request.form.get('year', datetime.now().year))
        month = int(request.form.get('month', datetime.now().month)) if request.form.get('month') != 'all' else 'all'
    else:
        year = int(request.args.get('year', datetime.now().year))
        month = int(request.args.get('month', datetime.now().month)) if request.args.get('month') != 'all' else 'all'
    
    # Definir período de consulta
    if month == 'all':
        start_date = date(year, 1, 1)
        end_date = date(year, 12, 31)
        period_name = f"Ano {year}"
    else:
        start_date = date(year, month, 1)
        end_date = date(year, month, calendar.monthrange(year, month)[1])
        period_name = f"{calendar.month_name[month]} de {year}"
    
    # Converter datas para datetime
    start_datetime = datetime.combine(start_date, datetime.min.time())
    end_datetime = datetime.combine(end_date, datetime.max.time())
    
    # Dados de lucratividade por unidade
    profitability_data = []
    
    for unit in units:
        # Receita da unidade
        cursor.execute(
            "SELECT SUM(m.amount) as revenue "
            "FROM movement m "
            "JOIN cashier c ON m.cashier_id = c.id "
            "WHERE c.unit_id = %s AND m.type = 'entrada' AND m.payment_status = 'realizado' "
            "AND m.created_at BETWEEN %s AND %s",
            (unit['id'], start_datetime, end_datetime)
        )
        revenue_result = cursor.fetchone()
        revenue = revenue_result['revenue'] if revenue_result and revenue_result['revenue'] else 0
        
        # Despesas da unidade
        cursor.execute(
            "SELECT SUM(m.amount) as expenses "
            "FROM movement m "
            "JOIN cashier c ON m.cashier_id = c.id "
            "WHERE c.unit_id = %s AND (m.type = 'despesa_loja' OR m.type = 'saida') "
            "AND m.created_at BETWEEN %s AND %s",
            (unit['id'], start_datetime, end_datetime)
        )
        expenses_result = cursor.fetchone()
        expenses = expenses_result['expenses'] if expenses_result and expenses_result['expenses'] else 0
        
        # Estornos
        cursor.execute(
            "SELECT SUM(m.amount) as refunds "
            "FROM movement m "
            "JOIN cashier c ON m.cashier_id = c.id "
            "WHERE c.unit_id = %s AND m.type = 'estorno' "
            "AND m.created_at BETWEEN %s AND %s",
            (unit['id'], start_datetime, end_datetime)
        )
        refunds_result = cursor.fetchone()
        refunds = refunds_result['refunds'] if refunds_result and refunds_result['refunds'] else 0
        
        # Calcular lucro e margem
        profit = revenue - expenses - refunds
        profit_margin = (profit / revenue * 100) if revenue > 0 else 0
        
        profitability_data.append({
            'unit': unit,
            'revenue': revenue,
            'expenses': expenses,
            'refunds': refunds,
            'profit': profit,
            'profit_margin': profit_margin
        })
    
    # Ordenar por lucro
    profitability_data.sort(key=lambda x: x['profit'], reverse=True)
    
    # Calcular totais
    total_revenue = sum(data['revenue'] for data in profitability_data)
    total_expenses = sum(data['expenses'] for data in profitability_data)
    total_refunds = sum(data['refunds'] for data in profitability_data)
    total_profit = total_revenue - total_expenses - total_refunds
    total_profit_margin = (total_profit / total_revenue * 100) if total_revenue > 0 else 0
    
    # Dados para o gráfico
    revenue_data = [{'name': data['unit']['name'], 'value': float(data['revenue'])} for data in profitability_data]
    profit_data = [{'name': data['unit']['name'], 'value': float(data['profit'])} for data in profitability_data]
    margin_data = [{'name': data['unit']['name'], 'value': float(data['profit_margin'])} for data in profitability_data]
    
    cursor.close()
    conn.close()
    
    return render_template(
        'reports/profitability.html',
        units=units,
        profitability_data=profitability_data,
        year=year,
        month=month,
        month_name=calendar.month_name[month] if month != 'all' else 'Todos',
        period_name=period_name,
        total_revenue=total_revenue,
        total_expenses=total_expenses,
        total_refunds=total_refunds,
        total_profit=total_profit,
        total_profit_margin=total_profit_margin,
        revenue_data=json.dumps(revenue_data),
        profit_data=json.dumps(profit_data),
        margin_data=json.dumps(margin_data),
        calendar=calendar
    )