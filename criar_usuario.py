from config import Config
import pymysql
from pymysql.cursors import DictCursor
from werkzeug.security import generate_password_hash
from datetime import datetime

def get_db_connection():
    return pymysql.connect(
        host=Config.MYSQL_HOST,
        port=int(Config.MYSQL_PORT),
        user=Config.MYSQL_USER,
        password=Config.MYSQL_PASSWORD,
        database=Config.MYSQL_DB,
        cursorclass=DictCursor,
        ssl={"ssl": {"mode": "REQUIRED"}}
    )

def criar_admin():
    # Dados do usuário
    name = "caio"
    email = "caio@teste.com"
    cpf = "123.456.789-00"
    phone = "(21) 99999-9999"
    role = "admin"
    is_superuser = True
    is_active = True
    senha = "sua_senha_secreta"
    password_hash = generate_password_hash(senha)
    
    conn = get_db_connection()
    cursor = conn.cursor()
    
    try:
        # Verificar se o usuário já existe
        cursor.execute("SELECT id FROM user WHERE email = %s", (email,))
        existing_user = cursor.fetchone()
        
        if existing_user:
            print(f"Usuário com email {email} já existe!")
            return
        
        # Criar novo usuário
        cursor.execute(
            "INSERT INTO user (name, email, password_hash, cpf, phone, role, is_superuser, is_active, last_login) "
            "VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)",
            (name, email, password_hash, cpf, phone, role, is_superuser, is_active, datetime.now())
        )
        
        conn.commit()
        print(f"Usuário {email} criado com sucesso!")
        print(f"Senha: {senha}")
        
    except Exception as e:
        conn.rollback()
        print(f"Erro ao criar usuário: {str(e)}")
    finally:
        cursor.close()
        conn.close()

if __name__ == "__main__":
    criar_admin()