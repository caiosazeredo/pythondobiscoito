@echo off
echo Criando estrutura do projeto Casa do Biscoito...

:: Criar pasta principal
mkdir casa_do_biscoito
cd casa_do_biscoito

:: Criar estrutura simplificada
mkdir static
mkdir static\css
mkdir static\js
mkdir static\img
mkdir templates
mkdir templates\auth
mkdir templates\admin
mkdir templates\user

:: Criar arquivos principais
echo # Arquivo principal > app.py
echo # Modelos de dados > models.py
echo # Configuração do banco > config.py
echo # Script para popular o banco > populate_db.py
echo # Dependências do projeto > requirements.txt

echo Estrutura criada com sucesso!
cd ..