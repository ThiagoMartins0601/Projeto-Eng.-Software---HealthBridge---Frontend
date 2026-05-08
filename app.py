from flask import Flask, render_template, request, redirect, url_for, flash, session
from werkzeug.security import generate_password_hash, check_password_hash
import sqlite3
import os

app = Flask(__name__)
app.secret_key = 'chave_projeto_triagem_2026'

def get_db_connection():
    conn = sqlite3.connect('database.db')
    conn.row_factory = sqlite3.Row
    return conn

def limpar_documento(doc):
    if not doc:
        return ""
    return doc.replace('.', '').replace('-', '').replace('/', '').strip()


def init_db():
    conn = get_db_connection()
    cursor = conn.cursor()
    
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS usuarios (
            cpf TEXT PRIMARY KEY,
            nome TEXT NOT NULL,
            data_nascimento TEXT NOT NULL,
            cep TEXT NOT NULL,
            rua TEXT NOT NULL,
            numero TEXT NOT NULL,
            complemento TEXT,
            bairro TEXT NOT NULL,
            uf TEXT NOT NULL,
            cidade TEXT NOT NULL,
            possui_convenio TEXT,
            nome_convenio TEXT,
            alergias TEXT,
            problema_cronico TEXT,
            senha TEXT NOT NULL
        )
    ''')

    cursor.execute('''
        CREATE TABLE IF NOT EXISTS instituicoes (
            cnpj TEXT PRIMARY KEY,
            razao_social TEXT NOT NULL,
            nome_fantasia TEXT NOT NULL,
            data_fundacao TEXT,
            tipo_instituicao TEXT NOT NULL,
            telefone TEXT NOT NULL,
            email TEXT NOT NULL,
            cep TEXT NOT NULL,
            rua TEXT NOT NULL,
            numero TEXT NOT NULL,
            complemento TEXT,
            bairro TEXT NOT NULL,
            uf TEXT NOT NULL,
            cidade TEXT NOT NULL,
            senha TEXT NOT NULL
        )
    ''')
    
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS triagens (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            paciente_cpf TEXT,
            data_hora TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            titulo TEXT,
            resumo_ia TEXT,
            FOREIGN KEY(paciente_cpf) REFERENCES usuarios(cpf)
        )
    ''')
    
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS consultas (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            paciente_cpf TEXT,
            instituicao_cnpj TEXT,
            data_agendada TEXT,
            status TEXT DEFAULT 'Pendente',
            triagem_id INTEGER,
            FOREIGN KEY(paciente_cpf) REFERENCES usuarios(cpf),
            FOREIGN KEY(instituicao_cnpj) REFERENCES instituicoes(cnpj),
            FOREIGN KEY(triagem_id) REFERENCES triagens(id)
        )
    ''')
    
    conn.commit()
    conn.close()

init_db()


@app.route('/')
def index():
    if 'user_id' in session:
        return redirect(url_for('dashboard'))
    return render_template('login.html')

@app.route('/login', methods=['POST'])
def login():
    identificador = limpar_documento(request.form['identificador'])
    senha = request.form['senha']
    
    conn = get_db_connection()
    
    user = conn.execute('SELECT * FROM usuarios WHERE cpf = ?', (identificador,)).fetchone()
    if user and check_password_hash(user['senha'], senha):
        session.update({'user_id': user['cpf'], 'user_type': 'paciente', 'user_nome': user['nome']})
        conn.close()
        return redirect(url_for('dashboard'))
    
    inst = conn.execute('SELECT * FROM instituicoes WHERE cnpj = ?', (identificador,)).fetchone()
    if inst and check_password_hash(inst['senha'], senha):
        session.update({'user_id': inst['cnpj'], 'user_type': 'instituicao', 'user_nome': inst['nome_fantasia']})
        conn.close()
        return redirect(url_for('dashboard'))
    
    conn.close()
    flash('Identificador ou senha incorretos.')
    return redirect(url_for('index'))


@app.route('/cadastro_paciente', methods=['GET', 'POST'])
def cadastro_paciente():
    if request.method == 'POST':
        f = request.form
        cpf_limpo = limpar_documento(f['cpf'])
        senha_hash = generate_password_hash(f['senha'])
        
        dados = (
            cpf_limpo, f['nome'], f['data_nascimento'], f['cep'], f['rua'], f['numero'], 
            f.get('complemento', ''), f['bairro'], f['uf'], f['cidade'], 
            f['possui_convenio'], f.get('nome_convenio', ''), f.get('alergias', ''), 
            f.get('problema_cronico', ''), senha_hash
        )
        
        try:
            conn = get_db_connection()
            conn.execute('INSERT INTO usuarios VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)', dados)
            conn.commit()
            conn.close()
            flash('Cadastro realizado com sucesso! Faça seu login.')
            return redirect(url_for('index'))
        except sqlite3.IntegrityError:
            flash('Erro: Este CPF já está cadastrado.')
            
    return render_template('cadastro_paciente.html')

@app.route('/cadastro_instituicao', methods=['GET', 'POST'])
def cadastro_instituicao():
    if request.method == 'POST':
        f = request.form
        cnpj_limpo = limpar_documento(f['cnpj'])
        senha_hash = generate_password_hash(f['senha'])
        
        dados = (
            cnpj_limpo, f['razao_social'], f['nome_fantasia'], f.get('data_fundacao', ''), 
            f['tipo_instituicao'], f['telefone'], f['email'], f['cep'], f['rua'], 
            f['numero'], f.get('complemento', ''), f['bairro'], f['uf'], f['cidade'], senha_hash
        )
        
        try:
            conn = get_db_connection()
            conn.execute('INSERT INTO instituicoes VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)', dados)
            conn.commit()
            conn.close()
            flash('Instituição cadastrada com sucesso!')
            return redirect(url_for('index'))
        except sqlite3.IntegrityError:
            flash('Erro: Este CNPJ já está cadastrado.')
            
    return render_template('cadastro_instituicao.html')


@app.route('/dashboard')
def dashboard():
    if 'user_id' not in session:
        return redirect(url_for('index'))
    
    conn = get_db_connection()
    if session['user_type'] == 'paciente':
        clinicas = conn.execute('SELECT * FROM instituicoes').fetchall()
        historico = conn.execute('SELECT * FROM triagens WHERE paciente_cpf = ? ORDER BY data_hora DESC', 
                                 (session['user_id'],)).fetchall()
        return render_template('dashboard_paciente.html', clinicas=clinicas, historico=historico)
    else:
        fila = conn.execute('''
            SELECT c.*, u.nome, u.data_nascimento, t.resumo_ia 
            FROM consultas c 
            JOIN usuarios u ON c.paciente_cpf = u.cpf 
            LEFT JOIN triagens t ON c.triagem_id = t.id
            WHERE c.instituicao_cnpj = ? ORDER BY c.data_agendada ASC''', (session['user_id'],)).fetchall()
        return render_template('dashboard_instituicao.html', fila=fila)

@app.route('/salvar_triagem', methods=['POST'])
def salvar_triagem():
    """Salva um resumo de conversa gerado pela IA."""
    if session.get('user_type') != 'paciente':
        return redirect(url_for('index'))
    
    resumo = request.form['resumo_ia']
    titulo = request.form.get('titulo', 'Nova Triagem')
    
    conn = get_db_connection()
    conn.execute('INSERT INTO triagens (paciente_cpf, titulo, resumo_ia) VALUES (?, ?, ?)',
                 (session['user_id'], titulo, resumo))
    conn.commit()
    conn.close()
    flash('Triagem salva com sucesso.')
    return redirect(url_for('dashboard'))

@app.route('/agendar/<cnpj>', methods=['POST'])
def agendar(cnpj):
    if session.get('user_type') != 'paciente':
        return redirect(url_for('index'))
    
    data = request.form['data_consulta']
    conn = get_db_connection()
    
    ultima_triagem = conn.execute('SELECT id FROM triagens WHERE paciente_cpf = ? ORDER BY id DESC LIMIT 1', 
                                  (session['user_id'],)).fetchone()
    
    triagem_id = ultima_triagem['id'] if ultima_triagem else None
    
    conn.execute('''INSERT INTO consultas (paciente_cpf, instituicao_cnpj, data_agendada, triagem_id) 
                    VALUES (?, ?, ?, ?)''', (session['user_id'], cnpj, data, triagem_id))
    conn.commit()
    conn.close()
    flash('Agendamento realizado!')
    return redirect(url_for('dashboard'))

@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('index'))

if __name__ == '__main__':
    app.run(debug=True)
